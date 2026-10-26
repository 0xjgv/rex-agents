# Rex agents

Launch interactive Claude Code and Codex workers into Rex split panes, and close the ones a driver owns. Reason handles discovery and messaging. Python standard library only.

**Start with [ONBOARDING.md](ONBOARDING.md)** for the workflow, worker protocol, installation, and troubleshooting.

```sh
python3.13 -m unittest discover -s tests -v
./bin/rex-agents install
rex config check
rex config reload
```

Reason's Claude and Codex integrations must be enabled separately through supported Reason setup. Ordinary commands never install Reason or change its configuration.

```sh
rex-agents launch claude --name reviewer --cwd /absolute/project --model claude-opus-5-5 --effort xhigh --task-file /tmp/task.txt
rex-agents launch codex --name helper --cwd /absolute/project --model gpt-6.1-sol --effort high --task-file /tmp/task.txt
rex-agents cleanup
```

For same-harness work, use native subagents when they support the requested model and effort. Use this launcher for cross-harness work or an explicit interactive pane. `--model` and `--effort` are optional; omitted values inherit native settings.

Each worker pane carries the label `rex-agents:<owner>:<name>`, the only worker record. Launches never take focus. An owned worker cannot launch more workers. The driver collects results through Reason, then runs `rex-agents cleanup` before its final answer. Cleanup closes that driver's labeled panes, including unfinished workers. It prints `closed`, `gone`, and `uncertain` JSON and exits 1 on uncertainty.

When a launched worker blocks on AskUserQuestion or a permission prompt, a hook pops up a Reason notification to the human.

After hook definitions change, rerun `rex-agents install` and re-trust Codex hooks through `/hooks`. See [VERIFICATION.md](VERIFICATION.md) for measured results and limits.
