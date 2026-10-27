# Verification record

Versions: Rex `0.0.1792787366-g623b2d` (API revision 7), Claude Code `2.1.310`, Codex `0.164.0`, Reason Network `0.12.13`, Python standard library.

## Earlier design (historical)

These results describe the earlier, larger design (locators, reservations, `list`/`send`/`focus`, Lua actions). They still hold for Reason and the native harnesses:

- Claude and Codex conversations exchanged Reason messages with correct senders and `reply_to`. Multiline bodies with quotes, `$(...)`, backticks, `$HOME`, and spaced paths arrived literally. The integration never polled or acknowledged an inbox.
- A delivery result (pushed, queued, or left in an inbox) was observed separately from completed work. Reason rejects self-sends.
- Codex's shared app server drops the Rex environment before hooks run. `--no-daemon` preserves it for hooks.
- Cross-harness launches showed the requested models (Claude Opus 5.5 high, `GPT-6.1-Sol high`) and right/below/right splits without focus changes. Empty Codex sessions display effort as `default` until the first prompt.
- Reason's wrapper failed account enrollment with `this link names only this computer, which can't let itself in`. Local messaging works; no second machine is enrolled.

Raw evidence is under `.verification/` (gitignored).

## Simplification (2026-10-26)

Probes (raw notes in `.verification/simplify/probes.md`):

- Rex pane labels persist through process title changes (tested with a 92-character label). Rex rejects labels over 128 characters: `label must be at most 128 characters`.
- `rex split` panes start with the Rex server's environment (`REX_*` only). The caller's variables, including `CLAUDE*`, are not inherited.
- Panes close themselves when their process exits, with status 0 or 3 (`block target ... not found`).
- Claude Bash shells carry `REX_SERVER`, `REX_SESSION`, `REX_BLOCK`, and `CLAUDE_CODE_SESSION_ID`.
- Codex tool shells carry `CODEX_THREAD_ID` but no `REX_*` variables, with and without `--no-daemon`.
- Inside the Codex workspace-write sandbox, `reason-network who --json` fails: `Error: could not start the network daemon`.
- From a plain Claude Bash shell, `reason-network who --json` marks the right session `is_me` without `REASON_NETWORK_*` variables.
- Codex hook review showed the `PermissionRequest` alert hook untrusted ("1 hook needs review"), so the Codex alert was inactive before this change.

Live smoke run from a Claude driver pane, using the new code without reinstalling:

- `launch claude --model claude-haiku-5-5` opened a worker whose header showed Haiku 5.5.
- A task containing quotes, `$(printf x)`, backticks, `$HOME`, and a path with spaces arrived literally.
- A second launch with the same name was refused (exit 1).
- A second worker (`launch codex --effort low`) anchored on the first worker and split `below`.
- A launch with `REX_BLOCK` set to a worker pane was refused: `Owned workers cannot launch nested workers`.
- `cleanup` closed exactly the two workers and exited 0. A repeat returned empty `closed`, `gone`, and `uncertain` lists. Unrelated panes remained.

An independent review then found five defects, all fixed with regression tests that fail when each fix is reverted:

- Hook events left by the earlier install reached the alert path.
- An explicit `--block` bypassed the nesting guard.
- A session closing mid-scan aborted launch and cleanup.
- An unexpected Reason output shape escaped the hook.
- The executable was resolved on the caller's PATH, not the pane's.

After the fixes, a third live launch started Claude from its absolute path with Haiku 5.5 and the literal task, and `cleanup` closed it with no uncertainty. The suite has 29 tests.

Not yet verified live:

- Alert hook delivery of the Reason `--notify` pop-up.
- A Codex driver launching through its `SessionStart` locator after hook re-trust.

Reinstall migration on the live configuration:

- `rex-agents install` left our hooks on Claude `SessionStart`, `PermissionRequest`, and `PreToolUse` (`AskUserQuestion`), and on Codex `SessionStart` and `PermissionRequest`.
- It removed our `UserPromptSubmit`, `PostToolUse`, `Stop`, and `SessionEnd` entries.
- The six unrelated hooks in each file and all non-hook Claude settings were unchanged.
- The `require` line and `rex_agents.lua` were removed.
- `rex config check` reported zero actions, and `rex config reload` succeeded.
- Codex hooks still need re-trust through `/hooks`.

## Model picks the harness (2026-10-27)

`launch` takes no harness argument. `--model` is required: `claude-*` runs Claude Code, `gpt-*` runs Codex. The skill maps sol, terra, astra, opus, fable, and sonnet to model IDs. Every worker gets a pane, even on the driver's own harness. The colliding skills (Claude `sol`, `astra`, `fable`, `opus`, `sonnet`; Codex `fable`) were deleted, and the Codex `fable` MCP server that the deleted skill hosted was disabled.

Live run from a Claude driver pane, without reinstalling:

- `launch --model gpt-6.1-sol --effort low` opened Codex. Its footer showed `GPT-6.1-Sol low`.
- `launch --model claude-sonnet-5-5 --effort low` opened Claude Code, anchored on the first worker. Its header showed `Sonnet 5.5 with low effort`, and it answered the task.
- `launch --model llama-4` was refused before Rex: `Unknown model family llama-4: expected claude-* or gpt-*`.
- `cleanup` closed both workers and exited 0.

## Dogfood: plain-language drivers (2026-10-27)

Two fresh driver conversations ran in their own Rex tabs, opened as a human would, with no model or effort hints. The prompts, both final plans, and the pane watch logs are in `.verification/dogfood-2026-10-27/`.

- **Claude driver** (`claude`, default Opus 5.5 xhigh, `--allowedTools` for `rex-agents`, `reason-network`, and the Reason MCP send and list tools). The prompt began "Work with sol 6.1 on a plan". It loaded `Skill(rex-agents)` first, launched `sol-plan` on `gpt-6.1-sol` at effort `high`, which it chose itself, and exchanged several rounds with sol.
- **Codex driver** (plain `codex`, with the shared app-server daemon, `model_reasoning_effort="medium"` to save time). The prompt began "Work with opus on a plan". It used `/Users/juan/.agents/skills/rex-agents/SKILL.md`, launched `opus-cleanup-plan` on Claude Opus 5.5 at effort `high`, agreed a five-bullet plan over several rounds, ran `rex-agents cleanup` itself, and closed opus. It launched without `--session` or `--block`. Its `SessionStart` hook wrote locator `d81bdee8d2826351.json`, pointing to its own pane, even though it was started without `--no-daemon`. That conflicts with the note that the shared app server drops `REX_*` before hooks, which may be stale for Codex 0.164. Whether this pane used the shared daemon was not checked, so workers keep `--no-daemon`.
- **Idle wake.** The Claude driver ended its turn at 09:57:09 UTC ("Waiting on sol's revision"). At 09:58:27 sol's Reason message started a new turn: "Another Claude session sent a message: <reason-message …>". No task notification came first. A relay worker showed the same thing: it ended its turn at 09:57:55 and woke at 09:58:00 on the driver's reply. Codex idle wake was already recorded (`it runs after the current turn, or now if idle`).
- **Question relay.** A haiku worker told to call AskUserQuestion was refused by the hook: `PreToolUse:AskUserQuestion hook error: You are a rex-agents worker, and only your driver talks to the human. …`. It sent the question to its driver with `send_message`, and the driver's reply woke it. Nothing waited on the human.
- **Human alerts.** Before the relay change, an AskUserQuestion in a Claude worker and a command approval in a worker-labeled Codex pane (`approval_policy="on-request"`, `sandbox_mode="read-only"`) each fired the hook. The human first reported no pop-up, then reported that both appeared, so delivery may lag. A direct `alert()` replay popped up. `approval_policy = "untrusted"` is rejected by Codex 0.164: `Error loading configuration: approval_policy = "untrusted" is no longer supported; remove this setting`.
- Codex hooks are trusted: `SessionStart` wrote locators for Codex workers. The `⚠ 1 warning` is gone from `--no-daemon` panes started after the `fable` MCP server was disabled. It remains in the daemon-backed Codex driver pane, probably because that daemon loaded the old config (inferred, not checked).
- `This machine isn't on a Reason Network yet: ask your user to run \`reason network\`.` trails every successful send. It concerns team enrollment (`"team": null`), not delivery.

Findings fed back: the skill now tells drivers to end their turn while waiting, because the Claude driver had built its own pane watcher to wake itself. The new hook relays worker questions to the driver.

Still open:

- Codex permission prompts never happen on this machine (`approval_policy = "never"`), so the Codex alert is rarely reachable.
- Codex `request_user_input` has no hook; only the task's rules keep it from reaching the human.
- Drivers and workers alike rename the shared Rex session when the Rex `SessionStart` hook asks them to name their work. Here the Codex driver and the `sol-plan` worker (`worker-startup-detection`) both renamed it.

The suite has 33 tests.

## Reason `ask_user` relay (2026-10-27)

Reason's MCP `ask_user` pops a question up on the human's screen and waits, and `~/.claude/settings.json` allows it without a prompt. The Claude `PreToolUse` hook now matches `AskUserQuestion|mcp__reason-network__ask_user`.

- `rex-agents install` changed only that matcher in `~/.claude/settings.json`. `~/.codex/hooks.json` stayed byte-identical, so Codex needs no re-trust.
- A Haiku 5.5 worker (`relay-ask-user`, effort low) told to call `ask_user` was refused: `PreToolUse:mcp__reason-network__ask_user hook error: You are a rex-agents worker, and only your driver talks to the human. …`. It sent that text to its driver with `send_message`. `cleanup` closed it and exited 0.

Fixture-only: a human-launched worker's `ask_user` passes untouched, since Reason pops it up itself. Codex workers have no hook for `ask_user`; only the task's rules stop them.

The suite has 34 tests.

## Splits anchor on the driver (2026-10-27)

Owned launches now split the driver pane every time, alternating `right` and `below`. Earlier sections that say a worker "anchored on the first worker" describe the previous behavior.

Live run from a Claude driver pane, without reinstalling: three idle `claude-sonnet-5-5` workers (`--effort low`, no task) all reported the driver as `anchor_id`. `rex window ls --json` showed the driver window as a horizontal split (worker 1 on the right half), whose left half was a vertical split (worker 2 on the bottom), whose top was a horizontal split (driver, then worker 3 on its right). `cleanup` closed all three, exited 0, and removed the caller's split state. Panes owned by another driver were untouched.

Fixture-only: human launches still split right from the driver every time.

## Columns of two (2026-10-27)

The driver splits once. Later workers fill full-height columns of two beside it, and every column keeps the same width. Launch now calls Rex's `session.new_split` API through `rex api call`, because `rex split -b` refuses a split ID (`"split:…" is a split ID, not a block`), and only a split anchor can open a full-height column. The previous section describes the behavior this replaces. The `splits/<owner>.json` cache is gone.

- Environment parity: in a scratch session, a pane from `rex split -- CMD` and a pane from `session.new_split` with `command`, `cwd`, and the caller's `PATH` as `path_prepend` had identical `env` output, apart from `REX_BLOCK` and `_`. Without `path_prepend`, the API pane lacked the caller's `PATH` entries from `.zshrc`.
- Live run from a Claude driver pane, without reinstalling: five idle `claude-sonnet-5-5` workers (`--effort low`, no task). Anchors: the driver, `col1`, `col1`'s column split, `col3`, then the split holding all worker columns. `rex window ls --json` showed the driver at `[0, 0, 0.5, 1]`, then `col1/col2`, `col3/col4`, and `col5`, each column 0.167 wide.
- `col6` went below `col5`. After `rex block close` on `col1`, five workers remained and the newest column was full, so `col7` opened a fourth column with ratio 0.75. All four columns were 0.125 wide, with `col2` alone at full height.
- In both layout snapshots, the driver window's `focused_block_id` was still the driver, and the driver's window never became active.
- The `col5` pane showed `Sonnet 5.5 with low effort`. `cleanup` closed `col2` through `col7` and exited 0. Panes owned by another driver were untouched.

Fixture-only: human launches use the same placement. No Codex worker ran through the API path; the environment probe and `test_gpt_model_runs_codex` cover its argv.

The suite has 35 tests.

## Workers session (2026-10-27)

Workers now open in a Rex session of their own, and the driver's pane never splits. The first launch calls `session.create` with a session labeled `<driver session label>-workers`. Later launches call `session.new_split` in the session of the newest owned pane and fill columns of two, as in the previous section. That section's layout beside the driver is replaced. `cleanup` kills a session it emptied.

- Live run from a Claude driver pane, without reinstalling: five idle `claude-sonnet-5-5` workers (`--effort low`, no task). All five reported the same `session_id`, labeled `csproj-lockfile-fix-workers` after the driver's session. Anchors: `q1`, `q1`'s column split, `q3`, then the window's root split.
- `rex window ls --json` showed one window: `q1/q2`, `q3/q4`, and `q5`, each column 0.333 wide. The driver's layer was still the driver alone at `[0, 0, 1, 1]`, and it was still focused.
- The user watched the screen during the launches and reported that the Rex view stayed put.
- The `q5` pane showed `Sonnet 5.5 with low effort`. `cleanup` closed `q1` through `q5` and exited 0. `rex ls` then listed only the driver's session.
- Rex accepts duplicate session labels: `rex session new probe-dup` twice created two sessions with that label. Two drivers in one Rex session therefore get two workers sessions with the same name; launch does not fail.

Fixture-only: workers join an existing owned pane's session; human launches use the same placement; cleanup leaves alone sessions that still hold other panes, and sessions that held none of the caller's panes. A workers session that empties because its workers exited on their own stays until the user closes it. No Codex worker ran through these API calls.

The suite has 37 tests.
