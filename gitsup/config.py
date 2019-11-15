from typing import Dict, Iterable, NamedTuple, Optional, Tuple
import os
import re
import yaml

__DEFAULT_BRANCH = "master"
__SUBMODULE_REGEX = re.compile(
    r"GITSUPT_SUBMODULE_(?P<name>.+)_(?P<type>OWNER|REPOSITORY|BRANCH|PATH)"
)


class Project(NamedTuple):
    owner: str
    repository: str
    branch: str
    path: Optional[str] = None

    def __str__(self) -> str:
        if self.path:
            path_string = f", path: {self.path}"
        else:
            path_string = ""
        return (f"owner: {self.owner}, repository: {self.repository}, branch: "
                f"{self.branch}{path_string}")

    @property
    def spec(self) -> str:
        return f"{self.owner}/{self.repository}:{self.branch}"


class Tree(NamedTuple):
    parent: Project
    subprojects: Dict[str, Project]

    def __str__(self) -> str:
        subproject_strings = [f"({p})" for p in self.subprojects.values()]
        return f"parent ({self.parent}), subprojects {', '.join(subproject_strings)}"

    @property
    def subproject_paths(self) -> Iterable[str]:
        return tuple([p.path for p in self.subprojects.values()])

    def get_supbroject_repository_from_path(self, path: str) -> Optional[str]:
        for name, project in self.subprojects.items():
            if project.path == path:
                return name

        return None


class Config(NamedTuple):
    token: str
    tree: Tree

    def __str__(self) -> str:
        return f"tree ({self.tree})"


def get_config(config_file_path: Optional[str]) -> Config:
    env_token, env_tree = _get_config_from_environment()

    if config_file_path:
        file_token, file_tree = _get_config_from_config_file(config_file_path)
    else:
        file_token = None
        file_tree = None

    if env_token:
        print("Use Github personal access token from environment")
        token = env_token
    elif file_token:
        print(f"Use Github personal access token form config file '{config_file_path}'")
        token = file_token
    else:
        raise RuntimeError("No Github personal access token provided")

    if env_tree:
        print("Use project tree from environment")
        tree = env_tree
    elif file_tree:
        print(f"Use project tree from config file '{config_file_path}'")
        tree = file_tree
    else:
        raise RuntimeError("No project tree provided")

    return Config(token=token, tree=tree)


def _get_config_from_environment() -> Tuple[Optional[str], Optional[Tree]]:
    try:
        token = os.environ["GITSUPT_TOKEN"]
    except KeyError:
        token = None

    try:
        owner = os.environ["GITSUPT_OWNER"]
        repository = os.environ["GITSUPT_REPOSITORY"]
        branch = os.environ["GITSUPT_BRANCH"]
        project = Project(owner=owner, repository=repository, branch=branch)

        # Get the subprojects from the environment. The format of the
        #  keys is GITSUPT_SUBMODULE_<repository>_<OWNER | BRANCH | PATH>
        subproject_config = {}
        for key, value in os.environ.items():
            key_match = re.fullmatch(__SUBMODULE_REGEX, key)
            if key_match:
                type = key_match.group("type").lower()
                name = key_match.group("name")

                config = subproject_config.setdefault(name, {})
                config[type] = value

        # Create the subproject config from the provided environment keys
        #  and the default config
        subprojects = {}
        for name, config in subproject_config.items():
            subprojects[name] = _create_subproject(name=name,
                                                   default_owner=owner,
                                                   config=config)

        if not subprojects:
            raise RuntimeError(f"No submodule configuration found for parent repository "
                               f"'{owner}/{repository}' in environment. The project and "
                               f"submodules must be configured fully in either the "
                               f"environment or the config file")

        tree = Tree(parent=project, subprojects=subprojects)
    except KeyError:
        tree = None

    return token, tree


def _create_subproject(name: str, default_owner: str, config: Dict[str, str]) -> Project:
    # All config options are optional and default values are used
    #  if an option isn't found:
    #    owner: the owner of the parent project
    #    branch: master
    #    path: the repository name
    try:
        owner = config["owner"]
    except (KeyError, TypeError):
        owner = default_owner
    try:
        branch = config["branch"]
    except (KeyError, TypeError):
        branch = __DEFAULT_BRANCH
    try:
        path = config["path"]
    except (KeyError, TypeError):
        path = name
    subproject = Project(owner=owner, repository=name, branch=branch, path=path)

    return subproject


def _get_config_from_config_file(config_file_path: str) -> Tuple[Optional[str],
                                                                 Optional[Tree]]:
    with open(config_file_path) as file:
        data = yaml.full_load(file)

    try:
        token = data["token"]
    except KeyError:
        token = None

    try:
        owner = data["owner"]
        repository = data["repository"]
        branch = data["branch"]
        parent = Project(owner=owner, repository=repository, branch=branch)

        subprojects = {}
        for name, config in data["submodules"].items():
            subprojects[name] = _create_subproject(name=name,
                                                   default_owner=owner,
                                                   config=config)

        if not subprojects:
            raise RuntimeError(f"No submodule configuration found for parent repository "
                               f"'{owner}/{repository}' in environment. The project and "
                               f"submodules must be configured fully in either the "
                               f"environment or the config file")

        tree = Tree(parent=parent, subprojects=subprojects)
    except KeyError:
        tree = None

    return token, tree
