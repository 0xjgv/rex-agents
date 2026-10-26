---
name: rex-agents
description: Discover Claude Code and Codex agents, launch interactive workers, send Reason messages, and focus their Rex panes.
---

# Rex agents

Use `rex-agents list --json` to discover agents and their current Reason addresses. Use exact addresses when names are ambiguous. Repository and display names never establish sender identity. `rex-agents doctor` reports missing dependencies and incompatible integrations.

Launch an interactive worker with `rex-agents launch claude --name reviewer --cwd /absolute/project --task-file /path/task.txt` or substitute `codex`. Workers open in background split panes beside the launching pane and inherit model and permission settings. Launches preserve focus and return pane IDs immediately; `registration: pending` does not mean the agent is ready. Inspect `list` until the worker registers. Never retry an uncertain launch without inspecting its pane. No worktree is created. For another configured Rex machine, add `--host LABEL`; install this integration there first.

Send with `rex-agents send ADDRESS --message-file /path/message.txt`. The CLI requires your native conversation ID and verifies Reason's `is_me`. If identity is missing, report the failure; do not impersonate another session or use a human action as a fallback. Message files preserve multiline text and shell characters. `--fyi` requests no wake; normal messages may wake the recipient. To reply, use `--reply-to ORIGINAL_MESSAGE_ID`. Reason's native MCP `send_message` is also available.

Reason owns delivery and reply handling. Keep its native hooks and MCP enabled. Do not consume or acknowledge another conversation's inbox. A delivery result means pushed, queued, or left in an inbox; it never proves the recipient completed the task. Use explicit completion messages when work is finished, and preserve reply IDs.

Navigation is off by default. Change `rex-agents navigation on|off` only when the user asks; `navigation status` is read-only. Rex Remote Control is a separate user setting and currently stays disabled. When both are enabled, use `rex-agents focus ADDRESS` to navigate. Missing or inaccessible panes do not prevent Reason messaging. Existing conversations acquire mappings on their next hook event; restart or resume if newly installed hooks have not loaded. For a shell without Rex context, pass `--server`, `--session`, `--block`, or `--client` before the command when known. Never infer identities from directory or title.

The Rex command palette has List Agents, Message Agent, Focus Agent, Launch Agent, and Toggle Agent Navigation. Human actions send as Reason's terminal identity. No default keyboard bindings are installed.

`rex-agents install` adds only this project's CLI, skill, hooks, and Lua actions. Run `rex config check` and `rex config reload` afterward. Ordinary commands never install Reason or change its configuration. `rex-agents uninstall` removes this project's additions and cache, leaving Reason and active sessions intact.
