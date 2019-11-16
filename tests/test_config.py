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
    def _get_config_file(config, *, write_yaml=True):
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
        cls.check_tree = cls.tree.copy()
        cls.check_tree["submodules"][cls.submodule_2] = {
            # The owner of the parent repository
            "owner": "owner",
            "branch": "master",
            "path": cls.submodule_2,
        }
        cls.full = cls.tree.copy()
        cls.full.update(cls.token)

    def test_get_config_from_environment(self):
        # No config provided in the environment
        self._clear_environment()
        token, tree = config._get_config_from_environment()
        self.assertIsNone(token)
        self.assertIsNone(tree)

        # Token only provided by environment
        self._set_environment(self.token)
        token, tree = config._get_config_from_environment()
        self.assertEqual(token, "token")
        self.assertIsNone(tree)

        # Tree only provided by environment
        self._set_environment(self.tree)
        token, tree = config._get_config_from_environment()
        self.assertIsNone(token)
        self._assert_tree_valid(tree, self.check_tree)

        # Token and tree provided by environment
        self._set_environment(self.full)
        token, tree = config._get_config_from_environment()
        self.assertIsNotNone(token)
        self.assertIsNotNone(tree)

        # Token and tree provided by environment, with default parent
        #  branch
        config_dict = self.full.copy()
        del config_dict["branch"]
        self._set_environment(config_dict)
        token, tree = config._get_config_from_environment()
        self.assertIsNotNone(token)
        self.assertIsNotNone(tree)

        # No submodule config provided
        self._set_environment(self.full)
        os.environ["GITSUP_SUBMODULES"] = ""
        with self.assertRaises(RuntimeError) as cm:
            config._get_config_from_environment()
        self.assertEqual(
            cm.exception.args[0],
            f"No submodule configuration found for parent repository "
            f"'owner/repository' in environment. The repository and "
            f"submodules must be configured fully in either the "
            f"environment or the config file",
        )

    def test_get_config_from_yaml_config_file(self):
        # No config
        self._clear_environment()
        with self.assertRaises(FileNotFoundError):
            config._get_config_from_config_file("missing_file")

        # Empty config
        self._clear_environment()
        file_path = self._get_config_file({}, write_yaml=True)
        with self.assertRaises(RuntimeError) as cm:
            config._get_config_from_config_file(file_path)
        self.assertEqual(
            cm.exception.args[0], f"Invalid config file provided: {file_path}"
        )

        # Token only
        self._clear_environment()
        file_path = self._get_config_file(self.token, write_yaml=True)
        token, tree = config._get_config_from_config_file(file_path)
        self.assertEqual(token, "token")
        self.assertIsNone(tree)

        # Tree only
        self._clear_environment()
        file_path = self._get_config_file(self.tree, write_yaml=True)
        token, tree = config._get_config_from_config_file(file_path)
        self.assertIsNone(token)
        self._assert_tree_valid(tree, self.check_tree)

        # Token and tree
        self._clear_environment()
        file_path = self._get_config_file(self.full, write_yaml=True)
        token, tree = config._get_config_from_config_file(file_path)
        self.assertIsNotNone(token)
        self.assertIsNotNone(tree)

        # No submodule config provided
        self._clear_environment()
        config_dict = self.full.copy()
        config_dict["submodules"] = {}
        file_path = self._get_config_file(config_dict, write_yaml=True)
        with self.assertRaises(RuntimeError) as cm:
            config._get_config_from_config_file(file_path)
        self.assertEqual(
            cm.exception.args[0],
            f"No submodule configuration found for parent repository "
            f"'owner/repository' in environment. The repository and "
            f"submodules must be configured fully in either the "
            f"environment or the config file",
        )

    def test_get_config_from_json_config_file(self):
        # No config
        self._clear_environment()
        with self.assertRaises(FileNotFoundError):
            config._get_config_from_config_file("missing_file")

        # Empty config
        self._clear_environment()
        file_path = self._get_config_file({}, write_yaml=False)
        with self.assertRaises(RuntimeError) as cm:
            config._get_config_from_config_file(file_path)
        self.assertEqual(
            cm.exception.args[0], f"Invalid config file provided: {file_path}"
        )

        # Token only
        self._clear_environment()
        file_path = self._get_config_file(self.token, write_yaml=False)
        token, tree = config._get_config_from_config_file(file_path)
        self.assertEqual(token, "token")
        self.assertIsNone(tree)

        # Tree only
        self._clear_environment()
        file_path = self._get_config_file(self.tree, write_yaml=False)
        token, tree = config._get_config_from_config_file(file_path)
        self.assertIsNone(token)
        self._assert_tree_valid(tree, self.check_tree)

        # Token and tree
        self._clear_environment()
        file_path = self._get_config_file(self.full, write_yaml=False)
        token, tree = config._get_config_from_config_file(file_path)
        self.assertIsNotNone(token)
        self.assertIsNotNone(tree)

        # No submodule config provided
        self._clear_environment()
        config_dict = self.full.copy()
        config_dict["submodules"] = {}
        file_path = self._get_config_file(config_dict, write_yaml=False)
        with self.assertRaises(RuntimeError) as cm:
            config._get_config_from_config_file(file_path)
        self.assertEqual(
            cm.exception.args[0],
            f"No submodule configuration found for parent repository "
            f"'owner/repository' in environment. The repository and "
            f"submodules must be configured fully in either the "
            f"environment or the config file",
        )

    def test_get_config(self):
        # Test no config file provided, get config from env
        self._set_environment(self.full)
        result = config.get_config(None)
        self.assertIsNotNone(result.token)
        self.assertIsNotNone(result.tree)

        # Test token and tree from config
        self._clear_environment()
        file_path = self._get_config_file(self.full)
        result = config.get_config(file_path)
        self.assertIsNotNone(result.token)
        self.assertIsNotNone(result.tree)

        # Test token from env, tree from config
        self._set_environment(self.token)
        file_path = self._get_config_file(self.tree)
        result = config.get_config(file_path)
        self.assertIsNotNone(result.token)
        self.assertIsNotNone(result.tree)

        # Test token from config, tree from env
        self._set_environment(self.tree)
        file_path = self._get_config_file(self.token)
        result = config.get_config(file_path)
        self.assertIsNotNone(result.token)
        self.assertIsNotNone(result.tree)

        # Test token missing
        self._set_environment(self.tree)
        with self.assertRaises(RuntimeError) as cm:
            config.get_config(None)
        self.assertEqual(
            cm.exception.args[0], "No Github personal access token provided"
        )

        # Test tree missing
        self._set_environment(self.token)
        with self.assertRaises(RuntimeError) as cm:
            config.get_config(None)
        self.assertEqual(cm.exception.args[0], "No repository tree provided")

        # Test file doesn't exist
        with self.assertRaises(FileNotFoundError) as cm:
            config.get_config("missing_path/config.yaml")
        self.assertEqual(
            cm.exception.args[0],
            f"Config file 'missing_path/config.yaml' doesn't exist",
        )


if __name__ == "__main__":
    unittest.main()
