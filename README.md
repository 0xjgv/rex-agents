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
rex-agents launch --name reviewer --cwd /absolute/project --model claude-opus-5-5 --effort xhigh --task-file /tmp/task.txt
rex-agents launch --name helper --cwd /absolute/project --model gpt-6.1-sol --effort high --task-file /tmp/task.txt
rex-agents cleanup
```

The model picks the harness: `claude-*` runs Claude Code, `gpt-*` runs Codex. `--model` is required; an omitted `--effort` inherits native settings. Every worker runs in a pane, even on the driver's own harness. The skill maps short names (sol, terra, astra, opus, fable, sonnet) to model IDs and has the driver choose the effort.

Each worker pane carries the label `rex-agents:<owner>:<name>`, the only worker record. Launches never take focus. An owned worker cannot launch more workers. The driver collects results through Reason, then runs `rex-agents cleanup` before its final answer. Cleanup closes that driver's labeled panes, including unfinished workers. It prints `closed`, `gone`, and `uncertain` JSON and exits 1 on uncertainty.

When a driver-owned Claude worker opens AskUserQuestion, a hook refuses it and tells the worker to ask its driver through Reason. When a worker blocks on a permission prompt, the hook pops up a Reason notification to the human.

After hook definitions change, rerun `rex-agents install` and re-trust Codex hooks through `/hooks`. See [VERIFICATION.md](VERIFICATION.md) for measured results and limits.
