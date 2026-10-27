---
name: rex-agents
description: Launch interactive Claude Code and Codex workers into Rex panes, coordinate them through Reason, and close them when done.
---

# Rex agents

`rex-agents` launches native interactive Claude Code or Codex workers into unfocused Rex split panes, and closes the workers a driver owns. Reason handles discovery and messaging: use `reason-network who --json` or MCP `list_team` to find agents, and MCP `send_message` to message them.

Choose the delegation tool before launching anything. For work in the same harness, prefer that harness's native subagent tool when it supports the requested model and effort. Use `rex-agents launch` for cross-harness work, an explicitly requested visible interactive pane, or a model/effort combination the native subagent tool cannot select. Do not change the requested model to make native routing fit. Native subagents keep their harness's lifecycle and are not included in Rex cleanup.

For cross-harness work, a Claude driver calls Codex `gpt-6.1-sol` at `high` effort. A Codex driver calls Claude `claude-opus-5-5` at `xhigh` effort:

```sh
rex-agents launch codex --name helper --cwd /absolute/project --model gpt-6.1-sol --effort high --task-file /path/task.txt
rex-agents launch claude --name reviewer --cwd /absolute/project --model claude-opus-5-5 --effort xhigh --task-file /path/task.txt
```

`--model` and `--effort` are independently optional. Omitted values inherit native settings; the native harness validates availability. Permissions and global defaults stay unchanged. The task is passed once, and no worktree is created.

## Worker protocol

1. Put your own Reason address in the task. In a Claude shell, take the `is_me` row of `reason-network who --json`. In Codex, use MCP `list_team`; the CLI fails inside the Codex sandbox with `could not start the network daemon`.
2. Tell the worker to report by messaging that address with MCP `send_message`, and to send blocking human questions there instead of opening AskUserQuestion or `request_user_input`.
3. Reply to the worker's message `from` address with `reply_to`. Ask your human before answering a question meant for them; never answer for the human.
4. A delivery result means pushed, queued, or left in an inbox. It never proves the worker finished. Wait for its explicit completion message.
5. Collect every result, save what must outlive the pane, then run `rex-agents cleanup` before your final answer.

Never poll, read, or acknowledge another conversation's Reason inbox. Reason's own hooks and MCP deliver messages.

## Launch and cleanup rules

Each worker pane is labeled `rex-agents:<owner>:<name>`. The owner is a hash of your native conversation ID, or `-` for a human launch. The label is the only worker record. A launch refuses a name that already has a pane, and an owned worker pane cannot launch more workers. Launches return pane IDs immediately with `registration: pending`; the worker is not ready until it messages you.

If a launch reports an uncertain outcome, look for its label in Rex before retrying. A retry refuses while the labeled pane exists.

Owned launches alternate `right`, `below`, `right` from the last launch, anchored on your newest worker in the same tab, or your own pane. Human launches split right from the driver pane. Launches never take focus.

`cleanup` closes every pane labeled with your owner, including unfinished workers. In-flight work is lost. It prints JSON with `closed`, `gone`, and `uncertain`, and exits 1 when anything is uncertain. Retrying is safe. It never closes your own pane or unlabeled panes. Nothing runs cleanup automatically on Stop or SessionEnd. Claude `/clear` changes your identity and leaves old workers for manual closing.

When your shell lacks Rex context (Codex tool shells), the integration uses the pane its SessionStart hook recorded. If that is missing, pass `--session` and `--block` before the command. Never infer identity from directory or title.

When a launched worker opens AskUserQuestion (Claude) or a permission prompt (Claude and Codex), a hook pops up a Reason notification to the human. The prompt still waits in the worker pane.

`rex-agents install` adds only this project's CLI and skill links and hooks. After it changes hooks, re-trust Codex hooks through `/hooks`. Ordinary commands never install Reason or change its configuration.
