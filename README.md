# Rex agents

Connect interactive Claude Code and Codex conversations through Rex and Reason. Discover agents, launch workers in background panes, exchange messages, and optionally navigate to their panes. Python standard library only; Reason remains the only integration background service.

**Start with [ONBOARDING.md](ONBOARDING.md)** for the workflow, installation, identity model, troubleshooting, and removal.

```sh
python3 -m unittest discover -s tests -v
./bin/rex-agents install
rex config check
rex config reload
rex-agents doctor
```

Reason's native Claude/Codex integrations must be enabled separately through supported Reason setup. Ordinary commands never install Reason or change its configuration.

```sh
rex-agents list --json
rex-agents launch claude --name reviewer --cwd /absolute/project --model claude-opus-5-5 --effort xhigh --task-file /tmp/task.txt
rex-agents launch codex --name helper --cwd /absolute/project --model gpt-6.1-sol --effort high --task-file /tmp/task.txt
rex-agents send person/reviewer --message-file /tmp/message.txt
rex-agents send person/reviewer --message-file /tmp/reply.txt --reply-to MESSAGE_ID
rex-agents navigation status
```

For same-harness work, use native subagents when they support the requested model and effort; no Rex pane is needed. Use this launcher for cross-harness work or an explicit interactive pane. For example, Claude can call Codex `gpt-6.1-sol` with `high` effort, and Codex can call Claude `claude-opus-5-5` with `xhigh` effort. These are explicit worker selections, not changed defaults. Both flags are optional; omitted values inherit native settings. The native harness determines actual model and effort availability. Permissions stay unchanged, and workers remain native interactive conversations.

Owned worker panes alternate `right`, `below`, `right`, using the last successful launch direction even if an earlier pane was closed. Each launch anchors to the newest live owned pane in the same server, session, and tab, or the driver pane. Launches preserve focus. Only human-launched drivers can launch owned workers; owned Rex workers cannot launch another level of Rex workers. Native subagents stay under their harness's lifecycle.

After collecting every worker's result, the driver runs `rex-agents cleanup` before its final answer. Cleanup closes local panes owned by that native driver identity, including unfinished workers. Only known completed results and saved native transcripts persist; in-flight work can be lost.

Cleanup returns JSON with `closed`, `gone`, and `uncertain`; uncertainty exits 1 and keeps reservations for a safe retry. It needs no Reason connection and never closes unrelated panes. Cleanup is an explicit CLI command, with no palette action or Stop/SessionEnd auto cleanup. Driver crashes and Claude `/clear` leave panes for manual recovery. Remote launch keeps its existing behavior; remote selectors and remote cleanup are unsupported.

Navigation defaults off. Rex Remote Control stays disabled on this machine. `rex-agents navigation on` permits explicit focus requests but does not change that Rex setting. Messages never automatically focus a pane. Workers and action prompts open split panes, not tabs.

The command palette provides List Agents, Message Agent, Launch Agent, Focus Agent, and Toggle Agent Navigation. Human actions send as Reason's terminal identity; agent CLI sends require verified native identity. There are no default key bindings.

CLI and skill links point into this checkout. These changes need no install or new dependencies; Lua actions and hooks remain unchanged.

See [VERIFICATION.md](VERIFICATION.md) for measured results and limitations. Remote behavior has fixture coverage; live cross-machine validation awaits another enrolled machine.

API references: [Rex actions](https://www.superlogical.com/rex/docs/customize/actions), [Rex Lua API](https://www.superlogical.com/rex/docs/reference/lua), and [Reason CLI and hook source](https://github.com/reason-machines/reason-network/tree/5a6d0835868e1e648bed9144360d29455ebe8e6f/src).
