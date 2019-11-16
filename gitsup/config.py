from typing import Dict, Iterable, NamedTuple, Optional, Tuple
import os
import re
import yaml

__DEFAULT_BRANCH = "master"


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


def get_config(config_file_path: Optional[str]) -> Config:
    """
    Get the configuration from either the environment or the provided
    config file.

    The token and configuration tree are considered separate and each of
    them can be configured either via environment or config file. The
    full tree configuration must be configured fully via either
    environment or config file. If a part is missing an exception will
    be raised

    :param config_file_path: file path to yaml/json file that contains
        the configuration
    :return: storage object containing the full configuration
    :raise RuntimeError: configuration failed
    :raise FileNotFoundError: config file path has been provided, but
        file doesn't exist
    """

    env_token, env_tree = _get_config_from_environment()

    if config_file_path:
        try:
            file_token, file_tree = _get_config_from_config_file(config_file_path)
        except FileNotFoundError:
            raise FileNotFoundError(f"Config file '{config_file_path}' doesn't exist")
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
        print("Use repository tree from environment")
        tree = env_tree
    elif file_tree:
        print(f"Use repository tree from config file '{config_file_path}'")
        tree = file_tree
    else:
        raise RuntimeError("No repository tree provided")

    return Config(token=token, tree=tree)


def _get_config_from_environment() -> Tuple[Optional[str], Optional[Tree]]:
    try:
        token = os.environ["GITSUP_TOKEN"]
    except KeyError:
        token = None

    try:
        owner = os.environ["GITSUP_OWNER"]
        repository = os.environ["GITSUP_REPOSITORY"]
        branch = os.environ["GITSUP_BRANCH"]
        module = Module(owner=owner, repository=repository, branch=branch)

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

        if not submodules:
            raise RuntimeError(
                f"No submodule configuration found for parent repository "
                f"'{owner}/{repository}' in environment. The repository and "
                f"submodules must be configured fully in either the "
                f"environment or the config file"
            )

        tree = Tree(parent=module, submodules=submodules)
    except KeyError:
        tree = None

    return token, tree


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
        branch = __DEFAULT_BRANCH
    try:
        path = config["path"]
    except (KeyError, TypeError):
        path = name
    submodule = Module(owner=owner, repository=name, branch=branch, path=path)

    return submodule


def _get_config_from_config_file(
    config_file_path: str,
) -> Tuple[Optional[str], Optional[Tree]]:
    with open(config_file_path) as file:
        data = yaml.full_load(file)

    if not data:
        raise RuntimeError(f"Invalid config file provided: {config_file_path}")

    try:
        token = data["token"]
    except KeyError:
        token = None

    try:
        owner = data["owner"]
        repository = data["repository"]
        branch = data["branch"]
        parent = Module(owner=owner, repository=repository, branch=branch)

        submodules = {}
        for name, config in data["submodules"].items():
            submodules[name] = _create_submodule(
                name=name, default_owner=owner, config=config
            )

        if not submodules:
            raise RuntimeError(
                f"No submodule configuration found for parent repository "
                f"'{owner}/{repository}' in environment. The repository and "
                f"submodules must be configured fully in either the "
                f"environment or the config file"
            )

        tree = Tree(parent=parent, submodules=submodules)
    except KeyError:
        tree = None

    return token, tree
