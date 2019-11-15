from typing import Dict, Optional
import requests
import sys

from .config import Project, get_config


class Updater:
    GITSUPT_ENDPOINT = "https://api.github.com"
    UPDATE_MESSAGE_TEMPLATE = (
        "Update submodules in '{branch}' to latest commits\n\n{submodule_messages}"
    )

    def __init__(self, config_file_path: Optional[str] = None) -> None:
        self._config = get_config(config_file_path)

        print(f"Created git submodule updater using config\nConfig: {self._config}")#TODO

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {self._config.token}",
        }

    def __call__(self) -> None:
        print(f"Updating '{self._config.tree.parent.spec}'")

        current_oid = self._get_oid(self._config.tree.parent)
        current_subproject_oids = self._get_current_subproject_oids(current_oid)
        new_subproject_oids = {n: self._get_oid(self._config.tree.subprojects[n])
                               for n in current_subproject_oids.keys()}
        changed_subprojects = self._get_changed_subprojects(current_subproject_oids,
                                                            new_subproject_oids)

        if changed_subprojects:
            tree_oid = self._create_updated_tree(current_oid, changed_subprojects)
            commit_oid = self._commit_tree(current_oid, tree_oid, changed_subprojects)
            self._commit_oid(commit_oid)

            print(f"Updated '{self._config.tree.parent.spec}'")
        else:
            print(f"No changed submodules found for '{self._config.tree.parent.spec}'")

    def _get_oid(self, project: Project) -> str:
        url = (f"{self.GITSUPT_ENDPOINT}/repos/{project.owner}/{project.repository}/"
               f"branches/{project.branch}")
        response = requests.get(url=url, headers=self._headers)

        if not response.ok:
            raise RuntimeError(
                f"Failed to get oid for '{project.spec}': {response.json()['message']}"
            )

        oid = response.json()["commit"]["sha"]

        return oid

    def _get_current_subproject_oids(self, tree_oid: str) -> Dict[str, str]:
        url = (f"{self.GITSUPT_ENDPOINT}/repos/{self._config.tree.parent.owner}/"
               f"{self._config.tree.parent.repository}/git/trees/{tree_oid}")
        response = requests.get(url=url, headers=self._headers)

        if not response.ok:
            raise RuntimeError(
                f"Failed to update tree for '{self._config.tree.parent.spec}': "
                f"{response.json()['message']}"
            )
        current_subprojects = tuple(filter(lambda x: x["type"] == "commit", response.json()["tree"]))

        configured_subproject_paths = set(self._config.tree.subproject_paths)
        current_subproject_paths = set([p["path"] for p in current_subprojects])
        if current_subproject_paths != configured_subproject_paths:
            missing_submodule_paths = configured_subproject_paths - current_subproject_paths
            added_submodule_paths = (current_subproject_paths
                                     - current_subproject_paths.intersection(configured_subproject_paths))
            valid_submodule_paths = (current_subproject_paths
                                     - added_submodule_paths
                                     - missing_submodule_paths)

            if missing_submodule_paths:
                missing_submodule_names = ", ".join([
                    f"{self._config.tree.get_supbroject_repository_from_path(p)}/{p}"
                    for p in missing_submodule_paths
                ])
                print(f"Submodule missing, please remove from config: "
                      f"{missing_submodule_names}", file=sys.stderr)
            if added_submodule_paths:
                added_submodule_paths = ", ".join(added_submodule_paths)
                print(f"Additional submodule path found, please add to config if it "
                      f"should be updated automatically: {added_submodule_paths}",
                      file=sys.stderr)
        else:
            valid_submodule_paths = current_subproject_paths

        oids = {}
        for p in current_subprojects:
            if p["path"] in valid_submodule_paths:
                name = self._config.tree.get_supbroject_repository_from_path(p["path"])
                oids[name] = p["sha"]

        return oids

    def _get_changed_subprojects(self,
                                 current_oids: Dict[str, str],
                                 new_oids: Dict[str, str]) -> Dict[str, str]:
        changed_oids = {}
        for name in current_oids.keys():
            if current_oids[name] != new_oids[name]:
                changed_oids[name] = new_oids[name]

        if changed_oids:
            print(f"Update submodules:")
            for name in changed_oids.keys():
                owner = self._config.tree.subprojects[name].owner
                branch = self._config.tree.subprojects[name].branch
                print(f"\t[{owner}/{name}:{branch}]: {current_oids[name]} vs {new_oids[name]}")

        return changed_oids

    def _create_updated_tree(self,
                             current_oid: str,
                             latest_subproject_oids: Dict[str, str]) -> str:
        url = (f"{self.GITSUPT_ENDPOINT}/repos/{self._config.tree.parent.owner}/"
               f"{self._config.tree.parent.repository}/git/trees")
        data = {"base_tree": current_oid,
                "tree": [
                    {
                        "path": self._config.tree.subprojects[name].path,
                        "mode": "160000",
                        "type": "commit",
                        "sha": oid
                    } for name, oid in latest_subproject_oids.items()
                ]}
        response = requests.post(url=url, headers=self._headers, json=data)

        if not response.ok:
            owner = self._config.tree.parent.owner
            repository = self._config.tree.parent.repository
            branch = self._config.tree.parent.branch
            raise RuntimeError(
                f"Failed to update tree for '{self._config.tree.parent.spec}': "
                f"{response.json()['message']}"
            )

        oid = response.json()["sha"]

        return oid

    def _commit_tree(self,
                     current_oid: str,
                     tree_oid: str,
                     changed_subproject_oids: Dict[str, str]) -> str:
        url = (f"{self.GITSUPT_ENDPOINT}/repos/{self._config.tree.parent.owner}/"
               f"{self._config.tree.parent.repository}/git/commits")

        submodule_messages = []
        for name, oid in changed_subproject_oids.items():
            submodule_messages.append(
                f"* Update submodule '{name}' HEAD of branch "
                f"'{self._config.tree.subprojects[name].branch}':\n\t{oid}"
            )
        message = self.UPDATE_MESSAGE_TEMPLATE.format(
            branch=self._config.tree.parent.branch,
            submodule_messages="\n".join(submodule_messages)
        )

        data = {"message": message, "tree": tree_oid, "parents": [current_oid]}
        response = requests.post(url=url, headers=self._headers, json=data)

        if not response.ok:
            raise RuntimeError(
                f"Failed to commit tree to '{self._config.tree.parent.spec}': "
                f"{response.json()['message']}"
            )

        oid = response.json()["sha"]

        return oid

    def _commit_oid(self, new_oid: str) -> None:
        url = (f"{self.GITSUPT_ENDPOINT}/repos/{self._config.tree.parent.owner}/"
               f"{self._config.tree.parent.repository}/git/refs/heads/"
               f"{self._config.tree.parent.branch}")
        data = {"sha": new_oid}
        response = requests.patch(url=url, headers=self._headers, json=data)

        if not response.ok:
            raise RuntimeError(
                f"Failed to commit to '{self._config.tree.parent.spec}': "
                f"{response.json()['message']}")
