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

**State is the pane label.** Each worker pane is labeled `rex-agents:<owner>:<name>`, where `owner` is `sha256("kind:native_id")[:16]` for an agent driver, or `-` for a human. Rex labels survive title changes and are capped at 128 characters. Panes close when their process exits. `panes()` lists blocks across all sessions, sorted by block ID (UUIDv7, so oldest first). The duplicate-name check, nested-launch guard, ownership, placement, and cleanup all read labels. The cache under `~/.cache/rex-agents` holds only `sessions/<owner>.json` locators and `launch.lock`.

**Identity.** `native_identity()` reads `CODEX_THREAD_ID` or `CLAUDE_CODE_SESSION_ID`, fails on conflicts (Codex ID with Claude vars), and returns `None` for a human shell. Identity never comes from cwd, repo, pane title, or display name.

**Hooks.** `install.py` registers `SessionStart` and `PermissionRequest` for both harnesses, plus `PreToolUse` matching Reason's `ask_user` for both and `AskUserQuestion` for Claude. `ASK_USER` holds each harness's name for Reason's tool: Codex spells it `mcp__reason_network__ask_user`. `SessionStart` writes the pane locator, because Codex tool shells lack `REX_*` even with `--no-daemon`. In a worker pane it also returns `KEEP_NAME` as `additionalContext`: Rex's own SessionStart hook tells every agent to name its session, and workers share their driver's. `where()` uses that locator when the shell has no `REX_SESSION`/`REX_BLOCK`. Only `PreToolUse` and `PermissionRequest` call `alert()`; events left by earlier installs do nothing. If the hook's own pane carries an owned worker label, `alert()` denies `AskUserQuestion` and `ask_user` (printed PreToolUse JSON, `permissionDecision: deny`) with `RELAY`, which tells the worker to send the question to its driver through Reason. Human-launched workers keep `ask_user`, since Reason pops it up itself. Other blocking prompts in worker panes, and AskUserQuestion in human-launched workers, send Reason `send <person> --notify --from kind:id` to the human. Hooks ignore nested agents and subagents (`agent_id`, or cross-harness inherited vars) so they cannot claim a parent's pane.

**Launch.** `Integration.launch` validates name, selectors, cwd, and executable, then takes `launch.lock`. It refuses if the driver pane is an owned worker, or if any pane already carries the name. Workers open in the driver's window: launch sends `rex api call session.new_split` into the driver's session. Requests travel as JSON on stdin, with ARGV as `command` and the caller's `PATH` as `path_prepend`, as `rex split` does. Launch uses the API because `rex split` cannot anchor on a split. Workers run `claude --name NAME` or `codex --no-daemon` directly; their panes start with Rex's environment, not the caller's, apart from `PATH`. `place()` keeps workers in balanced columns of up to three on the driver's right. If no pane in the driver's window carries the caller's owner, or the right side of the driver's own split holds any other pane, it splits the driver's pane horizontally with ratio 2/3: the driver keeps its full height and the workers take the right third. Otherwise it reads the window from `rex window ls` and treats that right side as the workers' area. The worker goes below the leftmost shortest column with ratio n/(n+1), so rows stay equal. When every column holds three, the worker opens a column after the whole area with ratio c/(c+1), so columns stay equal; `session.move_block` then moves the last column's lowest unfocused worker above it, and `session.resize_pane` sets the driver's border to 1/2. So 4 workers sit 2+2 and 7 sit 3+2+2. A failed move or resize reports that the worker launched. Rex does not rebalance when a pane closes, so sizes can end up uneven. Owned panes in other windows or sessions do not affect placement. Human launches follow the same rule with owner `-`. Any split failure is reported as uncertain; the label check refuses a retry while the pane exists. It cannot see a pane that Rex creates after a local timeout, so callers wait and inspect before retrying. Workers start from the absolute path `shutil.which` found, because the pane gets the login shell's environment. The nesting guard checks the explicit block, `REX_BLOCK`, and the locator's block.

`launch(name, cwd, model, task=None, effort=None)` requires a model, and the model picks the harness (`HARNESS`): `claude-*` runs Claude Code, `gpt-*` runs Codex, anything else is refused. Claude gets `--model`/`--effort`, Codex `-m` and `-c model_reasoning_effort=...`. An omitted effort inherits native settings. The skill maps short names (sol, terra, astra, luna, opus, fable, sonnet, haiku) to model IDs. When the user leaves the model or effort open, the driver names the task's role and takes the model and effort from the skill's role table, which may pick either harness. The table copies effort-router's unmeasured `ROLES` defaults; nothing calls effort-router.

**Cleanup.** `Integration.cleanup()` requires native identity and closes every pane labeled with the caller's owner, except the driver's own pane. It then re-lists to confirm absence, and runs `rex session kill` on each session that held a closed or gone pane and now holds no pane at all. It prints `closed`, `gone`, `uncertain` JSON and exits 1 if anything is uncertain. Never add Stop or SessionEnd auto cleanup.

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
- Launches never take focus, and a moved worker is never the focused one. Workers open in the driver's tab, in balanced columns of up to three on its right: one column takes a third of the width, more share half. The driver's pane keeps its full height.
- Workers remain native interactive conversations. Python stdlib only, with no extra daemon, MCP, or SDK dependency.
- Never retry an uncertain launch without inspecting Rex: the label check under `launch.lock` does this. Never pass the initial task twice.
- One level of owned workers: an owned worker pane cannot launch more workers.
- Cleanup closes only panes labeled with the caller's owner, never the driver's own pane, and kills only sessions it emptied.
- Identity never comes from cwd, repo, pane title, or display name.
- Ordinary commands never install or reconfigure Reason.
- Subprocesses get argument arrays; message bodies go via stdin and are never shell-evaluated.

## Tests

Tests make no real Rex or Reason calls. They replace the Rex and Reason boundaries with in-memory fakes of panes, labels, and rosters, clear `os.environ`, and point `XDG_*` and `REX_AGENTS_REASON` at temp paths; none write to the real home.

Live checks are recorded in `VERIFICATION.md`, with raw evidence in `.verification/` (gitignored). Update `VERIFICATION.md` when behavior is re-verified live, and state what remains fixture-only.
