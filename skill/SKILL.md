---
name: rex-agents
disable-model-invocation: true
description: Work with other models as a team. Launch opus, fable, sonnet, haiku (Claude Code) or sol, terra, astra, luna (Codex) as interactive workers in Rex panes, collaborate with them through Reason, and close them when done. Use when the user asks to work with, consult, or delegate to one of these models, or to a team of agents.
---

# Rex agents

You drive. Each worker is a native interactive Claude Code or Codex conversation in an unfocused Rex pane, placed beside you or in a named group. You pick its model and effort, talk with it through Reason, make the decisions, and close it. Only you talk to the human.

Never rename a Rex session, tab, or pane: no `rex session rename`, even when Rex's SessionStart hook says to name the session. The launch options set the session name, and the human owns it.

## Pick model and effort

| Name | Model | Runs in |
|---|---|---|
| opus | `claude-opus-5-5` | Claude Code |
| fable | `claude-fable-5-2` | Claude Code |
| sonnet | `claude-sonnet-5-5` | Claude Code |
| haiku | `claude-haiku-5-5` | Claude Code |
| sol | `gpt-6.2-sol` | Codex |
| terra | `gpt-6.1-terra` | Codex |
| astra | `gpt-6.2-astra` | Codex |
| luna | `gpt-6-luna` | Codex |

Claude models run in Claude Code and GPT models run in Codex. Honor any model, harness, effort, worker count, or cross-harness comparison the user requests. For choices the user leaves open, start with the role defaults below. You may change the model, harness, effort, or worker count to fit the task. When you change a default, give the user a one-sentence reason with your picks.

A plus marks a default pair. An arrow lists preferences for a single worker. For `advise`, prefer the harness other than yours.

| Role | Assignment | Workers | Effort |
|---|---|---|---|
| `implement` | Split independent changes by file ownership and implement in parallel. For shared code, Sol implements and Opus reviews the resulting diff at `high` effort. | sol + opus | `medium` for implementation |
| `validate` | Checking finished work for correctness: review, tests, verification | opus → astra | `high` |
| `plan` | Give both the same brief in parallel. Each drafts a plan independently, then the driver compares them and recommends an approach. | opus + astra | `xhigh` |
| `advise` | Decisions, trade-offs, and second opinions | astra → fable | `high` |
| `research` | Give both the same read-only question in parallel. Each returns independent evidence, then the driver reconciles their findings. | terra + sonnet | `high` |
| `commit` | Commits, PR text, and other small mechanical tasks | terra → sonnet | `medium` |

Map each short name through the model table and tell the user your picks and efforts, such as "Terra alone at high effort because this question can be settled by tracing one code path." Always pass `--effort`: `low`, `medium`, `high`, `xhigh`, or `max`; Codex also takes `ultra`. Launch each selected model in its own Rex pane, including workers on your own harness.

## Launch

Write the task to a file, then:

```sh
rex-agents launch --name sol-plan --cwd /absolute/project --model gpt-6.2-sol --effort high --task-file /path/task.txt
```

Names are unique across Rex: 1–64 letters, digits, `_`, or `-`. The task is passed once, literally; no worktree is created. The result says `registration: pending`; the worker is ready when it messages you. On `Launch outcome uncertain`, look for its name in `rex-agents status` before retrying.

A Claude worker starts in its settings' permission mode and may stop on a prompt only the human can answer. Pass `--permission-mode MODE`, such as `bypassPermissions`, only when the user or your instructions ask for it.

`--disallowed-tools TOOL [TOOL ...]` removes built-in tools from a Claude worker. Their schemas leave every API request. Use it for workers that never need them, such as `Artifact` or `AskUserQuestion`.

`--env KEY=VALUE`, repeatable, sets a variable in the worker, Codex tool shells included. If a detached shell cannot find `rex` on PATH, set `REX_AGENTS_REX` to the absolute path of the installed Rex CLI for the launch and subsequent `rex-agents` commands, such as `REX_AGENTS_REX="/absolute/path/to/rex" rex-agents launch …`.

When driving from Codex, add `--group codex` unless the user requests another placement. The group label is supplied by the caller. Use `--group NAME` with any valid name to create or join that named Rex session. Your conversation gets one tab, named after its first worker, and subsequent workers join surviving panes in that tab. Another conversation gets its own tab in the same session. Workers fill equal-height rows in launch order, with equal widths within each row. Four workers form a 2×2 grid, five form rows of 3+2, and seven form 3+2+2. Groups require your native conversation identity and work from outside Rex. The launcher reuses an existing session with that label, including when it has other tabs. If several sessions have the same label, choose a unique group label before launching. Cleanup closes only your workers and leaves other conversations' tabs open.

`--tab` opens the worker alone in a new, unfocused tab of your session, named after it. `--with WORKER` opens the worker in your worker WORKER's tab; in a `--tab` tab, every pane shares the tab as an equal grid. `--new-session` opens the worker in a new Rex session named after it; add its helpers there with `--with WORKER`. `--new-session LABEL` opens each worker in its own tab of one session named LABEL, created by the first. `--new-session` and `--with` also work from outside Rex. The placement options are mutually exclusive. Close any of them with `cleanup --name`; a tab closes with its last pane, and so does a `--new-session` session, even when its worker had already ended.

## Watch

A worker that exits sends no message. For a worker you keep across turns, run `rex-agents wait --name NAME` as a background command right after its launch (Claude Code: `run_in_background`). It blocks until that worker's pane ends, and its exit wakes you. It prints `ended` with an `exit_code` when the worker's program exited, `ended` with only a `block_id` when the pane was closed, as `cleanup` does, or `gone` when no pane of yours has that name. On an end you did not cause, tell the user, and if its work is still owed, reopen it on its own conversation with `rex-agents resume --name NAME --task "..."`: same placement and flags, full context. Its watchers and your `wait` do not come back; run `wait` again. `launch` with the same name starts a fresh conversation instead.

`rex-agents status` lists your live workers with their session and block. A worker missing from it has no pane. Read a worker's screen with `rex capture -s SESSION -b BLOCK --trim`.

## Collaborate

Every task states:

1. Your Reason address. In Claude, take the `is_me` row of `~/.reason/bin/reason-network who --json`; `reason-network` is often not on PATH. In Codex, use MCP `list_team`; the CLI fails in the Codex sandbox.
2. The absolute repository and working-directory paths, bounded goal, owned files, and an instruction not to revert other agents' edits. Include exact user constraints and settled decisions, required tools, expected outcome, required checks, and the evidence or unverified gaps to return.
3. The rules: reply with MCP `send_message` to that address; send questions there, never to AskUserQuestion, `request_user_input`, or Reason `ask_user`; launch no workers, leave the Rex session's name alone, and message no one else; say `DONE` when finished, with each command you ran and its exit code or output.
4. Relevant applicable skill names and absolute `SKILL.md` paths, with instructions to read them before acting. Include this handoff for native subagents too, especially fresh agents without inherited context; preserve any leaf worker's no-delegation constraint. Do not copy the whole skill library.

Resolve paths on the recipient's machine. A local absolute path does not establish that a remote worker can read it. If a needed skill is inaccessible, pass its essential instructions and identify the gap; stop dependent work when missing instructions or permissions prevent safe execution within scope. Loading a skill grants neither tools nor authority beyond the task. A native subagent returns results and questions to its worker, which relays them to the driver.

Then work in rounds. Reply to the worker's `from` with `reply_to`: share drafts, ask for critique, push back. Attach drafts and long results with `send_message` `files` (up to 10 text files, 256 KB each, from the working folder or repository). Workers advise; you decide. Ask your human before answering a question meant for them. A delivery result never means the work finished; wait for `DONE`. While you wait, end your turn: a worker's message wakes you, so build no watcher for results. Never poll or read another conversation's inbox.

Give each worker its own name and task, and keep each thread on that worker's `from` address. Each worker owns its task and may split it among its own native subagents; their questions reach you through the worker.

## Close

Save what must outlive the panes, then run `rex-agents cleanup` before your final answer. It closes every pane you own, unfinished work included, and never your own pane. It prints `closed`, `gone`, and `uncertain` JSON and exits 1 when anything is uncertain; retrying is safe. To stop one worker and keep the rest, run `rex-agents cleanup --name NAME`; never close worker panes with `rex block close`, which skips the ownership check. Claude `/clear` changes your identity, so close older workers by hand.

## Trouble

- A worker's Reason `ask_user`, or a Claude worker's AskUserQuestion, is refused by a hook that tells it to message you. A subagent's `ask_user` is refused too, and the subagent returns the question to its worker. Codex `request_user_input` has no hook; only the task's rules stop it.
- A worker blocked on a permission prompt pops up a Reason notification to the human. The prompt still waits in its pane.
- `No Rex pane known for this conversation`: use `--group NAME`, `--new-session`, or `--with WORKER` for placement from outside Rex. For placement relative to your own pane, pass `--session` and `--block` as top-level options, before the subcommand: `rex-agents --session "$REX_SESSION" --block "$REX_BLOCK" launch …`. After `launch` they are rejected as unrecognized arguments.
- `Owned workers cannot launch nested workers`: you are a worker. Message your driver instead.
