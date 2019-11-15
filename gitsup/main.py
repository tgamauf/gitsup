import argparse
import sys

from . import __version__, Updater


def main():
    parser = argparse.ArgumentParser(
        description="Git submodule autoupdater"
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version="%(prog)s {version}".format(version=__version__),
    )
    parser.add_argument("-c", "--config", help="Config file path in YAML/JSON syntax")
    args = parser.parse_args()

    try:
        updater = Updater(config_file_path=args.config)
        updater()
    except RuntimeError as e:
        print(f"Failed to update git project: {e}", file=sys.stderr)
        sys.exit(1)
