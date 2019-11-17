from http import HTTPStatus
import json
import os
import requests
import requests_mock
import unittest
from unittest.mock import MagicMock, patch

import gitsup.update as update


class TestUpdate(unittest.TestCase):
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

    @classmethod
    def setUpClass(cls):
        cls.token = "token"
        cls.owner = "owner"
        cls.repository = "repository"
        cls.branch = "branch"
        cls.submodule_1 = "sub-1-repo"
        cls.submodule_1_owner = "sub-1-owner"
        cls.submodule_1_branch = "sub-1-branch"
        cls.submodule_1_path = "sub-1-path"
        cls.submodule_2 = "sub-2-repo"
        cls.submodule_2_owner = cls.owner
        cls.submodule_2_branch = "master"
        cls.submodule_2_path = cls.submodule_2
        cls.submodule_3 = "sub-3-repo"
        cls.submodule_3_owner = cls.owner
        cls.submodule_3_branch = "master"
        cls.submodule_3_path = cls.submodule_3
        cls.config = {
            "token": cls.token,
            "owner": cls.owner,
            "repository": cls.repository,
            "branch": cls.branch,
            "submodules": {
                cls.submodule_1: {
                    "owner": cls.submodule_1_owner,
                    "branch": cls.submodule_1_branch,
                    "path": cls.submodule_1_path,
                },
                # These are empty as we use default values here
                cls.submodule_2: {},
                cls.submodule_3: {},
            },
        }
        cls.parent_url_template = update.URL_TEMPLATE.format(
            owner=cls.owner, repository=cls.repository, url="{url}"
        )
        cls.submodule_1_url_template = update.URL_TEMPLATE.format(
            owner=cls.submodule_1_owner, repository=cls.submodule_1, url="{url}"
        )
        cls.submodule_2_url_template = update.URL_TEMPLATE.format(
            owner=cls.submodule_2_owner, repository=cls.submodule_2, url="{url}"
        )

    def _assert_header_valid(self, headers):
        # Github API v3 accept header
        self.assertIn("Accept", headers.keys())
        self.assertEqual(headers["Accept"], "application/vnd.github.v3+json")
        # Auth header
        self.assertIn("Authorization", headers.keys())
        self.assertEqual(headers["Authorization"], f"token {self.token}")

    def test_update_changed_parameter(self):
        # Test if the config file is handed over to config.
        # We interrupt the test when the get_config mock is called, as
        #  we aren't interested in running the rest
        with patch("gitsup.update.get_config") as mock_config:
            mock_config.side_effect = RuntimeError("interrupd")
            with self.assertRaises(RuntimeError):
                update.update_git_submodules(config_file_path="config-file-path")
            mock_config.assert_called_once_with(
                config_file_path="config-file-path", token=None
            )

        # Test if the token is handed over to config.
        # We interrupt the test when the get_config mock is called, as
        #  we aren't interested in running the rest
        with patch("gitsup.update.get_config") as mock_config:
            mock_config.side_effect = RuntimeError("interrupd")
            with self.assertRaises(RuntimeError):
                update.update_git_submodules(token="token")
            mock_config.assert_called_once_with(config_file_path=None, token="token")

    @requests_mock.mock()
    def test_update_changed_success(self, mock_requests):
        # Test:
        # - submodules 1 & 2 are configured and exist
        # - submodule 1 has been changed, submodule 2 is the same
        # - submodule 3 is configured, but doesn't exist
        # - submodule 4 isn't configured, but exists
        # -> the test must pass
        current_parent_oid = "current-parent_oid"
        current_submodule_1_oid = "current-sub-1-oid"
        current_submodule_2_oid = "current-sub-2-oid"
        new_submodule_1_oid = "new-sub-1-oid"
        tree_oid = "tree-oid"
        tree_commit = "tree-commit-oid"

        # Prepare mocks
        # _get_oid for parent
        mock_requests.get(
            self.parent_url_template.format(url=f"branches/{self.branch}"),
            json={"commit": {"sha": current_parent_oid}},
        )
        # _get_oid for submodule 1
        mock_requests.get(
            self.submodule_1_url_template.format(
                url=f"branches/{self.submodule_1_branch}"
            ),
            json={"commit": {"sha": new_submodule_1_oid}},
        )
        # _get_oid for submodule 2
        mock_requests.get(
            self.submodule_2_url_template.format(
                url=f"branches/{self.submodule_2_branch}"
            ),
            json={"commit": {"sha": current_submodule_2_oid}},
        )
        # _get_current_submodule_oids
        mock_requests.get(
            self.parent_url_template.format(url=f"git/trees/{current_parent_oid}"),
            json={
                "tree": [
                    {"path": "README.md", "type": "blob", "sha": "readme-oid"},
                    {
                        "path": self.submodule_1_path,
                        "type": "commit",
                        "sha": current_submodule_1_oid,
                    },
                    {
                        "path": self.submodule_2_path,
                        "type": "commit",
                        "sha": current_submodule_2_oid,
                    },
                    {"path": "sub-4-path", "type": "commit", "sha": "sub-4-oid"},
                ]
            },
        )
        # _create_updated_tree
        mock_requests.post(
            self.parent_url_template.format(url=f"git/trees"), json={"sha": tree_oid}
        )
        # _commit_tree
        mock_requests.post(
            self.parent_url_template.format(url=f"git/commits"),
            json={"sha": tree_commit},
        )
        # _commit_oid
        mock_requests.patch(
            self.parent_url_template.format(url=f"git/refs/heads/{self.branch}"),
            json={"text": "something"},
        )

        self._set_environment(self.config)
        update.update_git_submodules()

        self.assertEqual(mock_requests.call_count, 7)
        self._assert_header_valid(mock_requests.last_request._request.headers)
        history = mock_requests.request_history

        # _create_updated_tree
        self.assertDictEqual(
            history[4].json(),
            {
                "base_tree": current_parent_oid,
                "tree": [
                    {
                        "path": self.submodule_1_path,
                        "mode": "160000",
                        "type": "commit",
                        "sha": new_submodule_1_oid,
                    }
                ],
            },
        )
        # _commit_tree
        self.assertDictEqual(
            history[5].json(),
            {
                "message": (
                    "Update submodules in 'branch' to latest commits\n\n"
                    "* Update submodule 'sub-1-repo' to HEAD of branch "
                    "'sub-1-branch':\n\tnew-sub-1-oid"
                ),
                "tree": "tree-oid",
                "parents": ["current-parent_oid"],
            },
        )
        # _commit_oid
        self.assertDictEqual(history[6].json(), {"sha": "tree-commit-oid"})

    @requests_mock.mock()
    def test_unchanged_success(self, mock_requests):
        # Test:
        # - submodules 1 & 2 are configured and exist
        # - none of the submodules changed
        # -> the test must pass
        current_parent_oid = "current-parent_oid"
        current_submodule_1_oid = "current-sub-1-oid"
        current_submodule_2_oid = "current-sub-2-oid"

        # Prepare mocks
        # _get_oid for parent
        mock_requests.get(
            self.parent_url_template.format(url=f"branches/{self.branch}"),
            json={"commit": {"sha": current_parent_oid}},
        )
        # _get_oid for submodule 1
        mock_requests.get(
            self.submodule_1_url_template.format(
                url=f"branches/{self.submodule_1_branch}"
            ),
            json={"commit": {"sha": current_submodule_1_oid}},
        )
        # _get_oid for submodule 2
        mock_requests.get(
            self.submodule_2_url_template.format(
                url=f"branches/{self.submodule_2_branch}"
            ),
            json={"commit": {"sha": current_submodule_2_oid}},
        )
        # _get_current_submodule_oids
        mock_requests.get(
            self.parent_url_template.format(url=f"git/trees/{current_parent_oid}"),
            json={
                "tree": [
                    {"path": "README.md", "type": "blob", "sha": "readme-oid"},
                    {
                        "path": self.submodule_1_path,
                        "type": "commit",
                        "sha": current_submodule_1_oid,
                    },
                    {
                        "path": self.submodule_2_path,
                        "type": "commit",
                        "sha": current_submodule_2_oid,
                    },
                ]
            },
        )

        config_dict = self.config.copy()
        del config_dict["submodules"][self.submodule_3]
        self._set_environment(self.config)
        update.update_git_submodules()

        self.assertEqual(mock_requests.call_count, 4)

    def test_request(self):
        # Test connection timeout
        mock_request_fn = MagicMock()
        mock_request_fn.side_effect = requests.ConnectionError("something happened")
        with self.assertRaises(ConnectionError) as cm:
            update._request(f"test", mock_request_fn, test="test")
        self.assertEqual(
            cm.exception.args[0], f"test: failed to connect to API - something happened"
        )
        mock_request_fn.assert_called_once_with(test="test")

        # Test invalid response
        mock_json = MagicMock()
        mock_json.side_effect = json.JSONDecodeError("JSON failed", "doc", 0)
        mock_response = MagicMock(autospec=requests.Response)
        mock_response.json = mock_json
        mock_response.text = "some text"
        mock_response.status_code = HTTPStatus.NOT_FOUND
        mock_request_fn = MagicMock()
        mock_request_fn.return_value = mock_response
        with self.assertRaises(RuntimeError) as cm:
            update._request(f"test", mock_request_fn, test="test")
        self.assertEqual(
            cm.exception.args[0],
            f"test: could not decode API response - some text "
            f"({HTTPStatus.NOT_FOUND})",
        )
        mock_request_fn.assert_called_once_with(test="test")

        # Invalid token
        with requests_mock.mock() as mock_request:
            kwargs = {"url": "mock://some.url", "json": {"test": "value"}}
            mock_request.get(
                kwargs["url"],
                status_code=HTTPStatus.UNAUTHORIZED,
                json={"message": "Bad credentials"},
            )
            with self.assertRaises(PermissionError) as cm:
                update._request(error=f"test", fn=requests.get, **kwargs)
            self.assertEqual(
                cm.exception.args[0],
                "test: invalid Github personal access token provided",
            )

        # Test invalid key permissions, repository doesn't exist
        with requests_mock.mock() as mock_request:
            kwargs = {"url": "mock://some.url", "json": {"test": "value"}}
            mock_request.get(
                kwargs["url"],
                status_code=HTTPStatus.NOT_FOUND,
                json={"message": "Not found"},
            )
            with self.assertRaises(RuntimeError) as cm:
                update._request(error=f"test", fn=requests.get, **kwargs)
            self.assertEqual(
                cm.exception.args[0],
                "test: couldn't access repository. Please check if the "
                "owner and repository exist and the Github personal "
                "access token has permissions 'repo' assigned",
            )

        # Test branch doesn't exist
        with requests_mock.mock() as mock_request:
            kwargs = {"url": "mock://some.url", "json": {"test": "value"}}
            mock_request.get(
                kwargs["url"],
                status_code=HTTPStatus.NOT_FOUND,
                json={"message": "Branch not found"},
            )
            with self.assertRaises(RuntimeError) as cm:
                update._request(error=f"test", fn=requests.get, **kwargs)
            self.assertEqual(cm.exception.args[0], "test: invalid branch")

        # Test unknown 404
        with requests_mock.mock() as mock_request:
            kwargs = {"url": "mock://some.url", "json": {"test": "value"}}
            mock_request.get(
                kwargs["url"],
                status_code=HTTPStatus.NOT_FOUND,
                json={"message": "unknown"},
            )
            with self.assertRaises(RuntimeError) as cm:
                update._request(error=f"test", fn=requests.get, **kwargs)
            self.assertEqual(
                cm.exception.args[0], f"test: unknown ({HTTPStatus.NOT_FOUND})"
            )

        # Test other http error code
        with requests_mock.mock() as mock_request:
            kwargs = {"url": "mock://some.url", "json": {"test": "value"}}
            mock_request.get(
                kwargs["url"],
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                text="error",
            )
            with self.assertRaises(RuntimeError) as cm:
                update._request(error=f"test", fn=requests.get, **kwargs)
            self.assertEqual(
                cm.exception.args[0],
                f"test: error ({HTTPStatus.INTERNAL_SERVER_ERROR})",
            )


if __name__ == "__main__":
    unittest.main()
