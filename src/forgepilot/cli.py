"""Small CLI for exercising the Phase 1 tool surface."""

import argparse
import logging
from pathlib import Path

from forgepilot.tools import RepositoryTools


def main() -> int:
    parser = argparse.ArgumentParser(prog="forgepilot")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--verbose", action="store_true")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("files")
    for action in ("read", "write"):
        command = sub.add_parser(action)
        command.add_argument("path")
        if action == "write":
            command.add_argument("content")
    git = sub.add_parser("git")
    git.add_argument("args", nargs="+")
    run = sub.add_parser("run")
    run.add_argument("argv", nargs=argparse.REMAINDER)
    tests = sub.add_parser("test")
    tests.add_argument("args", nargs=argparse.REMAINDER)
    sub.add_parser("patch")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    tools = RepositoryTools(args.repo)
    try:
        if args.action == "files":
            print("\n".join(tools.list_files()))
        elif args.action == "read":
            print(tools.read_file(args.path), end="")
        elif args.action == "write":
            tools.write_file(args.path, args.content)
        else:
            result = {"git": lambda: tools.git(*args.args),
                      "run": lambda: tools.run(args.argv),
                      "test": lambda: tools.pytest(*args.args),
                      "patch": lambda: None}[args.action]()
            if args.action == "patch":
                print(tools.patch(), end="")
            else:
                print(result.stdout, end="")
                print(result.stderr, end="", file=__import__("sys").stderr)
                return result.returncode
    except (ValueError, OSError, RuntimeError) as exc:
        logging.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
