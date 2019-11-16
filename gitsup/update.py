from http import HTTPStatus
import json
from typing import Any, Callable, Dict, Iterable, Optional, Set
import requests
import sys

from .config import Config, Module, get_config

GITHUB_ENDPOINT = "https://api.github.com"
URL_TEMPLATE = GITHUB_ENDPOINT + "/repos/{owner}/{repository}/{url}"
UPDATE_SUBMODULE_TEMPLATE = (
    "* Update submodule '{name}' to HEAD of branch '{branch}':\n\t{oid}"
)
UPDATE_MESSAGE_TEMPLATE = (
    "Update submodules in '{branch}' to latest commits\n\n{submodule_messages}"
)


def update_git_submodules(config_file_path: Optional[str] = None) -> None:
    """
    Update git submodules of the configured repository to latest
    revision of the repositories underlying the configured submodules.

    :param config_file_path: path to optional configuration file. If
        this path isn't provided, the config is retrieved from the
        environment
    :raise ConnectionError: connection to API failed (probably
        temporary)
    :raise FileNotFoundError: provided config file doesn't exist
    :raise PermissionError: invalid Github personal access token
    :raise RuntimeError: update failed
    """

    config = get_config(config_file_path)

    print(f"Created git submodule updater using config\nConfig: {config}")
    print(f"Updating '{config.tree.parent.spec}'")

    current_oid = _get_oid(config.token, config.tree.parent)
    current_submodule_oids = _get_current_submodule_oids(config, current_oid)
    new_submodule_oids = {
        n: _get_oid(config.token, config.tree.submodules[n])
        for n in current_submodule_oids.keys()
    }
    changed_submodules = _get_changed_submodules(
        config, current_submodule_oids, new_submodule_oids
    )

    if changed_submodules:
        tree_oid = _create_updated_tree(config, current_oid, changed_submodules)
        commit_oid = _commit_tree(config, current_oid, tree_oid, changed_submodules)
        _commit_oid(config, commit_oid)

        print(f"Updated '{config.tree.parent.spec}'")
    else:
        print(f"No changed submodules found for '{config.tree.parent.spec}'")


def _get_oid(token: str, module: Module) -> str:
    """
    Get the latest commit oid/sha from the provided repository an
    branch.

    See https://developer.github.com/v3/repos/branches/#get-branch.
    """
    url = URL_TEMPLATE.format(
        owner=module.owner,
        repository=module.repository,
        url=f"branches/{module.branch}",
    )
    response = _request(
        error=f"Failed to get oid for '{module.spec}'",
        fn=requests.get,
        url=url,
        headers=_get_headers(token),
    )

    oid = response["commit"]["sha"]

    return oid


def _request(error: str, fn: Callable, **kwargs) -> Dict[str, Any]:
    """
    Error handling for Github API request calls.

    This function is supposed to wrap all Github API calls and will
    handle all error cases.
    """

    try:
        response = fn(**kwargs)
    except requests.ConnectionError as e:
        raise ConnectionError(f"{error}: failed to connect to API - {e}") from e

    if not response.ok:
        try:
            message = response.json()["message"]
        except json.JSONDecodeError:
            message = response.text

        if response.status_code == HTTPStatus.UNAUTHORIZED:
            raise PermissionError(
                f"{error}: invalid Github personal access token " f"provided"
            )
        elif response.status_code == HTTPStatus.NOT_FOUND:
            if message == "Not found":
                raise RuntimeError(
                    f"{error}: couldn't access repository. Please check if the owner "
                    f"and repository exist and the Github personal access token has "
                    f"permissions 'repo' assigned"
                )
            elif message == "Branch not found":
                raise RuntimeError(f"{error}: invalid branch")
            else:
                raise RuntimeError(f"{error}: {message} ({response.status_code})")
        else:
            raise RuntimeError(f"{error}: {message} ({response.status_code})")

    try:
        data = response.json()
    except json.JSONDecodeError:
        raise RuntimeError(
            f"{error}: could not decode API response - "
            f"{response.text} ({response.status_code})"
        ) from None

    return data


def _get_headers(token: str) -> Dict[str, str]:
    """ Create headers for API calls. """

    return {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
    }


def _get_current_submodule_oids(config: Config, current_oid: str) -> Dict[str, str]:
    """
    Get the current submodule oids/shas from the parent repository.

    See https://developer.github.com/v3/git/trees/#get-a-tree.
    """

    url = URL_TEMPLATE.format(
        owner=config.tree.parent.owner,
        repository=config.tree.parent.repository,
        url=f"git/trees/{current_oid}",
    )
    response = _request(
        error=f"Failed to update tree for '{config.tree.parent.spec}'",
        fn=requests.get,
        url=url,
        headers=_get_headers(config.token),
    )

    current_submodules = tuple(
        filter(lambda x: x["type"] == "commit", response["tree"])
    )
    configured_submodule_paths = set(config.tree.submodule_paths)
    current_submodule_paths = set([p["path"] for p in current_submodules])
    if current_submodule_paths != configured_submodule_paths:
        valid_submodule_paths = _parse_submodule_changes(
            config, configured_submodule_paths, current_submodule_paths
        )
    else:
        valid_submodule_paths = current_submodule_paths

    oids = {}
    for p in current_submodules:
        if p["path"] in valid_submodule_paths:
            name = config.tree.get_supmodule_repository_from_path(p["path"])
            oids[name] = p["sha"]

    return oids


def _parse_submodule_changes(
    config: Config,
    configured_submodule_paths: Set[str],
    current_submodule_paths: Set[str],
) -> Iterable[str]:
    """
    Compare the current oids/shas of the configured submodules and find
    valid/new/missing submodules. New and missing submodules will only
    be indicated to the user. The valid submodules will returned and
    used for update in the following steps..
    """

    missing_submodule_paths = configured_submodule_paths - current_submodule_paths
    added_submodule_paths = (
        current_submodule_paths
        - current_submodule_paths.intersection(configured_submodule_paths)
    )
    valid_submodule_paths = (
        current_submodule_paths - added_submodule_paths - missing_submodule_paths
    )

    if missing_submodule_paths:
        missing_submodule_names = ", ".join(
            [
                f"{config.tree.get_supmodule_repository_from_path(p)}/{p}"
                for p in missing_submodule_paths
            ]
        )
        print(
            f"Submodule missing, please remove from config: "
            f"{missing_submodule_names}",
            file=sys.stderr,
        )
    if added_submodule_paths:
        added_submodule_paths = ", ".join(added_submodule_paths)
        print(
            f"Additional submodule path found, please add to config if it "
            f"should be updated automatically: {added_submodule_paths}",
            file=sys.stderr,
        )

    return valid_submodule_paths


def _get_changed_submodules(
    config: Config, current_oids: Dict[str, str], new_oids: Dict[str, str]
) -> Dict[str, str]:
    """
    Check the oids/shas of the configured (valid) submodules and drop
    submodules that haven't changed since the last commit.
    """

    changed_oids = {}
    for name in current_oids.keys():
        if current_oids[name] != new_oids[name]:
            changed_oids[name] = new_oids[name]

    if changed_oids:
        print(f"Update submodules:")
        for name in changed_oids.keys():
            owner = config.tree.submodules[name].owner
            branch = config.tree.submodules[name].branch
            print(
                f"\t[{owner}/{name}:{branch}]: {current_oids[name]} vs {new_oids[name]}"
            )

    return changed_oids


def _create_updated_tree(
    config: Config, current_oid: str, latest_submodule_oids: Dict[str, str]
) -> str:
    """
    Update the heads of the git submodule tree to the latest submodule
    commits.

    See https://developer.github.com/v3/git/trees/#create-a-tree.
    """

    url = URL_TEMPLATE.format(
        owner=config.tree.parent.owner,
        repository=config.tree.parent.repository,
        url=f"git/trees",
    )
    data = {
        "base_tree": current_oid,
        "tree": [
            {
                "path": config.tree.submodules[name].path,
                "mode": "160000",
                "type": "commit",
                "sha": oid,
            }
            for name, oid in latest_submodule_oids.items()
        ],
    }
    response = _request(
        error=f"Failed to update tree for '{config.tree.parent.spec}'",
        fn=requests.post,
        url=url,
        headers=_get_headers(config.token),
        json=data,
    )

    oid = response["sha"]

    return oid


def _commit_tree(
    config: Config,
    current_oid: str,
    tree_oid: str,
    changed_submodule_oids: Dict[str, str],
) -> str:
    """
    Commit the updated submodule tree to the parent repository..

    See https://developer.github.com/v3/git/commits/#create-a-commit.
    """

    url = URL_TEMPLATE.format(
        owner=config.tree.parent.owner,
        repository=config.tree.parent.repository,
        url=f"git/commits",
    )
    submodule_messages = []
    for name, oid in changed_submodule_oids.items():
        submodule_messages.append(
            UPDATE_SUBMODULE_TEMPLATE.format(
                name=name, branch=config.tree.submodules[name].branch, oid=oid
            )
        )
    message = UPDATE_MESSAGE_TEMPLATE.format(
        branch=config.tree.parent.branch,
        submodule_messages="\n".join(submodule_messages),
    )
    data = {"message": message, "tree": tree_oid, "parents": [current_oid]}
    response = _request(
        error=f"Failed to commit tree to '{config.tree.parent.spec}'",
        fn=requests.post,
        url=url,
        headers=_get_headers(config.token),
        json=data,
    )
    oid = response["sha"]

    return oid


def _commit_oid(config: Config, new_oid: str) -> None:
    """
    Update the configured branch of the parent repository to the updated
    submodule tree.

    See https://developer.github.com/v3/git/refs/#update-a-reference.
    """

    url = URL_TEMPLATE.format(
        owner=config.tree.parent.owner,
        repository=config.tree.parent.repository,
        url=f"git/refs/heads/{config.tree.parent.branch}",
    )
    data = {"sha": new_oid}
    _request(
        error=f"Failed to commit to '{config.tree.parent.spec}'",
        fn=requests.patch,
        url=url,
        headers=_get_headers(config.token),
        json=data,
    )
