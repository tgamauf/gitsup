from copy import deepcopy
import json
import os
from tempfile import NamedTemporaryFile
from typing import Dict
import unittest
import yaml

import gitsup.config as config


class TestConfig(unittest.TestCase):
    @staticmethod
    def _clear_environment():
        for k in filter(lambda x: x.startswith("GITSUP"), os.environ):
            del os.environ[k]

    @classmethod
    def _set_environment(cls, config):
        cls._clear_environment()

        if "token" in config:
            os.environ["GITSUP_TOKEN"] = config["token"]
        if "owner" in config:
            os.environ["GITSUP_OWNER"] = config["owner"]
        if "repository" in config:
            os.environ["GITSUP_REPOSITORY"] = config["repository"]
        if "branch" in config:
            os.environ["GITSUP_BRANCH"] = config["branch"]

        if "submodules" in config:
            if isinstance(config["submodules"], str):
                os.environ["GITSUP_SUBMODULES"] = config["submodules"]
            else:
                submodules_config = config["submodules"]
                os.environ["GITSUP_SUBMODULES"] = ", ".join(submodules_config)
                for n, c in submodules_config.items():
                    if "owner" in c:
                        os.environ[f"GITSUP_SUBMODULE_{n}_OWNER"] = c["owner"]
                    if "branch" in c:
                        os.environ[f"GITSUP_SUBMODULE_{n}_BRANCH"] = c["branch"]
                    if "path" in c:
                        os.environ[f"GITSUP_SUBMODULE_{n}_PATH"] = c["path"]

    @staticmethod
    def _get_config_file(config, *, write_yaml):
        file = NamedTemporaryFile(mode="w+t", delete=False)

        if write_yaml:
            yaml.dump(config, file.file)
        else:
            json.dump(config, file.file)

        return file.name

    def _assert_tree_valid(self, tree: config.Tree, check: Dict):
        self.assertEqual(tree.parent.owner, check["owner"])
        self.assertEqual(tree.parent.repository, check["repository"])
        self.assertEqual(tree.parent.branch, check["branch"])
        self.assertSetEqual(
            set(tree.submodules.keys()), set(check["submodules"].keys())
        )
        self.assertSetEqual(
            set(tree.submodule_paths),
            set(s["path"] for s in check["submodules"].values()),
        )
        for name in tree.submodules.keys():
            self.assertEqual(
                tree.submodules[name].owner, check["submodules"][name]["owner"]
            )
            self.assertEqual(tree.submodules[name].repository, name)
            self.assertEqual(
                tree.submodules[name].branch, check["submodules"][name]["branch"]
            )
            self.assertEqual(
                tree.submodules[name].path, check["submodules"][name]["path"]
            )
            self.assertEqual(
                tree.get_supmodule_repository_from_path(tree.submodules[name].path),
                name,
            )

    @classmethod
    def setUpClass(cls):
        cls.token = {"token": "token"}
        cls.submodule_1 = "sub-1-repo"
        cls.submodule_2 = "sub-2-repo"
        cls.tree = {
            "owner": "owner",
            "repository": "repository",
            "branch": "branch",
            "submodules": {
                cls.submodule_1: {
                    "owner": "sub-1-owner",
                    "branch": "sub-1-branch",
                    "path": "sub-1-path",
                },
                cls.submodule_2: {},
            },
        }
        # The check tree contains the defaults as well
        cls.check_tree = deepcopy(cls.tree)
        cls.check_tree["submodules"][cls.submodule_2] = {
            # The owner of the parent repository
            "owner": "owner",
            "branch": config._DEFAULT_BRANCH,
            "path": cls.submodule_2,
        }
        cls.full = deepcopy(cls.tree)
        cls.full.update(cls.token)

    def test_get_tree_from_environment(self):
        # Full config
        self._set_environment(self.tree)
        tree = config._get_tree_from_environment()
        self._assert_tree_valid(tree, self.check_tree)

        # No owner configured
        env_config = deepcopy(self.tree)
        del env_config["owner"]
        self._set_environment(env_config)
        tree = config._get_tree_from_environment()
        self.assertIsNone(tree)

        # No repository configured
        env_config = deepcopy(self.tree)
        del env_config["repository"]
        self._set_environment(env_config)
        tree = config._get_tree_from_environment()
        self.assertIsNone(tree)

        # No branch is configured -> check for default branch
        env_config = deepcopy(self.tree)
        del env_config["branch"]
        self._set_environment(env_config)
        tree = config._get_tree_from_environment()
        self.assertEqual(tree.parent.branch, config._DEFAULT_BRANCH)

        # No submodules config provided
        env_config = deepcopy(self.tree)
        del env_config["submodules"]
        self._set_environment(env_config)
        tree = config._get_tree_from_environment()
        self.assertIsNone(tree)

        # Only submodule names configured -> expect defaults
        env_config = deepcopy(self.tree)
        env_config["submodules"][self.submodule_1] = {}
        check_env_config = deepcopy(self.check_tree)
        check_env_config["submodules"][self.submodule_1] = {
            "owner": env_config["owner"],
            "branch": config._DEFAULT_BRANCH,
            "path": self.submodule_1,
        }
        self._set_environment(env_config)
        tree = config._get_tree_from_environment()
        self._assert_tree_valid(tree, check_env_config)

        # Only a single submodule without any attached config configured
        env_config = deepcopy(self.tree)
        env_config["submodules"] = self.submodule_1
        check_env_config = deepcopy(self.check_tree)
        check_env_config["submodules"][self.submodule_1] = {
            "owner": env_config["owner"],
            "branch": config._DEFAULT_BRANCH,
            "path": self.submodule_1,
        }
        del check_env_config["submodules"][self.submodule_2]
        self._set_environment(env_config)
        tree = config._get_tree_from_environment()
        self._assert_tree_valid(tree, check_env_config)

    def test_get_config_from_config_file(self):
        for write_yaml in (False, True):
            with self.subTest(write_yaml=write_yaml):
                self._test_get_config_from_config_file(write_yaml)

    def _test_get_config_from_config_file(self, write_yaml):
        # Invalid config file
        self._clear_environment()
        with self.assertRaises(FileNotFoundError):
            config._get_tree_from_config_file("missing_file")

        # Empty config file
        self._clear_environment()
        file_path = self._get_config_file({}, write_yaml=write_yaml)
        with self.assertRaises(RuntimeError) as cm:
            config._get_tree_from_config_file(file_path)
        self.assertEqual(
            cm.exception.args[0], f"Invalid config file provided: {file_path}"
        )

        # Full config
        self._clear_environment()
        file_path = self._get_config_file(self.tree, write_yaml=write_yaml)
        tree = config._get_tree_from_config_file(file_path)
        self._assert_tree_valid(tree, self.check_tree)

        # No owner configured
        self._clear_environment()
        env_config = deepcopy(self.tree)
        del env_config["owner"]
        file_path = self._get_config_file(env_config, write_yaml=write_yaml)
        tree = config._get_tree_from_config_file(file_path)
        self.assertIsNone(tree)

        # No repository configured
        self._clear_environment()
        env_config = deepcopy(self.tree)
        del env_config["repository"]
        file_path = self._get_config_file(env_config, write_yaml=write_yaml)
        tree = config._get_tree_from_config_file(file_path)
        self.assertIsNone(tree)

        # No branch is configured -> check for default branch
        self._clear_environment()
        env_config = deepcopy(self.tree)
        del env_config["branch"]
        file_path = self._get_config_file(env_config, write_yaml=write_yaml)
        tree = config._get_tree_from_config_file(file_path)
        self.assertEqual(tree.parent.branch, config._DEFAULT_BRANCH)

        # No submodules config provided
        self._clear_environment()
        env_config = deepcopy(self.tree)
        del env_config["submodules"]
        file_path = self._get_config_file(env_config, write_yaml=write_yaml)
        tree = config._get_tree_from_config_file(file_path)
        self.assertIsNone(tree)

        # Only submodule names configured -> expect defaults
        self._clear_environment()
        env_config = deepcopy(self.tree)
        env_config["submodules"][self.submodule_1] = {}
        check_env_config = deepcopy(self.check_tree)
        check_env_config["submodules"][self.submodule_1] = {
            "owner": env_config["owner"],
            "branch": config._DEFAULT_BRANCH,
            "path": self.submodule_1,
        }
        file_path = self._get_config_file(env_config, write_yaml=write_yaml)
        tree = config._get_tree_from_config_file(file_path)
        self._assert_tree_valid(tree, check_env_config)

        # Only a single submodule without any attached config configured
        self._clear_environment()
        env_config = deepcopy(self.tree)
        env_config["submodules"] = self.submodule_1
        check_env_config = deepcopy(self.check_tree)
        check_env_config["submodules"][self.submodule_1] = {
            "owner": env_config["owner"],
            "branch": config._DEFAULT_BRANCH,
            "path": self.submodule_1,
        }
        del check_env_config["submodules"][self.submodule_2]
        file_path = self._get_config_file(env_config, write_yaml=write_yaml)
        tree = config._get_tree_from_config_file(file_path)
        self._assert_tree_valid(tree, check_env_config)

    def test_get_config(self):
        # Test no token provided
        self._clear_environment()
        self._set_environment(self.tree)
        with self.assertRaises(RuntimeError) as cm:
            config.get_config(config_file_path=None, token=None)
        self.assertEqual(
            cm.exception.args[0], "No Github personal access token provided"
        )

        # Test that token from parameter is prioritized over environment
        self._set_environment(self.full)
        result = config.get_config(config_file_path=None, token="parameter_token")
        self.assertEqual(result.token, "parameter_token")
        self.assertIsNotNone(result.tree)

        # Test that token from parameter is prioritized over config
        #  file
        self._clear_environment()
        file_path = self._get_config_file(self.tree, write_yaml=True)
        result = config.get_config(config_file_path=file_path, token="parameter_token")
        self.assertEqual(result.token, "parameter_token")
        self.assertIsNotNone(result.tree)

        # Test that token from environment is prioritized over config
        #  file
        env_config = deepcopy(self.full)
        env_config["token"] = "env_token"
        self._set_environment(env_config)
        file_path = self._get_config_file(self.tree, write_yaml=True)
        result = config.get_config(config_file_path=file_path, token=None)
        self.assertEqual(result.token, "env_token")
        self.assertIsNotNone(result.tree)

        # Test tree from environment prioritized over config file
        env_config = deepcopy(self.full)
        env_config["owner"] = "env_owner"
        env_config["submodules"][self.submodule_1]["owner"] = "env_owner"
        self._set_environment(env_config)
        file_path = self._get_config_file(self.tree, write_yaml=True)
        result = config.get_config(config_file_path=file_path, token=None)
        self.assertIsNotNone(result.token)
        self.assertEqual(result.tree.parent.owner, "env_owner")
        self.assertEqual(result.tree.submodules[self.submodule_1].owner, "env_owner")

        # Test no tree provided
        self._set_environment(self.token)
        with self.assertRaises(RuntimeError) as cm:
            config.get_config(config_file_path=None, token=None)
        self.assertEqual(cm.exception.args[0], "No repository tree provided")

        # Test file doesn't exist
        with self.assertRaises(FileNotFoundError) as cm:
            config.get_config(config_file_path="missing_path/config.yaml", token=None)
        self.assertEqual(
            cm.exception.args[0],
            f"Config file 'missing_path/config.yaml' doesn't exist",
        )

        # Test token and tree provided by environment
        env_config = deepcopy(self.full)
        env_config["token"] = "env_token"
        env_config["owner"] = "env_owner"
        self._set_environment(env_config)
        file_path = self._get_config_file(self.tree, write_yaml=True)
        result = config.get_config(config_file_path=file_path, token=None)
        self.assertEqual(result.token, "env_token")
        self.assertEqual(result.tree.parent.owner, "env_owner")

        # Test token and tree provided by config file
        self._clear_environment()
        file_path = self._get_config_file(self.full, write_yaml=True)
        result = config.get_config(config_file_path=file_path, token=None)
        self.assertEqual(result.token, "token")
        self.assertEqual(result.tree.parent.owner, "owner")


if __name__ == "__main__":
    unittest.main()
