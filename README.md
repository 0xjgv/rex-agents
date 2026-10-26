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
rex-agents launch claude --name reviewer --cwd /absolute/project --task-file /tmp/task.txt
rex-agents launch codex --name helper --cwd /absolute/project
rex-agents send person/reviewer --message-file /tmp/message.txt
rex-agents send person/reviewer --message-file /tmp/reply.txt --reply-to MESSAGE_ID
rex-agents navigation status
```

Navigation defaults off. Rex Remote Control is also intentionally disabled on this machine. `rex-agents navigation on` permits explicit focus requests but does not change that Rex setting. Launches and messages never automatically focus a pane. Workers and action prompts open split panes, not tabs.

The command palette provides List Agents, Message Agent, Launch Agent, Focus Agent, and Toggle Agent Navigation. Human actions send as Reason's terminal identity; agent CLI sends require verified native identity. There are no default key bindings.

See [VERIFICATION.md](VERIFICATION.md) for measured results and limitations. Remote behavior has fixture coverage; live cross-machine validation awaits another enrolled machine.

API references: [Rex actions](https://www.superlogical.com/rex/docs/customize/actions), [Rex Lua API](https://www.superlogical.com/rex/docs/reference/lua), and [Reason CLI and hook source](https://github.com/reason-machines/reason-network/tree/5a6d0835868e1e648bed9144360d29455ebe8e6f/src).
