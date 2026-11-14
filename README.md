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

The model picks the harness: `claude-*` runs Claude Code, `gpt-*` runs Codex. `--model` is required; an omitted `--effort` inherits native settings. `--permission-mode MODE` starts a Claude worker in that permission mode, such as `bypassPermissions`; omitted, the worker takes its settings' mode and may stop on a permission prompt. `--disallowed-tools TOOL [TOOL ...]` removes those tools from a Claude worker, shrinking every request it sends; a Codex worker refuses it. Repeat `--env KEY=VALUE` to set variables in the worker, Codex tool shells included. Every worker runs in a pane, even on the driver's own harness. The skill maps short names (sol, terra, astra, opus, fable, sonnet) to model IDs and has the driver choose the effort.

Each worker pane carries its owner and name in the label `rex-agents:<owner>:<name>` (grouped panes append `:group`). Launches never take focus. A worker opens beside the driver, or with `--tab` in a tab of its own, with `--new-session` in a Rex session of its own, or with `--with WORKER` beside another worker. `--group NAME` shares a named session across callers and gives each native conversation its own tab. Workers fill equal-height rows in launch order, with up to three equally wide panes in each row. Group names are caller-supplied, so `codex`, `research`, and `reviews` use the same launcher behavior. A group launch requires a native conversation identity and works from outside Rex. An existing session with that label is reused, including when it has other tabs. Duplicate session labels are refused. An owned worker cannot launch more workers. The driver collects results through Reason, then runs `rex-agents cleanup` before its final answer. Cleanup closes that driver's labeled panes, including unfinished workers. It prints `closed`, `gone`, and `uncertain` JSON and exits 1 on uncertainty.

A worker that exits sends no message. `rex-agents status` lists the driver's live workers. `rex-agents wait --name NAME` blocks until that worker's pane ends and prints how; a driver runs it as a background command, so the exit wakes it.

When a driver-owned Claude worker opens AskUserQuestion, a hook refuses it and tells the worker to ask its driver the way its task says. When a worker blocks on a permission prompt, the hook pops up a Reason notification to the human.

After hook definitions change, rerun `rex-agents install` and re-trust Codex hooks through `/hooks`. See [VERIFICATION.md](VERIFICATION.md) for measured results and limits.
