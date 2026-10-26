"""Command-line and short Rex action entry points."""
import argparse
import json
import os
from pathlib import Path
import sys

from .core import Error, Integration, decode, run
from .install import EVENTS, hook_command, install, installed, navigation, paths


def display(data):
    for row in data["sessions"]:
        mapping = row.get("rex")
        location = mapping and mapping.get("location")
        pane = location["block"] if location else "unavailable"
        print(f"{row['address']}  {row['machine']}  {row['status']}  {row.get('repo') or row.get('cwd', '')}  {pane}")
        if row.get("doing"):
            print(f"  {row['doing']}")
    for warning in data.get("warnings", []):
        print(f"Warning: {warning}", file=sys.stderr)


def doctor(app):
    checks = []
    def check(name, callback):
        try:
            detail = callback()
            checks.append(dict(check=name, ok=True, detail=detail))
        except (Error, OSError) as exc:
            checks.append(dict(check=name, ok=False, detail=str(exc)))
    for executable in ("rex", "claude", "codex"):
        check(executable, lambda executable=executable: run([executable, "version" if executable == "rex" else "--version"]).strip())
    check("Reason API", lambda: app.roster().get("machine"))
    def reason_integrations():
        report = app.reason("doctor").strip()
        missing = [name for name in ("Claude Code", "Codex") if f"{name}: wired up" not in report]
        if missing:
            raise Error("Reason integrations missing: " + ", ".join(missing))
        return report
    check("Reason integrations", reason_integrations)
    def local_hooks():
        if not installed():
            raise Error("Integration is not installed")
        for kind, path in paths(Path.home()).items():
            document = decode(path.read_text())
            for event in EVENTS:
                commands = [hook.get("command") for group in document.get("hooks", {}).get(event, [])
                            for hook in group.get("hooks", [])]
                if hook_command(kind, event) not in commands:
                    raise Error(f"Missing {kind} {event} locator hook")
        return "Locator hooks installed; Codex must trust them through its native UI"
    check("locator hooks", local_hooks)
    check("navigation mode", navigation)
    check("Rex configuration", lambda: decode(app.rex("config", "check", "--json")))
    def actions():
        data = decode(app.rex("actions", "--json"))
        names = {a["name"] for a in data["actions"]}
        expected = {"rex_agents_list", "rex_agents_send", "rex_agents_focus", "rex_agents_launch", "rex_agents_registry", "rex_agents_remote_launch", "rex_agents_navigation"}
        if expected - names:
            raise Error("Missing actions: " + ", ".join(sorted(expected - names)))
        return "all integration actions loaded"
    check("Rex actions", actions)
    check("locator registry", app.registry)
    def workers():
        pending = []
        for path in (app.cache/"launches").glob("*.json"):
            launch = decode(path.read_text())
            if launch.get("failed"):
                continue
            if not launch.get("location"):
                raise Error(f"Uncertain launch {launch['name']}: inspect reservation {path.name}")
            try:
                app.live_location(launch["location"])
            except Error:
                continue
            records = [r for r in app.locators() if r.get("launch") == launch["token"] and not r.get("ended")]
            if not records and not launch.get("has_task", True):
                pending.append(launch["name"] + ": waiting for native session creation or hook trust")
                continue
            if len(records) != 1:
                raise Error(f"Worker {launch['name']} has a pane but no unique native identity; check hook trust and restart/resume")
            app.me(records[0]["kind"], records[0]["native_id"])
        return {"registered": "Other active workers have verified native identities", "pending": pending}
    check("worker registration", workers)
    return checks


def action(app, value, prompt=False):
    operation = value["operation"]
    args = value.get("args", {})
    if operation == "navigation":
        return navigation(args.get("mode", "toggle"))
    if operation == "list":
        display(app.listing())
        return
    if operation in ("send", "focus"):
        target = args.get("target") or (input("Agent address or exact name: ").strip() if prompt else None)
        if not target:
            raise Error("Target required")
        if operation == "focus":
            return app.focus(target)
        message = args.get("message")
        if message is None and prompt:
            print("Message (finish with a line containing only .):")
            lines = []
            while True:
                line = input()
                if line == ".":
                    break
                lines.append(line)
            message = "\n".join(lines)
        if message is None:
            raise Error("Message required")
        output = app.send(target, message, fyi=args.get("fyi", False), reply_to=args.get("reply_to"), human=True)
        return {"output": output}
    if operation == "launch":
        def field(name, label):
            return args.get(name) or (input(label).strip() if prompt else None)
        kind = field("kind", "Agent (claude/codex): ")
        if kind not in ("claude", "codex"):
            raise Error("Agent must be claude or codex")
        return app.launch(kind, field("name", "Worker name: "), field("cwd", "Working directory: "),
                          args.get("task"), args.get("host"),
                          **{key: args[key] for key in ("model", "effort") if key in args})
    raise Error(f"Unknown action: {operation}")


def parser():
    p = argparse.ArgumentParser(description="Discover, message, launch, and focus interactive Rex agents through Reason.")
    for option in ("server", "session", "block", "client"):
        p.add_argument("--" + option)
    commands = p.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--json", action="store_true")
    sending = commands.add_parser("send")
    sending.add_argument("target")
    sending.add_argument("--message-file", required=True)
    sending.add_argument("--fyi", action="store_true")
    sending.add_argument("--reply-to")
    launch = commands.add_parser("launch")
    launch.add_argument("kind", choices=("claude", "codex"))
    launch.add_argument("--name", required=True)
    launch.add_argument("--cwd", required=True)
    launch.add_argument("--task-file")
    launch.add_argument("--host")
    launch.add_argument("--model", help="Native worker model; omitted values inherit (local only)")
    launch.add_argument("--effort", help="Native worker effort; omitted values inherit (local only)")
    commands.add_parser("cleanup", help="Close local workers owned by this native driver, including unfinished work")
    commands.add_parser("focus").add_argument("target")
    commands.add_parser("navigation").add_argument("mode", nargs="?", default="status", choices=("on", "off", "status"))
    commands.add_parser("doctor")
    commands.add_parser("install")
    commands.add_parser("uninstall")
    hook = commands.add_parser("_hook", help=argparse.SUPPRESS)
    hook.add_argument("kind", choices=("claude-code", "codex"))
    hook.add_argument("event")
    commands.add_parser("_registry", help=argparse.SUPPRESS)
    commands.add_parser("_worker", help=argparse.SUPPRESS).add_argument("payload")
    commands.add_parser("_action", help=argparse.SUPPRESS)
    commands.add_parser("_prompt", help=argparse.SUPPRESS).add_argument("payload")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    app = Integration(**{k: getattr(args, k) for k in ("server", "session", "block", "client")})
    try:
        result = None
        if args.command == "list":
            result = app.listing()
            if not args.json:
                display(result)
                return 0
        elif args.command == "send":
            text = Path(args.message_file).read_text()
            print(app.send(args.target, text, fyi=args.fyi, reply_to=args.reply_to), end="")
        elif args.command == "launch":
            task = Path(args.task_file).read_text() if args.task_file else None
            result = app.launch(args.kind, args.name, args.cwd, task, args.host,
                                model=args.model, effort=args.effort)
        elif args.command == "cleanup":
            result = app.cleanup()
            print(json.dumps(result, indent=2))
            return int(bool(result["uncertain"]))
        elif args.command == "navigation":
            result = navigation(args.mode)
        elif args.command == "focus":
            result = app.focus(args.target)
        elif args.command == "doctor":
            result = doctor(app)
            print(json.dumps(result, indent=2))
            return int(any(not c["ok"] for c in result))
        elif args.command in ("install", "uninstall"):
            result = install(remove=args.command == "uninstall")
        elif args.command == "_hook":
            if not installed():
                return 0
            payload = decode(sys.stdin.read())
            app.hook(args.kind, args.event, payload)
        elif args.command == "_registry":
            result = app.registry()
        elif args.command == "_worker":
            app.worker(args.payload)
        elif args.command in ("_action", "_prompt"):
            value = decode(args.payload if args.command == "_prompt" else sys.stdin.read())
            result = action(app, value, args.command == "_prompt")
        if result is not None:
            print(json.dumps(result, indent=2))
        return 0
    except (Error, OSError, ValueError, EOFError) as exc:
        print(f"rex-agents: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
