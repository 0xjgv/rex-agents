"""Command-line entry points."""
import argparse
import json
from pathlib import Path
import sys

from .core import Error, Integration, decode
from .install import install, installed


def parser():
    p = argparse.ArgumentParser(description="Launch interactive Claude Code and Codex workers into Rex panes, and close the ones you own.")
    for option in ("server", "session", "block"):
        p.add_argument("--" + option)
    commands = p.add_subparsers(dest="command", required=True)
    launch = commands.add_parser("launch")
    launch.add_argument("kind", choices=("claude", "codex"))
    launch.add_argument("--name", required=True)
    launch.add_argument("--cwd", required=True)
    launch.add_argument("--task-file")
    launch.add_argument("--model", help="Native worker model; omitted values inherit")
    launch.add_argument("--effort", help="Native worker effort; omitted values inherit")
    commands.add_parser("cleanup", help="Close workers owned by this native driver, including unfinished work")
    commands.add_parser("install")
    commands.add_parser("uninstall")
    hook = commands.add_parser("_hook", help=argparse.SUPPRESS)
    hook.add_argument("kind", choices=("claude-code", "codex"))
    hook.add_argument("event")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    app = Integration(**{k: getattr(args, k) for k in ("server", "session", "block")})
    try:
        result = None
        if args.command == "launch":
            task = Path(args.task_file).read_text() if args.task_file else None
            result = app.launch(args.kind, args.name, args.cwd, task, model=args.model, effort=args.effort)
        elif args.command == "cleanup":
            result = app.cleanup()
            print(json.dumps(result, indent=2))
            return int(bool(result["uncertain"]))
        elif args.command in ("install", "uninstall"):
            result = install(remove=args.command == "uninstall")
        elif args.command == "_hook":
            if not installed():
                return 0
            app.hook(args.kind, args.event, decode(sys.stdin.read()))
        if result is not None:
            print(json.dumps(result, indent=2))
        return 0
    except (Error, OSError, ValueError) as exc:
        print(f"rex-agents: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
