import argparse
import sys

from . import __version__, update_git_submodules


def main():
    parser = argparse.ArgumentParser(description="Git submodule autoupdater")
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version="%(prog)s {version}".format(version=__version__),
    )
    parser.add_argument("-c", "--config", help="Config file path in YAML/JSON syntax")
    parser.add_argument("-t", "--token", help="Github API token")
    args = parser.parse_args()

    try:
        update_git_submodules(config_file_path=args.config, token=args.token)
    except RuntimeError as e:
        print(f"Failed to update git project: {e}", file=sys.stderr)
        sys.exit(1)
