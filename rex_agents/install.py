"""Add and remove only this project's configuration entries."""
import json
import os
from pathlib import Path
import shlex
import shutil
import time

from .core import CLI, ROOT, Error, atomic, read

MARKER = 'require("rex_agents") -- rex-agents managed\n'
EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop", "SessionEnd")
# Prompts that block a launched worker; Codex has no hook for its model's questions.
BLOCKING = {"claude-code": {"PreToolUse": "AskUserQuestion", "PermissionRequest": None},
            "codex": {"PermissionRequest": None}}


def events(kind):
    return {**dict.fromkeys(EVENTS), **BLOCKING[kind]}


def paths(home):
    return {
        "claude-code": Path(os.environ.get("CLAUDE_CONFIG_DIR", str(home/".claude")))/"settings.json",
        "codex": Path(os.environ.get("CODEX_HOME", str(home/".codex")))/"hooks.json",
    }


def hook_command(kind, event):
    return shlex.join([str(CLI), "_hook", kind, event])


def edit_hooks(document, kind, remove=False):
    hooks = document.setdefault("hooks", {})
    for event, matcher in events(kind).items():
        command = hook_command(kind, event)
        groups = []
        for group in hooks.get(event, []):
            kept = [h for h in group.get("hooks", []) if h.get("command") != command]
            if kept:
                groups.append(dict(group, hooks=kept))
        if not remove:
            group = {"hooks": [{"type": "command", "command": command, "timeout": 3 if event == "SessionEnd" else 15}]}
            groups.append({"matcher": matcher, **group} if matcher else group)
        if groups:
            hooks[event] = groups
        else:
            hooks.pop(event, None)
    if not hooks:
        document.pop("hooks", None)
    return document


def state_path():
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share")))/"rex-agents/install.json"


def installed():
    return state_path().is_file()


def navigation(mode="status"):
    if mode not in ("status", "toggle", "on", "off"):
        raise Error("Navigation mode must be on, off, status, or toggle")
    path = state_path()
    state = read(path, {})
    enabled = state.get("navigation_enabled", False)
    if mode != "status":
        if not state:
            raise Error("Install rex-agents before changing navigation mode")
        enabled = not enabled if mode == "toggle" else mode == "on"
        state["navigation_enabled"] = enabled
        atomic(path, state)
    return {"enabled": enabled, "note": "Rex Remote Control stays unchanged. Enable it in Settings > Rex Server only when you want app navigation."}


def install(home=None, remove=False):
    home = Path(home or Path.home())
    config = Path(os.environ.get("XDG_CONFIG_HOME", str(home/".config")))/"rex"
    init = Path(os.environ.get("REX_CONFIG", str(config/"init.lua")))
    module = init.parent/"rex_agents.lua"
    state = Path(os.environ.get("XDG_DATA_HOME", str(home/".local/share")))/"rex-agents"
    manifest_path = state/"install.json"
    manifest = read(manifest_path, {})
    links = {home/".local/bin/rex-agents": CLI,
             home/".agents/skills/rex-agents": ROOT/"skill",
             paths(home)["claude-code"].parent/"skills/rex-agents": ROOT/"skill"}
    if remove:
        # Read current files so additions made after installation survive removal.
        for kind, path in paths(home).items():
            if path.exists():
                document = edit_hooks(read(path), kind, True)
                atomic(path, document)
        if init.exists():
            atomic(init, init.read_text().replace(MARKER, ""))
        if module.exists() and module.read_text().startswith("-- Managed by rex-agents.\n"):
            module.unlink()
        for path, target in links.items():
            if path.is_symlink() and path.resolve() == target.resolve():
                path.unlink()
        cache = Path(os.environ.get("XDG_CACHE_HOME", str(home/".cache")))/"rex-agents"
        if cache.exists():
            shutil.rmtree(cache)
        manifest_path.unlink(missing_ok=True)
        return {"removed": True, "reason": "unchanged", "active_sessions": "unchanged"}
    documents = {kind: read(path, {}) for kind, path in paths(home).items()}
    text = init.read_text() if init.exists() else ""
    for path, target in links.items():
        if path.exists() or path.is_symlink():
            if not path.is_symlink() or path.resolve() != target.resolve():
                raise Error(f"Refusing to replace unrelated path: {path}")
    if module.exists() and not module.read_text().startswith("-- Managed by rex-agents.\n"):
        raise Error(f"Refusing to replace unrelated module: {module}")
    if not manifest:
        backup = state/"backups"/str(time.time_ns())
        for path in [init, *paths(home).values()]:
            if path.exists():
                destination = backup/path.relative_to(home) if path.is_relative_to(home) else backup/path.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        manifest = {"backup": str(backup)}
        atomic(manifest_path, manifest)
    for kind, path in paths(home).items():
        atomic(path, edit_hooks(documents[kind], kind))
    for path, target in links.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_symlink():
            path.symlink_to(target, target_is_directory=target.is_dir())
    lua = (ROOT/"lua/rex_agents.lua").read_text().replace("@CLI@", json.dumps(str(CLI))).replace("@REX@", json.dumps(shutil.which("rex") or "rex")).replace("@PATH@", json.dumps(os.environ.get("PATH", os.defpath)))
    atomic(module, lua)
    if MARKER not in text:
        atomic(init, text + ("\n" if text and not text.endswith("\n") else "") + MARKER)
    return {"installed": True, "config": str(init), **manifest}
