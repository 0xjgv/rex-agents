"""Add and remove only this project's configuration entries."""
import os
from pathlib import Path
import shlex
import shutil
import time

from .core import CLI, ROOT, Error, atomic, read

# SessionStart records the pane for drivers whose tool shells lose REX_*; the rest alert on
# prompts that block a launched worker. Codex has no hook for its model's questions.
EVENTS = {"claude-code": {"SessionStart": None, "PreToolUse": "AskUserQuestion", "PermissionRequest": None},
          "codex": {"SessionStart": None, "PermissionRequest": None}}
# Earlier versions installed Rex palette actions through this line and module.
LEGACY_MARKER = 'require("rex_agents") -- rex-agents managed\n'


def paths(home):
    return {
        "claude-code": Path(os.environ.get("CLAUDE_CONFIG_DIR", str(home/".claude")))/"settings.json",
        "codex": Path(os.environ.get("CODEX_HOME", str(home/".codex")))/"hooks.json",
    }


def hook_command(kind, event):
    return shlex.join([str(CLI), "_hook", kind, event])


def edit_hooks(document, kind, remove=False):
    hooks = document.setdefault("hooks", {})
    ours = shlex.join([str(CLI), "_hook"]) + " "
    # Drop every entry of ours, including events earlier versions registered.
    for event in list(hooks):
        groups = []
        for group in hooks[event]:
            kept = [h for h in group.get("hooks", []) if not str(h.get("command", "")).startswith(ours)]
            if kept:
                groups.append(dict(group, hooks=kept))
        if groups:
            hooks[event] = groups
        else:
            hooks.pop(event)
    if not remove:
        for event, matcher in EVENTS[kind].items():
            group = {"hooks": [{"type": "command", "command": hook_command(kind, event), "timeout": 15}]}
            hooks.setdefault(event, []).append({"matcher": matcher, **group} if matcher else group)
    if not hooks:
        document.pop("hooks", None)
    return document


def state_path():
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share")))/"rex-agents/install.json"


def installed():
    return state_path().is_file()


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
    if not remove:
        for path, target in links.items():
            if path.exists() or path.is_symlink():
                if not path.is_symlink() or path.resolve() != target.resolve():
                    raise Error(f"Refusing to replace unrelated path: {path}")
    # Read current files so additions made after installation survive.
    documents = {kind: read(path, {}) for kind, path in paths(home).items()}
    if not remove and not manifest:
        backup = state/"backups"/str(time.time_ns())
        for path in [init, *paths(home).values()]:
            if path.exists():
                destination = backup/path.relative_to(home) if path.is_relative_to(home) else backup/path.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        manifest = {"backup": str(backup)}
        atomic(manifest_path, manifest)
    for kind, path in paths(home).items():
        if path.exists() or not remove:
            atomic(path, edit_hooks(documents[kind], kind, remove))
    if init.exists() and LEGACY_MARKER in init.read_text():
        atomic(init, init.read_text().replace(LEGACY_MARKER, ""))
    if module.exists() and module.read_text().startswith("-- Managed by rex-agents.\n"):
        module.unlink()
    if remove:
        for path, target in links.items():
            if path.is_symlink() and path.resolve() == target.resolve():
                path.unlink()
        cache = Path(os.environ.get("XDG_CACHE_HOME", str(home/".cache")))/"rex-agents"
        if cache.exists():
            shutil.rmtree(cache)
        manifest_path.unlink(missing_ok=True)
        return {"removed": True, "reason": "unchanged", "active_sessions": "unchanged"}
    for path, target in links.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_symlink():
            path.symlink_to(target, target_is_directory=target.is_dir())
    return {"installed": True, **manifest}
