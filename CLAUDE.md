# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Rex agents launches interactive Claude Code and Codex workers into Rex panes and closes the ones a driver owns. Reason handles discovery and messaging; this project does neither. Python 3.13+ standard library only; no packages, build, or linter. `bin/rex-agents` is a shim that re-execs into `python3.13` when started by an older `python3`, then puts the repo root on `sys.path`. User-facing docs: `ONBOARDING.md` (workflow, troubleshooting), `VERIFICATION.md` (live results and open limits), `skill/SKILL.md` (instructions installed for agents).

## Commands

```sh
python3.13 -m unittest discover -s tests -v   # full suite
./bin/rex-agents --help
```

Install touches live config (`~/.claude/settings.json`, `~/.codex/hooks.json`, `~/.local/bin`, skill links, and removes any legacy Rex `init.lua` line and module). Run it only when the task requires it:

```sh
./bin/rex-agents install && rex config check && rex config reload
```

## Architecture

All code lives in `rex_agents/core.py` (`Integration`), `cli.py` (commands), and `install.py` (hooks and links). Public commands: `launch`, `cleanup`, `install`, `uninstall`. `_hook KIND EVENT` is the internal hook entry point.

**State is the pane label.** Each worker pane is labeled `rex-agents:<owner>:<name>`, where `owner` is `sha256("kind:native_id")[:16]` for an agent driver, or `-` for a human. Rex labels survive title changes and are capped at 128 characters. Panes close when their process exits. `panes()` lists blocks across all sessions, sorted by block ID (UUIDv7, so oldest first). The duplicate-name check, nested-launch guard, ownership, anchoring, and cleanup all read labels. The cache under `~/.cache/rex-agents` holds only `sessions/<owner>.json` locators, `splits/<owner>.json` (last split direction), and `launch.lock`.

**Identity.** `native_identity()` reads `CODEX_THREAD_ID` or `CLAUDE_CODE_SESSION_ID`, fails on conflicts (Codex ID with Claude vars), and returns `None` for a human shell. Identity never comes from cwd, repo, pane title, or display name.

**Hooks.** `install.py` registers `SessionStart` and `PermissionRequest` for both harnesses, plus `PreToolUse` matching `AskUserQuestion` for Claude. `SessionStart` writes the pane locator, because Codex tool shells lack `REX_*` even with `--no-daemon`. `where()` uses that locator when the shell has no `REX_SESSION`/`REX_BLOCK`. Only `PreToolUse` and `PermissionRequest` call `alert()`; events left by earlier installs do nothing. If the hook's own pane carries an owned worker label, `alert()` denies `AskUserQuestion` (printed PreToolUse JSON, `permissionDecision: deny`) with `RELAY`, which tells the worker to send the question to its driver through Reason. Other blocking prompts in worker panes, and questions in human-launched workers, send Reason `send <person> --notify --from kind:id` to the human. Hooks ignore nested agents and subagents (`agent_id`, or cross-harness inherited vars) so they cannot claim a parent's pane.

**Launch.** `Integration.launch` validates name, selectors, cwd, and executable, then takes `launch.lock`. It refuses if the driver pane is an owned worker, or if any pane already carries the name. It then runs `rex split --focus=false --label LABEL -- ARGV`. Workers run `claude --name NAME` or `codex --no-daemon` directly; split panes start with Rex's environment, not the caller's. Owned launches alternate `right`/`below` from `splits/<owner>.json`, anchored on the newest owned pane in the driver's session and tab, else the driver. Human launches split right from the driver. Any split failure is reported as uncertain; the label check refuses a retry while the pane exists. It cannot see a pane that Rex creates after a local timeout, so callers wait and inspect before retrying. Workers start from the absolute path `shutil.which` found, because the pane gets the login shell's environment. The nesting guard checks the explicit block, `REX_BLOCK`, and the locator's block.

`launch(name, cwd, model, task=None, effort=None)` requires a model, and the model picks the harness (`HARNESS`): `claude-*` runs Claude Code, `gpt-*` runs Codex, anything else is refused. Claude gets `--model`/`--effort`, Codex `-m` and `-c model_reasoning_effort=...`. An omitted effort inherits native settings. The skill maps short names (sol, terra, astra, opus, fable, sonnet) to model IDs and has the driver choose the effort.

**Cleanup.** `Integration.cleanup()` requires native identity and closes every pane labeled with the caller's owner, except the driver's own pane. It then re-lists to confirm absence. It prints `closed`, `gone`, `uncertain` JSON and exits 1 if anything is uncertain. Complete cleanup resets split alternation. Never add Stop or SessionEnd auto cleanup.

`run()` raises `CommandError` when a subprocess exits nonzero and plain `Error` on timeout or `OSError`. A nonzero exit alone does not prove Rex created nothing.

## Install mechanics

- CLI and skill are **symlinks** into the repo, so Python edits take effect immediately.
- Hook commands embed the absolute `bin/rex-agents` path. Moving the repo breaks them. Changing hook definitions invalidates Codex hook trust; the user must re-trust via `/hooks`.
- `edit_hooks` removes every hook entry whose command starts with this project's `_hook` command, including events earlier versions registered, then adds the current `EVENTS`.
- Install and uninstall remove the legacy Lua module and `require` marker line from earlier versions; run `rex config reload` afterward.
- Install takes a one-time backup. Uninstall removes hooks, links, and the cache. `_hook` does nothing when not installed.
- `~/.local/share/rex-agents/install.json` holds the install manifest and backup path.
- Path overrides: `XDG_CACHE_HOME`, `XDG_DATA_HOME`, `XDG_CONFIG_HOME`, `REX_CONFIG`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME`. Binary overrides: `REX_AGENTS_REX`, `REX_AGENTS_REASON` (default `~/.reason/bin/reason-network`).

## Delegation routing

Every worker runs in a Rex pane, including one on the driver's own harness, so all workers share one Reason channel, one cleanup, and a driver-chosen effort. The shared skill is the only model-named delegation skill; the former `sol`, `astra`, `fable`, `opus`, and `sonnet` skills were removed to stop routing collisions.

## Invariants

Tests and the live verification depend on these. Do not weaken them without the user's explicit request.

- Never poll, read, or acknowledge another conversation's Reason inbox. Reason's own hooks and MCP handle delivery.
- Launches never take focus. Workers open as splits beside the anchor pane, not tabs.
- Workers remain native interactive conversations. Python stdlib only, with no extra daemon, MCP, or SDK dependency.
- Never retry an uncertain launch without inspecting Rex: the label check under `launch.lock` does this. Never pass the initial task twice.
- One level of owned workers: an owned worker pane cannot launch more workers.
- Cleanup closes only panes labeled with the caller's owner, never the driver's own pane.
- Identity never comes from cwd, repo, pane title, or display name.
- Ordinary commands never install or reconfigure Reason.
- Subprocesses get argument arrays; message bodies go via stdin and are never shell-evaluated.

## Tests

Tests make no real Rex or Reason calls. They replace the Rex and Reason boundaries with in-memory fakes of panes, labels, and rosters, clear `os.environ`, and point `XDG_*` and `REX_AGENTS_REASON` at temp paths; none write to the real home.

Live checks are recorded in `VERIFICATION.md`, with raw evidence in `.verification/` (gitignored). Update `VERIFICATION.md` when behavior is re-verified live, and state what remains fixture-only.
