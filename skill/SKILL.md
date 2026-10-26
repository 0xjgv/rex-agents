---
name: rex-agents
description: Discover Claude Code and Codex agents, launch interactive workers, send Reason messages, and focus their Rex panes.
---

# Rex agents

Use `rex-agents list --json` to discover agents and their current Reason addresses. Use exact addresses when names are ambiguous. Repository and display names never establish sender identity. `rex-agents doctor` reports missing dependencies and incompatible integrations.

Choose the delegation tool before launching anything. For work in the same harness, prefer that harness's native subagent tool when it supports the requested model and effort. For example, a Codex driver delegates Sol work through native Codex subagents without creating Rex panes. Use `rex-agents launch` for cross-harness work, an explicitly requested visible interactive pane, or a model/effort combination the native subagent tool cannot select. Do not change the requested model to make native routing fit. Native subagents use their harness's lifecycle and are not included in Rex cleanup.

For cross-harness work, a Claude driver can call Codex `gpt-6.1-sol` at `high` effort. A Codex driver can call Claude `claude-opus-5-5` at `xhigh` effort:

```sh
rex-agents launch codex --name helper --cwd /absolute/project --model gpt-6.1-sol --effort high --task-file /path/task.txt
rex-agents launch claude --name reviewer --cwd /absolute/project --model claude-opus-5-5 --effort xhigh --task-file /path/task.txt
```

`--model` and `--effort` are independently optional. Omitted values inherit native settings; actual availability belongs to the native harness. Keep native workers interactive. Preserve permissions and global defaults. The initial task is passed once, and no worktree is created.

Owned launches alternate `right`, `below`, `right`, using the last successful launch direction even after manual pane closure. The anchor is the newest live owned pane in the same server, session, and tab, or the driver pane. Launches preserve focus and return pane IDs immediately. `registration: pending` does not mean the agent is ready. Inspect `list` until the worker registers. Never retry an uncertain launch without inspecting its pane.

Human-launched drivers can launch one level of owned workers. Owned Rex workers cannot launch another level of Rex workers; native subagents remain managed by their harness. Ownership follows the native driver identity, including launches with explicit Rex context. Missing or conflicting agent identity fails explicitly. Human launches have no agent owner and require manual pane management.

Collect all worker results before running `rex-agents cleanup`, then give the driver's final answer. Cleanup cancels unfinished owned workers. Only known completed results and saved native transcripts persist; in-flight work can be lost. Save completed results outside worker panes before closing them.

Cleanup is local-only, uses native identity without Reason, and protects the driver pane and unrelated panes. JSON contains `closed`, `gone`, and `uncertain`; the exit status is 1 when uncertainty remains, otherwise 0. Unknown pane states stay reserved, and retrying cleanup is safe. Cleanup is an explicit CLI command, with no palette action. Never run cleanup on Stop or SessionEnd. Driver crashes require manual pane recovery. Resuming the same identity retains ownership; Claude `/clear` creates a new identity and leaves old workers for manual recovery.

For another configured Rex machine, add `--host LABEL`. Remote launches retain native remote settings and reject model or effort overrides. Remote cleanup is unsupported; manage those panes manually.

Send with `rex-agents send ADDRESS --message-file /path/message.txt`. The CLI requires your native conversation ID and verifies Reason's `is_me`. If identity is missing, report the failure; do not impersonate another session or use a human action as a fallback. Message files preserve multiline text and shell characters. `--fyi` requests no wake; normal messages may wake the recipient. To reply, use `--reply-to ORIGINAL_MESSAGE_ID`. Reason's native MCP `send_message` is also available.

Reason owns delivery and reply handling. Keep its native hooks and MCP enabled. Do not consume or acknowledge another conversation's inbox. A delivery result means pushed, queued, or left in an inbox; it never proves the recipient completed the task. Use explicit completion messages when work is finished, and preserve reply IDs.

Navigation is off by default. Change `rex-agents navigation on|off` only when the user asks; `navigation status` is read-only. Rex Remote Control is a separate user setting and currently stays disabled. When both are enabled, use `rex-agents focus ADDRESS` to navigate. Missing or inaccessible panes do not prevent Reason messaging. Existing conversations acquire mappings on their next hook event; restart or resume if newly installed hooks have not loaded. For a shell without Rex context, pass `--server`, `--session`, `--block`, or `--client` before the command when known. Never infer identities from directory or title.

The Rex command palette has List Agents, Message Agent, Focus Agent, Launch Agent, and Toggle Agent Navigation. Human actions send as Reason's terminal identity. No default keyboard bindings are installed.

Launched workers run in unfocused panes, so a prompt there can go unseen. A driver that launches a worker puts its own Reason address (from `rex-agents list --json`, the `is_me` row) in the task. A worker that needs a human decision sends the question to that address instead of opening AskUserQuestion or `request_user_input`, then waits for the reply. The driver asks its human and replies with `--reply-to`; it never answers for the human. As a backstop, hooks pop up a Reason notification when a launched worker opens AskUserQuestion (Claude) or a permission prompt (Claude and Codex), and tell the owning driver with `--fyi`. The prompt still waits in the worker pane.

CLI and skill links point into this checkout. After hook definitions change, run `rex-agents install` and re-trust Codex hooks through `/hooks`.

`rex-agents install` adds only this project's CLI, skill, hooks, and Lua actions. Run `rex config check` and `rex config reload` afterward. Ordinary commands never install Reason or change its configuration. `rex-agents uninstall` removes this project's additions and cache, leaving Reason and active sessions intact.
