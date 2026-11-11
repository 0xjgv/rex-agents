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
    launch.add_argument("--name", required=True)
    launch.add_argument("--cwd", default=".", help="Worker directory; defaults to the current one")
    launch.add_argument("--task-file")
    launch.add_argument("--model", required=True, help="claude-* runs Claude Code; gpt-* runs Codex")
    launch.add_argument("--effort", help="Native worker effort; omitted values inherit")
    launch.add_argument("--permission-mode", metavar="MODE", help="Claude Code permission mode; omitted values inherit")
    launch.add_argument("--env", action="append", metavar="KEY=VALUE", help="Set a worker variable; repeatable")
    where = launch.add_mutually_exclusive_group()
    where.add_argument("--tab", action="store_true", help="Open the worker in a new tab of the driver's session")
    where.add_argument("--new-session", nargs="?", const=True, default=False, metavar="LABEL",
                       help="Open the worker in a tab of the Rex session LABEL, created if needed; LABEL defaults to the worker's name")
    where.add_argument("--with", dest="beside", metavar="WORKER", help="Open the worker beside your worker WORKER, in its tab")
    cleanup = commands.add_parser("cleanup", help="Close workers owned by this native driver, including unfinished work")
    cleanup.add_argument("--name", help="Close only this owned worker")
    commands.add_parser("status", help="List this driver's live workers")
    wait = commands.add_parser("wait", help="Block until one of this driver's workers ends, then print how")
    wait.add_argument("--name", required=True)
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
            result = app.launch(args.name, args.cwd, args.model, task, effort=args.effort, tab=args.tab,
                                beside=args.beside, new_session=args.new_session, env=args.env,
                                permission_mode=args.permission_mode)
        elif args.command == "cleanup":
            result = app.cleanup(name=args.name)
            print(json.dumps(result, indent=2))
            return int(bool(result["uncertain"]))
        elif args.command == "status":
            result = app.status()
        elif args.command == "wait":
            result = app.wait(args.name)
        elif args.command in ("install", "uninstall"):
            result = install(remove=args.command == "uninstall")
        elif args.command == "_hook":
            if not installed():
                return 0
            result = app.hook(args.kind, args.event, decode(sys.stdin.read()))
        if result is not None:
            print(json.dumps(result, indent=2))
        return 0
    except (Error, OSError, ValueError) as exc:
        print(f"rex-agents: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
