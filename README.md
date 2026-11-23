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
rex-agents launch --name helper --cwd /absolute/project --model gpt-6.2-sol --effort high --task-file /tmp/task.txt
rex-agents cleanup
```

The model picks the harness: `claude-*` runs Claude Code, `gpt-*` runs Codex. `--model` is required; an omitted `--effort` inherits native settings. `--permission-mode MODE` starts a Claude worker in that permission mode, such as `bypassPermissions`; omitted, the worker takes its settings' mode and may stop on a permission prompt. `--disallowed-tools TOOL [TOOL ...]` removes those tools from a Claude worker, shrinking every request it sends; a Codex worker refuses it. `--append-system-prompt-file FILE` appends the file's text to a Claude worker's system prompt (`--append-system-prompt`), where standing rules survive compaction; a Codex worker gets it as `developer_instructions`. A missing file is refused before any pane opens. `--settings JSON` gives a Claude worker Claude Code settings, such as `autoMemoryDirectory`; they are merged into the worker's own `--settings` (`crossSessionInbound` stays `accept`), kept for resume, and refused for a Codex worker or anything but a JSON object. Repeat `--env KEY=VALUE` to set variables in the worker, Codex tool shells included. Every worker runs in a pane, even on the driver's own harness. The skill maps short names (sol, terra, astra, opus, fable, sonnet) to model IDs and has the driver choose the effort.

Each worker pane carries its owner and name in the label `rex-agents:<owner>:<name>` (grouped panes append `:group`). Launches never take focus. A worker opens beside the driver, or with `--tab` in a tab of its own, with `--new-session` in a Rex session of its own, or with `--with WORKER` beside another worker. `--group NAME` shares a named session across callers and gives each native conversation its own tab. Workers fill equal-height rows in launch order, with up to three equally wide panes in each row. Group names are caller-supplied, so `codex`, `research`, and `reviews` use the same launcher behavior. A group launch requires a native conversation identity and works from outside Rex. An existing session with that label is reused, including when it has other tabs. Duplicate session labels are refused. An owned worker cannot launch more workers. The driver collects results through Reason, then runs `rex-agents cleanup` before its final answer. Cleanup closes that driver's labeled panes, including unfinished workers. It prints `closed`, `gone`, and `uncertain` JSON and exits 1 on uncertainty.

A worker that exits sends no message. `rex-agents status` lists the driver's live workers. `rex-agents status --all` lists every live worker in every Rex session, whoever launched it, and adds each one's `owner`. `rex-agents wait --name NAME` blocks until that worker's pane ends and prints how; a driver runs it as a background command, so the exit wakes it.

`rex-agents resume --name NAME [--task TEXT | --task-file PATH]` reopens an ended worker on its own conversation, with full context, in the same placement and with the same flags, the appended system prompt included as launch read it. Launch pins a Claude worker's conversation with `--session-id`; a Codex worker's ID comes from its SessionStart hook. Each launch writes `${XDG_STATE_HOME:-~/.local/state}/rex-agents/workers/<owner>/<name>.json`, which outlives the pane and `cleanup`; relaunching the name starts a new conversation and overwrites it. Resume refuses while the worker has a pane. Background processes, such as the driver's `wait`, do not come back: re-arm them. Without a record, `claude --resume NAME` run in the worker's cwd reopens a Claude worker whose name is unique there; two conversations under one name make it ambiguous.

When a driver-owned Claude worker opens AskUserQuestion, a hook refuses it and tells the worker to ask its driver the way its task says. When a worker blocks on a permission prompt, the hook pops up a Reason notification to the human.

After hook definitions change, rerun `rex-agents install` and re-trust Codex hooks through `/hooks`. See [VERIFICATION.md](VERIFICATION.md) for measured results and limits.
