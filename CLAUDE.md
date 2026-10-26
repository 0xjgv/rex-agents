# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Rex agents connects interactive Claude Code and Codex conversations to their exact Rex panes and messages them through Reason. Python 3.13+ standard library only; no packages, build, or linter. `bin/rex-agents` is a shim that re-execs into `python3.13` when started by an older `python3`, then puts the repo root on `sys.path`. User-facing docs: `ONBOARDING.md` (workflow, identity model, troubleshooting), `VERIFICATION.md` (live results and open limits), `skill/SKILL.md` (instructions installed for agents).

## Commands

```sh
python3.13 -m unittest discover -s tests -v                                    # full suite
python3.13 -m unittest tests.test_integration.IntegrationTests.test_ambiguous_target  # one test
./bin/rex-agents --help
```

Install touches live config (`~/.claude/settings.json`, `~/.codex/hooks.json`, Rex `init.lua`, `~/.local/bin`, skill links). Run it only when the task requires it, then reload Rex:

```sh
./bin/rex-agents install && rex config check && rex config reload
rex-agents doctor   # JSON checks; exits 1 if any check fails
```

## Architecture

Four entry paths converge on `Integration` in `rex_agents/core.py`:

- **Agent hooks.** `install.py` registers `bin/rex-agents _hook KIND EVENT` for `SessionStart`, `UserPromptSubmit`, `PostToolUse`, `Stop`, `SessionEnd` in Claude and Codex, plus `PermissionRequest` in both and `PreToolUse` matching `AskUserQuestion` in Claude. `Integration.hook` writes a locator `~/.cache/rex-agents/sessions/<sha256("kind:native_id")>.json` mapping the native conversation ID to Rex `server/session/block`. `SessionStart` records without touching the network; later events call `resolve()`, which checks Reason `is_me` and is the only code that renames a conversation (`reason status --name`, once, for launched workers). Nested agents and subagents that inherit a parent's Rex env are ignored so they cannot take its pane. On the two blocking-prompt events, `alert()` makes a launched worker send Reason `--notify` to its human (owned workers: to the driver with `--fyi --notify`). The prompt still waits in the pane; Codex `request_user_input` has no hook.
- **CLI.** `cli.py` parses commands and dispatches. `list`, `send`, `launch`, `cleanup`, `focus`, `navigation`, `doctor`, `install`, `uninstall` are public; `_hook`, `_registry`, `_worker`, `_action`, `_prompt` are internal entry points for hooks, Rex actions, and worker panes. `cleanup` prints JSON with `closed`, `gone`, and `uncertain`, exiting 1 if uncertainty remains, otherwise 0. Native identity errors also exit 1. Python `_action` forwards supplied model and effort arguments; the fixed Lua schema stays unchanged, with no cleanup palette action.
- **Rex actions.** `lua/rex_agents.lua` defines seven actions: five user-facing palette actions, plus `rex_agents_registry` and `rex_agents_remote_launch`, which other hosts call via `rex do`. User-facing actions with complete args run `rex-agents _action` (JSON on stdin) under a 24 s limit. List Agents, and any action missing args, opens a background split running `rex-agents _prompt PAYLOAD`, so output and interactive input escape the action time limit. Both reach `cli.action()`.
- **Launch.** `Integration.launch` takes `launch.lock`, rejects duplicate names (Reason roster plus `~/.cache/rex-agents/launches/<token>.json` reservations), then runs `rex split --focus=false` with `rex-agents _worker PAYLOAD`. `_worker` records the pane and `execvpe`s `claude --name NAME` or `codex --no-daemon` with `REX_AGENTS_LAUNCH=<token>`, which the worker's hooks use to link locator and reservation. Codex needs `--no-daemon` because its shared app server drops the Rex env before hooks run.

`launch(..., model=None, effort=None)` passes optional selectors to the native interactive harness. Claude drivers call Codex with `--model gpt-6.1-sol --effort high`; Codex drivers call Claude with `--model claude-opus-5-5 --effort xhigh`. Omitted values inherit native settings. The native harness validates actual availability. Selectors never change global defaults or permissions.

Local launch records track the native driver owner and split direction. Successful owned launches alternate `right` and `below`, using the last successful launch even after manual closure. The anchor is the newest live owned pane in the same server, session, and tab, or the driver pane. Ownership is resolved even with explicit Rex context. Human-launched drivers can launch one level of owned workers; owned Rex workers cannot launch another level of Rex workers. Native subagents remain under their harness lifecycle. Human launches have no agent owner.

`Integration.cleanup()` uses local ownership and Rex pane state under `launch.lock`, without Reason. The driver collects all completed results, then runs cleanup before its final answer. Cleanup closes unfinished workers too; only known completed results and saved native transcripts persist. Unknown pane states remain reserved for a safe retry. Protect the driver pane and unrelated panes. Never add Stop or SessionEnd auto cleanup. Driver crashes require manual pane recovery. A resumed native identity retains ownership; Claude `/clear` creates a new identity and leaves old workers for manual recovery. Complete cleanup resets split alternation.

Remote hosts reuse the same code: `listing()` calls `rex do rex_agents_registry` on each configured Rex host, and `launch --host` calls `rex do rex_agents_remote_launch` there. Remote launch rejects model and effort overrides; remote cleanup is unsupported. Remote paths have fixture coverage only.

Identity plumbing: `IDENTITY_VARS`, `clean_env()`, and `identity_env()` control which identity Reason sees. Agent sends set `REASON_NETWORK_AGENT/SESSION` and pass `--from kind:native_id`; `human=True` strips all agent vars so Reason uses its terminal identity. `native_identity()` reads `CODEX_THREAD_ID`, `REX_AGENTS_NATIVE_ID` (written to `CLAUDE_ENV_FILE` on Claude `SessionStart`), or `CLAUDE_CODE_SESSION_ID`, and fails on conflicts.

`run()` raises `CommandError` when a subprocess exits nonzero and plain `Error` on timeout or `OSError`. A nonzero exit alone does not prove Rex created nothing. `launch()` marks a reservation failed only when a `CommandError` message matches a known-definite pattern (`unknown flag`, `invalid`, `not found`, ...); every other failure leaves an uncertain reservation that blocks retries. Likewise, a stale reservation is released only after Rex confirms its pane is gone (`block ls` lacks it, or `session target "..." not found`); an unreachable host keeps it blocked. Keep these rules when touching `run()` or `launch()`.

## Install mechanics

- CLI and skill are **symlinks** into the repo, so Python edits take effect immediately.
- Hook definitions include the blocking-prompt events. After changing `EVENTS` or `BLOCKING`, reinstall and re-trust Codex hooks; `doctor` reports missing events.
- The Lua module is a **copy** with `@CLI@`, `@REX@`, `@PATH@` substituted at install time. After editing `lua/rex_agents.lua`, reinstall and run `rex config check` and `rex config reload`.
- Hook commands embed the absolute `bin/rex-agents` path. Moving the repo breaks them. Changing hook definitions invalidates Codex hook trust; the user must re-trust via `/hooks`.
- Install edits only its own hook entries, links, module, and `require` marker line, and takes a one-time backup. Uninstall removes those and the cache. `_hook` does nothing when not installed.
- `~/.local/share/rex-agents/install.json` holds the install manifest, backup path, and `navigation_enabled`.
- Path overrides: `XDG_CACHE_HOME`, `XDG_DATA_HOME`, `XDG_CONFIG_HOME`, `REX_CONFIG`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME`. Binary overrides: `REX_AGENTS_REX`, `REX_AGENTS_REASON` (default `~/.reason/bin/reason-network`).

## Delegation routing

Use native subagents for same-harness tasks when they support the requested model and effort. Use `rex-agents launch` for cross-harness tasks, explicit interactive panes, or selections unavailable to native subagents. The shared skill makes this choice; the CLI always launches a pane. Native subagent lifecycle stays with the harness and is outside Rex cleanup.

## Invariants

Tests and the live verification depend on these. Do not weaken them without the user's explicit request.

- An agent send never falls back to the terminal identity. Missing native identity or no unique `is_me` row fails.
- Identity never comes from cwd, repo, pane title, or display name. Messaging matches native IDs through Reason `is_me`. Local launch ownership and cleanup use native identity without Reason registration.
- Never poll, read, or acknowledge another conversation's Reason inbox. Reason's own hooks and MCP handle delivery.
- Launches, prompts, and messages never take focus. Workers open as splits beside the anchor pane, not tabs.
- Workers remain native interactive conversations. Use Python stdlib only, with no extra daemon, dx, MCP, or SDK dependency.
- Navigation is off by default. `focus` fails before any Rex call when it is off. The integration never changes Rex's Remote Control setting.
- Discovery (`list`, `registry`, `doctor`) never renames conversations.
- Never retry an uncertain launch without inspecting Rex for its pane. Never pass the initial task twice.
- Ordinary commands never install or reconfigure Reason.
- Subprocesses get argument arrays; message bodies go via stdin and are never shell-evaluated.

## Tests

`tests/test_integration.py` makes no real Rex or Reason calls. `Fake(Integration)` overrides `reason`, `rex`, and `hosts` with in-memory rosters and pane state; extend it for new external calls. Tests clear `os.environ` or point `XDG_*` and `REX_AGENTS_REASON` at temp paths; none write to the real home. `IntegrationTests` patches `rex_agents.install.navigation` to enabled. `InstallTests` installs into a temp home whose path contains a space and a quote. `ProcessBoundaryTests` runs the real `bin/rex-agents` as a subprocess against a fake Reason engine selected with `REX_AGENTS_REASON`.

`tests/test_cli_lifecycle.py` patches `Integration` and subprocess boundaries and clears the environment. It checks optional CLI and `_action` selectors, literal tasks, cleanup JSON and exit status, and identity errors without real subprocess or network calls.

Live checks are recorded in `VERIFICATION.md`, with raw evidence in `.verification/` (gitignored). Update `VERIFICATION.md` when behavior is re-verified live, and state what remains fixture-only.
