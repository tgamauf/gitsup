from functools import lru_cache
from typing import Any, Dict, Iterable, NamedTuple, Optional
import os
import re
import yaml


_DEFAULT_BRANCH = "master"


class Module(NamedTuple):
    """
    Storage class for Git module configuration.

    It stores the repository and owner, branch (optional) path of the
    repository.
    """

    owner: str
    repository: str
    branch: str
    path: Optional[str] = None

    def __str__(self) -> str:
        if self.path:
            path_string = f", path: {self.path}"
        else:
            path_string = ""
        return (
            f"owner: {self.owner}, repository: {self.repository}, branch: "
            f"{self.branch}{path_string}"
        )

    @property
    def spec(self) -> str:
        return f"{self.owner}/{self.repository}:{self.branch}"


class Tree(NamedTuple):
    """
    Storage class for Git tree configuration.

    It consists of the parent repository confiaguration and a dict
    mapping the repository name of a Git submodule to the module
    configuration.
    """

    parent: Module
    submodules: Dict[str, Module]

    def __str__(self) -> str:
        submodule_strings = [f"({p})" for p in self.submodules.values()]
        return f"parent ({self.parent}), submodules {', '.join(submodule_strings)}"

    @property
    def submodule_paths(self) -> Iterable[str]:
        return tuple([p.path for p in self.submodules.values()])

    def get_supmodule_repository_from_path(self, path: str) -> Optional[str]:
        for name, module in self.submodules.items():
            if module.path == path:
                return name

        return None


class Config(NamedTuple):
    """
    Storage class for full gitsup configuration.

    It stores to Github personal access token and repository tree.
    """

    token: str
    tree: Tree

    def __str__(self) -> str:
        return f"tree ({self.tree})"


def get_config(*, config_file_path: Optional[str], token: Optional[str]) -> Config:
    """
    Get the configuration from either the environment or the provided
    config file.

    The token and configuration tree are considered separate and each of
    them can be configured either via environment or config file. The
    full tree configuration must be configured fully via either
    environment or config file. If a part is missing an exception will
    be raised.

    If the token is provided by parameter it overrides both the
    environment and the config file.

    :param config_file_path: file path to yaml/json file that contains
        the configuration
    :param token: Github API token (has priority over environment or
        config file
    :return: storage object containing the full configuration
    :raise RuntimeError: configuration failed
    :raise FileNotFoundError: config file path has been provided, but
        file doesn't exist
    """

    # Try to get the token from either the provided parameter, the
    #  environment or the config file
    token = (
        token
        or _get_token_from_environment()
        or _get_token_from_config_file(config_file_path)
    )

    if not token:
        raise RuntimeError("No Github personal access token provided")

    try:
        # Get the repository tree config from either the environment or
        #  the config file
        tree = _get_tree_from_environment() or _get_tree_from_config_file(
            config_file_path
        )
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file '{config_file_path}' doesn't " f"exist")

    if not tree:
        raise RuntimeError("No repository tree provided")

    return Config(token=token, tree=tree)


def _get_token_from_environment() -> Optional[str]:
    """ Get the token from the environment. """

    try:
        token = os.environ["GITSUP_TOKEN"]
    except KeyError:
        token = None

    return token


def _get_tree_from_environment() -> Optional[Tree]:
    """ Get the repository tree configuration from the environment. """

    try:
        owner = os.environ["GITSUP_OWNER"]
        repository = os.environ["GITSUP_REPOSITORY"]
        try:
            branch = os.environ["GITSUP_BRANCH"]
        except KeyError:
            branch = _DEFAULT_BRANCH
        parent = Module(owner=owner, repository=repository, branch=branch)

        # Get the submodules from the environment. The format of the
        #  keys is GITSUP_SUBMODULE_<repository>_<OWNER | BRANCH | PATH>
        submodule_names = _parse_environment_list(os.environ["GITSUP_SUBMODULES"])
        submodule_config = {}
        for key, value in os.environ.items():
            for name in submodule_names:
                config = submodule_config.setdefault(name, {})

                key_match = re.fullmatch(
                    f"GITSUP_SUBMODULE_{name}_(?P<type>OWNER|BRANCH|PATH)", key
                )
                if key_match:
                    type_ = key_match.group("type").lower()
                    config[type_] = value

        # Create the submodule config from the provided environment keys
        #  and the default config
        submodules = {}
        for name, config in submodule_config.items():
            submodules[name] = _create_submodule(
                name=name, default_owner=owner, config=config
            )

        if submodules:
            tree = Tree(parent=parent, submodules=submodules)
        else:
            tree = None
    except KeyError:
        tree = None

    return tree


def _parse_environment_list(input: str) -> Iterable[str]:
    if not input:
        return ()

    result = [value.strip() for value in input.split(",")]
    # Filter empty values
    result = filter(lambda x: x, result)

    return tuple(result)


def _create_submodule(name: str, default_owner: str, config: Dict[str, str]) -> Module:
    # All config options are optional and default values are used
    #  if an option isn't found:
    #    owner: the owner of the parent module
    #    branch: master
    #    path: the repository name
    try:
        owner = config["owner"]
    except (KeyError, TypeError):
        owner = default_owner
    try:
        branch = config["branch"]
    except (KeyError, TypeError):
        branch = _DEFAULT_BRANCH
    try:
        path = config["path"]
    except (KeyError, TypeError):
        path = name
    submodule = Module(owner=owner, repository=name, branch=branch, path=path)

    return submodule


def _get_token_from_config_file(config_file_path: Optional[str]) -> Optional[str]:
    """ Get the token from the configuration file. """

    if not config_file_path:
        return None

    data = _read_config(config_file_path)

    try:
        token = data["token"]
    except KeyError:
        token = None

    return token


@lru_cache(maxsize=1)
def _read_config(config_file_path: str) -> Dict[str, Any]:
    """ Cached loading and decoding of the config file. """

    with open(config_file_path) as file:
        data = yaml.load(file, Loader=yaml.SafeLoader)

    if not data:
        raise RuntimeError(f"Invalid config file provided: {config_file_path}")

    return data


def _get_tree_from_config_file(config_file_path: Optional[str]) -> Optional[Tree]:
    """
    Get the repository tree configuration from the configuration file.
    """

    if not config_file_path:
        return None

    data = _read_config(config_file_path)

    try:
        owner = data["owner"]
        repository = data["repository"]
        try:
            branch = data["branch"]
        except KeyError:
            branch = _DEFAULT_BRANCH
        parent = Module(owner=owner, repository=repository, branch=branch)

        submodules = {}
        # Account for a single submodule with default config
        if isinstance(data["submodules"], str):
            name = data["submodules"]
            submodules[name] = _create_submodule(
                name=name, default_owner=owner, config={}
            )
        else:
            for name, config in data["submodules"].items():
                submodules[name] = _create_submodule(
                    name=name, default_owner=owner, config=config
                )

        if submodules:
            tree = Tree(parent=parent, submodules=submodules)
        else:
            tree = None
    except KeyError:
        tree = None

    return tree
