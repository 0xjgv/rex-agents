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
