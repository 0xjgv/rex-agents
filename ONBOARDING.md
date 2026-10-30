# Rex agents onboarding

Rex agents launches native interactive Claude Code and Codex workers into a Rex session of their own, and closes the workers a driver owns. Reason handles discovery and messaging. Rex handles terminals.

## What it does, and what it leaves to Reason

- `rex-agents launch` opens a worker in an unfocused pane in the driver's workers session, with optional model and effort.
- `rex-agents cleanup` closes the calling driver's workers, and the workers session once it is empty.
- A hook sends a driver-owned Claude worker's AskUserQuestion or Reason `ask_user` to its driver instead of the human. It pops up a Reason notification when a worker blocks on a permission prompt (Claude and Codex).

Find agents with `reason-network who` or MCP `list_team`. Message them with MCP `send_message`. Earlier versions also had `list`, `send`, `focus`, `navigation`, `doctor`, remote hosts, and Rex palette actions. Those are removed.

## Choose model and effort

Ask the driver to work with a model by name: sol, terra, astra, luna (Codex) or opus, fable, sonnet, haiku (Claude Code). The skill maps each name to its model ID. The model picks the harness: `claude-*` runs Claude Code, `gpt-*` runs Codex. The driver uses the model and effort you name. When you leave one open, the driver names the task's role (implement, validate, plan, advise, research, commit), takes the model and effort from the skill's role table, which may pick either harness, and tells you the pick. Every worker runs in a pane, even on the driver's own harness.

## Launch a worker

```sh
cat > /tmp/review-task.txt <<'TASK'
Read this project and identify three simplification opportunities.
Do not change files. Give file references and concrete reasons.
When done, send your result with MCP send_message to person/driver-session.
TASK

rex-agents launch --name reviewer --cwd /Users/juan/Code/rex-agents \
  --model claude-opus-5-5 --effort xhigh --task-file /tmp/review-task.txt
```

`--model` is required. An omitted `--effort` inherits native settings. Selectors change no global defaults or permissions. The directory must exist. The launcher creates no worktree. It passes the task once as one argument; nothing evaluates it as shell code. Names use letters, digits, underscores, or hyphens, up to 64 characters.

The result returns the session ID, pane IDs, the pane label, and `registration: pending`. The worker is ready when it messages you. A new Codex installation may first show its hook trust dialog.

Workers open in the driver's tab, in balanced columns of up to three on its right, and the driver keeps its full height. One column takes the right third. Two or more columns share the right half, all the same width. Each new worker goes to the shortest column, leftmost on a tie, and rows in a column stay equal. When every column holds three, the next worker opens a new column, and the last column's lowest worker moves above it: 3 workers sit in one column, 4 sit 2+2, 6 sit 3+3, and 7 sit 3+2+2. A worker that has focus is never moved. Placement reads the live layout. When a worker closes, Rex gives its space to a neighbor and nothing rebalances, so sizes can end up uneven. When the last worker closes, the driver regains the full width. Workers in other tabs or sessions, such as a workers session from an earlier version, do not affect placement. Pane labels (`rex-agents:<owner>:<name>`) remain the authoritative record. Human launches follow the same rule. Launches never take focus. Workers share the driver's session, so the skill tells them to leave its name alone. `cleanup` kills a session only if it emptied it.

## Worker protocol

1. The driver puts its own Reason address in the task. In a Claude shell, take the `is_me` row of `reason-network who --json`. In Codex, use MCP `list_team`; `reason-network` fails inside the Codex sandbox with `could not start the network daemon`.
2. The worker reports by messaging that address with MCP `send_message`. It sends blocking human questions there instead of opening AskUserQuestion, `request_user_input`, or Reason `ask_user`.
3. The driver replies to the message's `from` with `reply_to`. It asks its human before answering a question meant for them.
4. Delivered or queued does not mean the work finished. Wait for an explicit completion message.

## Close workers

Collect every result first. Then, from the same driver conversation, before its final answer:

```sh
rex-agents cleanup
```

Cleanup closes every pane labeled with the driver's owner, including unfinished workers. In-flight work is lost; native transcripts remain. It protects the driver pane and every unlabeled pane. It prints JSON with `closed`, `gone`, and `uncertain`, exits 0 when `uncertain` is empty, otherwise 1. Retrying is safe. Complete cleanup resets the next direction to `right`. Cleanup never closes human-launched panes (`rex-agents:-:<name>`). It also never closes panes from earlier versions, which carry `rex-agents:<uuid>` labels. Close those by hand.

No Stop or SessionEnd hook runs cleanup. A driver crash leaves panes for manual closing. Claude `/clear` changes the driver's identity, so close older workers by hand.

## How it works

The pane label is the only worker record: `rex-agents:<owner>:<name>`. The owner is the first 16 hex characters of `sha256("kind:native_id")` for an agent driver, or `-` for a human. The native ID comes from `CODEX_THREAD_ID` or `CLAUDE_CODE_SESSION_ID`. Rex keeps labels through title changes, and a pane closes when its process exits. So the label tells launch which names are taken and whether the driver is itself a worker. It tells cleanup which panes it may close.

Claude shells carry `REX_SESSION` and `REX_BLOCK`. Codex tool shells do not, even with `--no-daemon`. The `SessionStart` hook records each conversation's pane in `~/.cache/rex-agents/sessions/<owner>.json`, and launch and cleanup fall back to it. If the hook has not run (for example, Codex hooks are not trusted), pass the pane explicitly:

```sh
rex-agents --session SESSION_ID --block BLOCK_ID launch \
  --name helper --cwd /absolute/project --model gpt-6.1-sol --task-file /tmp/task.txt
```

Codex workers start with `--no-daemon`, because the shared app server drops the Rex environment before hooks run. The blocking-prompt hook reads its own pane label. In a driver-owned Claude worker, it refuses `AskUserQuestion` and Reason `ask_user` and tells the worker to send the question to its driver through Reason. For other blocking prompts in a worker pane, it sends the human a `--notify` message as the worker, and the prompt still waits in the pane. Codex model questions (`request_user_input`) and Codex calls to Reason `ask_user` have no hook; the task's rules are the only guard.

## Install

Requirements: Python 3.13 or newer (as `python3`, or `python3.13` on `PATH`), Rex, the Reason engine, and the agent CLIs you use.

1. Enable Claude Code and Codex through Reason's supported setup: `~/.reason/bin/reason-network setup`.
2. Run `./bin/rex-agents install`, then `rex config check` and `rex config reload`.
3. In Codex, trust the hooks through its dialog or `/hooks`. Changed hooks need renewed trust.

Install adds CLI and skill symlinks into this checkout and its own hook entries. Reinstalling over an earlier version also removes its old hook events, the Lua module, and the `require` line in Rex `init.lua`. Re-trust Codex hooks and run `rex config reload` afterward. Reinstall right after pulling this version: until then the old hook events stay registered. They are inert, but they still start a process on every prompt and tool call.

## Troubleshooting

**`No Rex pane known for this conversation`:** the shell has no Rex context and no locator exists. Trust Codex hooks and resume the conversation, or pass `--session` and `--block`.

**`Owned workers cannot launch nested workers`:** the driver pane is itself an owned worker. Launch from a human-started conversation.

**`Worker NAME already has a Rex pane`:** close that pane or choose another name.

**`Launch outcome uncertain`:** Rex may have created the pane. Look for its label with `rex block ls --json`. A retry refuses while the labeled pane exists. If the split timed out locally, Rex may still be creating the pane, so wait a few seconds and check again before retrying.

**A worker seems stuck:** it may wait on workspace trust, hook trust, login, or a prompt. Select its pane and look.

## Remove

```sh
rex-agents uninstall
rex config reload
```

Removal deletes only this project's hooks, links, legacy Lua additions, and cache. Reason integrations, active conversations, unrelated configuration, and backups remain. Hooks already loaded become inert.
