---
name: rex-agents
disable-model-invocation: true
description: Work with other models as a team. Launch opus, fable, sonnet, haiku (Claude Code) or sol, terra, astra, luna (Codex) as interactive workers in Rex panes, collaborate with them through Reason, and close them when done. Use when the user asks to work with, consult, or delegate to one of these models, or to a team of agents.
---

# Rex agents

You drive. Each worker is a native interactive Claude Code or Codex conversation in an unfocused Rex pane, in columns on the right of your tab. You pick its model and effort, talk with it through Reason, make the decisions, and close it. Only you talk to the human.

Never rename a Rex session, tab, or pane: no `rex session rename`, even when Rex's SessionStart hook says to name the session. Your workers share your session, and the human owns its name.

## Pick model and effort

| Name | Model | Runs in |
|---|---|---|
| opus | `claude-opus-5-5` | Claude Code |
| fable | `claude-fable-5-1` | Claude Code |
| sonnet | `claude-sonnet-5-5` | Claude Code |
| haiku | `claude-haiku-5-5` | Claude Code |
| sol | `gpt-6.1-sol` | Codex |
| terra | `gpt-6.1-terra` | Codex |
| astra | `gpt-6-astra` | Codex |
| luna | `gpt-6-luna` | Codex |

The model picks the harness: `claude-*` runs Claude Code, `gpt-*` runs Codex. Use any model, harness, or effort the user names. Fill what they leave open from the one role below that fits the task: take the first model in its preference order that fits the user's instructions, and the role's effort. For `advise`, use the harness other than yours unless the user says otherwise. These are defaults, not measured rankings.

| Role | Fits | Model preference | Effort |
|---|---|---|---|
| `implement` | Writing or changing code, including fixing a bug whose cause is unknown | sol → opus | `medium` |
| `validate` | Checking finished work for correctness: review, tests, verification | opus → astra | `high` |
| `plan` | Designing the approach: structure outlines and implementation plans | opus → sol | `xhigh` |
| `advise` | Decisions, trade-offs, and second opinions | astra → fable | `high` |
| `research` | Reading code or docs to answer questions with evidence, without changing anything | terra → sonnet | `high` |
| `commit` | Commits, PR text, and other small mechanical tasks | terra → sonnet | `medium` |

Map the short name through the model table, launch with that model and effort, and tell the user the role and pick, such as "plan → opus, xhigh". Always pass `--effort`: `low`, `medium`, `high`, `xhigh`, or `max`; Codex also takes `ultra`. Every worker gets a pane, even on your own harness; do not substitute a native subagent or another model.

## Launch

Write the task to a file, then:

```sh
rex-agents launch --name sol-plan --cwd /absolute/project --model gpt-6.1-sol --effort high --task-file /path/task.txt
```

Names are unique across Rex: 1–64 letters, digits, `_`, or `-`. The task is passed once, literally; no worktree is created. The result says `registration: pending`; the worker is ready when it messages you. On `Launch outcome uncertain`, look for its name in `rex-agents status` before retrying.

`--env KEY=VALUE`, repeatable, sets a variable in the worker, Codex tool shells included.

`--tab` opens the worker alone in a new, unfocused tab of your session, named after it. `--with WORKER` opens the worker in your worker WORKER's tab; in a `--tab` tab, every pane shares the tab as an equal grid. `--new-session` opens the worker in a new Rex session named after it; add its helpers there with `--with WORKER`. Close any of them with `cleanup --name`; a tab closes with its last pane, and so does a `--new-session` session, even when its worker had already ended.

## Watch

A worker that exits sends no message. For a worker you keep across turns, run `rex-agents wait --name NAME` as a background command right after its launch (Claude Code: `run_in_background`). It blocks until that worker's pane ends, and its exit wakes you. It prints `ended` with an `exit_code` when the worker's program exited, `ended` with only a `block_id` when the pane was closed, as `cleanup` does, or `gone` when no pane of yours has that name. On an end you did not cause, tell the user, and relaunch the worker if its work is still owed.

`rex-agents status` lists your live workers with their session and block. A worker missing from it has no pane. Read a worker's screen with `rex capture -s SESSION -b BLOCK --trim`.

## Collaborate

Every task states:

1. Your Reason address. In Claude, take the `is_me` row of `~/.reason/bin/reason-network who --json`; `reason-network` is often not on PATH. In Codex, use MCP `list_team`; the CLI fails in the Codex sandbox.
2. The goal, files, constraints, and the shape of the answer you want.
3. The rules: reply with MCP `send_message` to that address; send questions there, never to AskUserQuestion, `request_user_input`, or Reason `ask_user`; launch no workers, leave the Rex session's name alone, and message no one else; say `DONE` when finished, with each command you ran and its exit code or output.

Then work in rounds. Reply to the worker's `from` with `reply_to`: share drafts, ask for critique, push back. Attach drafts and long results with `send_message` `files` (up to 10 text files, 256 KB each, from the working folder or repository). Workers advise; you decide. Ask your human before answering a question meant for them. A delivery result never means the work finished; wait for `DONE`. While you wait, end your turn: a worker's message wakes you, so build no watcher for results. Never poll or read another conversation's inbox.

For a team, launch one worker per role, each with its own name and task, and keep each thread on that worker's `from` address. Each worker owns its task and may split it among its own native subagents; their questions reach you through the worker.

## Close

Save what must outlive the panes, then run `rex-agents cleanup` before your final answer. It closes every pane you own, unfinished work included, and never your own pane. It prints `closed`, `gone`, and `uncertain` JSON and exits 1 when anything is uncertain; retrying is safe. To stop one worker and keep the rest, run `rex-agents cleanup --name NAME`; never close worker panes with `rex block close`, which skips the ownership check. Claude `/clear` changes your identity, so close older workers by hand.

## Trouble

- A worker's Reason `ask_user`, or a Claude worker's AskUserQuestion, is refused by a hook that tells it to message you. A subagent's `ask_user` is refused too, and the subagent returns the question to its worker. Codex `request_user_input` has no hook; only the task's rules stop it.
- A worker blocked on a permission prompt pops up a Reason notification to the human. The prompt still waits in its pane.
- `No Rex pane known for this conversation`: pass `--session` and `--block` as top-level options, before the subcommand: `rex-agents --session "$REX_SESSION" --block "$REX_BLOCK" launch …`. After `launch` they are rejected as unrecognized arguments.
- `Owned workers cannot launch nested workers`: you are a worker. Message your driver instead.
