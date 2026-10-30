---
name: rex-agents
description: Work with other models as a team. Launch opus, fable, sonnet, haiku (Claude Code) or sol, terra, astra, luna (Codex) as interactive workers in Rex panes, collaborate with them through Reason, and close them when done. Use when the user asks to work with, consult, or delegate to one of these models, or to a team of agents.
---

# Rex agents

You drive. Each worker is a native interactive Claude Code or Codex conversation in an unfocused Rex pane, in columns on the right of your tab. You pick its model and effort, talk with it through Reason, make the decisions, and close it. Only you talk to the human.

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

The model picks the harness: `claude-*` runs Claude Code, `gpt-*` runs Codex. Use any model, harness, or effort the user names. Fill what they leave open from the one role below that fits the task: take the first model in its preference order that fits the user's instructions, and the role's effort. For `advise`, use the harness other than yours unless the user says otherwise. A role may pick either harness. These are defaults, not measured rankings.

| Role | Fits | Model preference | Effort |
|---|---|---|---|
| `implement` | Writing or changing code, including fixing a bug whose cause is unknown | sol → opus | `xhigh` |
| `validate` | Checking finished work for correctness: review, tests, verification | opus → astra | `xhigh` |
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

Names are unique across Rex: 1–64 letters, digits, `_`, or `-`. The task is passed once, literally; no worktree is created. The result says `registration: pending`; the worker is ready when it messages you. On `Launch outcome uncertain`, look for its label in `rex block ls --json` before retrying.

## Collaborate

Every task states:

1. Your Reason address. In Claude, take the `is_me` row of `reason-network who --json`. In Codex, use MCP `list_team`; the CLI fails in the Codex sandbox.
2. The goal, files, constraints, and the shape of the answer you want.
3. The rules: reply with MCP `send_message` to that address; send questions there, never to AskUserQuestion, `request_user_input`, or Reason `ask_user`; launch no workers, leave the Rex session's name alone, and message no one else; say `DONE` when finished.

Then work in rounds. Reply to the worker's `from` with `reply_to`: share drafts, ask for critique, push back. Attach drafts and long results with `send_message` `files` (up to 10 text files, 256 KB each, from the working folder or repository). Workers advise; you decide. Ask your human before answering a question meant for them. A delivery result never means the work finished; wait for `DONE`. While you wait, end your turn: a worker's message wakes you, so build no watcher. Never poll or read another conversation's inbox.

For a team, launch one worker per role, each with its own name and task, and keep each thread on that worker's `from` address. Workers cannot launch workers.

## Close

Save what must outlive the panes, then run `rex-agents cleanup` before your final answer. It closes every pane you own, unfinished work included, and never your own pane. It prints `closed`, `gone`, and `uncertain` JSON and exits 1 when anything is uncertain; retrying is safe. Claude `/clear` changes your identity, so close older workers by hand.

## Trouble

- A worker's Reason `ask_user`, or a Claude worker's AskUserQuestion, is refused by a hook that tells it to message you. Codex `request_user_input` has no hook; only the task's rules stop it.
- A worker blocked on a permission prompt pops up a Reason notification to the human. The prompt still waits in its pane.
- `No Rex pane known for this conversation`: pass `--session` and `--block` as top-level options, before the subcommand: `rex-agents --session "$REX_SESSION" --block "$REX_BLOCK" launch …`. After `launch` they are rejected as unrecognized arguments.
- `Owned workers cannot launch nested workers`: you are a worker. Message your driver instead.
