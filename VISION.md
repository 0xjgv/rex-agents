# Vision: task owners

Draft, 2026-10-30. Phase 1 shipped and passed a live run the same day; the rest is direction. `ONBOARDING.md` and `VERIFICATION.md` describe what runs today.

## Goal

A driver hands a task to a task owner and gets a result back. The task owner is a native Claude Code or Codex conversation in a Rex pane. It keeps every native capability: tools, skills, MCP servers, and its own subagents. It splits the work among subagents as it sees fit. Questions climb to the driver. Only the driver talks to the human.

```text
human
  ▲  AskUserQuestion
driver                     the one conversation that talks to the human
  ▲  Reason send_message
task owner (Rex pane)      a full native conversation; one level of panes
  ▲  final reply, then resume
subagents (in process)     the harness's own; the harness sets their depth
```

Questions and results travel up. Answers travel back down the same path.

## Terms

- **Driver.** The conversation the human talks to. It launches task owners, answers or relays their questions, decides, and closes their panes.
- **Task owner.** A pane labeled `rex-agents:<owner>:<name>` running native Claude Code or Codex. The code calls it a worker.
- **Subagent.** A child the task owner spawns with its harness's own tool: Claude's Agent tool or Codex `spawn_agent`. It runs inside the task owner's process and shares its pane.
- **Human.** Answers through the driver, and answers permission prompts in the pane that raised them.

## Principles

1. **One level of panes, native depth below.** Rex owns the first level, and the harness owns everything under it. A task owner cannot launch panes, but it can spawn subagents.
2. **Questions climb one level at a time.** Each level answers what it can and forwards the rest: subagent → task owner → driver → human.
3. **Answers reach the asker through the asker's handle.** Reason delivers to conversations, and a subagent is not one. So a subagent returns its question in its final reply, and the task owner resumes it by agent or thread ID. Between task owner and driver, the Reason message ID and `reply_to` are the handle.
4. **Pause, don't hold.** A blocked asker ends its turn and leaves a resume handle. No tool call blocks while it waits for a human.
5. **Approvals stay where they happen.** A permission prompt waits in the pane that raised it, and a notification tells the human where it is. Reason cannot answer a pane prompt.
6. **Native over built.** No daemon, SDK host, MCP server, or polling. Use what the harnesses and Reason already provide.
7. **Every pane visible, every pane owned.** The human can watch and type into any task owner. Cleanup closes what the driver owns, all at once or one worker by name. Subagents die with their pane (verified in both harnesses).

## Today

What works:

- Task owners launch with full native capabilities. Nothing in rex-agents blocks subagents. Codex 0.166.0 ships `multi_agent` as stable and on.
- A task owner's own questions go to the driver. The hook denies AskUserQuestion and Reason `ask_user` with `RELAY`.
- A task owner cannot launch panes. The nesting guard refuses: a Claude subagent shares its task owner's `REX_BLOCK`, and a Codex subagent has no locator.
- Since Phase 1, an owned worker gets `OWNER` at SessionStart. A subagent's Reason `ask_user` is denied with `RETURN`, the subagent puts the question in its final reply, and the worker relays it and resumes the subagent. Both harnesses passed this live.

- A field test (two rpi workers, sol and sonnet) nested subagents two levels deep in both harnesses with no leak to the human. The driver then approved a design gate itself, so `gamma`'s driver protocol now says approval gates always go to the human. Stopping one worker needed raw `rex block close`, so `cleanup --name NAME` now closes one owned worker.

The gap Phase 1 closed: `hook()` used to return early on any payload carrying `agent_id`. A subagent's `ask_user` reached the human past the driver, and its permission prompts sent no notification.

Harness facts this design rests on (Claude Code 2.1.314, Codex 0.166.0):

| Fact | Claude Code | Codex |
|---|---|---|
| Subagent hook payload carries `agent_id` | documented; the hook fired live | in the hook schema; the hook fired live |
| Subagent `session_id` is the parent's | not documented; the subagent transcript records the parent's `sessionId` | documented |
| Native question tool inside subagents | AskUserQuestion removed | `request_user_input` refused for non-root agents |
| Subagent inherits Reason MCP tools | documented; seen live | seen live (`mcp__reason_network__ask_user`) |
| Subagent permission prompt shows in the parent's pane | documented | documented, labeled by thread |
| Parent can resume a subagent | `SendMessage`; Explore and Plan cannot resume | `send_input`, `resume_agent` (v1); `followup_task` (v2) |
| SessionStart fires for subagents | not documented; SubagentStart fires | no; SubagentStart fires |
| Reason CLI works in the tool shell | yes | no: `could not start the network daemon` (verified) |

## Landscape

Research agents read vendor docs and source on 2026-10-30. Links are under Sources. None of this was re-checked live.

### Claude

| Product | Shape | Thread capabilities | Results | Questions and approvals |
|---|---|---|---|---|
| Projects (redesigned, beta since 2026-09-17) | A coordinator conversation starts parallel threads, in the cloud or locally through Remote Control | Full Claude Code session that can use subagents. Cloud threads skip repo agents, skills, hooks, and permission rules | Stay in the thread: branch, PR, Library tab | Go straight to the human ("Waiting on you"). Telling the coordinator to go ahead does not reach the thread |
| Chat Projects (claude.ai) | Shared knowledge and instructions | No threads | — | — |
| Subagents | Agent tool; same process; background by default | Inherited tools minus AskUserQuestion and Workflow. Nest up to 3 levels (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`) | Final message | Permission prompts go to the human in the main session. No question tool |
| Agent teams (experimental) | Lead spawns teammates as separate instances, in-process or in panes | Full sessions. No nested teams | `SendMessage` mailboxes and a shared task list | Teammate permission prompts appear in the lead's session |
| Background sessions (`claude --bg`) | Separate local processes under a supervisor | Full; edits go to a worktree | To the human: state row, branch, PR | "Needs input" goes to the human. Dialogs need `claude attach` |
| Workflow tool | A script spawns subagents | Up to 16 at once | Script variables; only the final answer returns | No input mid-run. Permission prompts go to the human |
| Managed Agents (beta) | Coordinator spawns session threads | Own tools and MCP servers. Up to 25 child threads | `agent.thread_message_received` | Permission requests go to the client, not the coordinator |
| Multi-agent research system (2025 post) | Lead runs subagents synchronously | Own tools | Findings go to the lead | The lead cannot steer its subagents |

### Coding tools

| Tool | Shape | Results | Questions and approvals |
|---|---|---|---|
| Codex CLI multi-agent | Child threads in the same session. v1 tools: spawn, send_input, resume, wait, close. v2 tools: spawn, send_message, followup_task, wait, interrupt, list. v1 enforces `agents.max_depth` | Final message goes to the parent | Approvals go to the human, labeled by thread |
| T3 Code `delegate_task` | A child thread gets only the task prompt. Children can delegate further, and cancelling a child cancels everything under it | Summary when the parent waits, or a notification | A pending question ends the wait (`hasPendingQuestion`). The parent answers or asks the user. Approvals are not routed |
| Devin managed Devins | A coordinator spawns children, each in its own VM | The coordinator wakes when a child finishes or needs input | The human can message any child |
| Cursor | Subagents share the checkout or get a worktree or VM; one level. Cloud agents run in VMs | Final message, or branch and PR | Not documented |
| Factory droids | Task tool; fresh context; no nesting | One final message | AskUser is disabled, so a blocked subagent reports back |
| GitHub Copilot | Coding agent runs on Actions. CLI `/fleet`. VS Code subagents do not nest by default (opt-in depth up to 5) and lack the clarifying-question tool | PR | Not documented |
| Amp | Task subagents. The main agent can send a running subagent new tasks | Final summary | The human cannot guide subagents directly |
| Conductor, Claude Squad | Driven by a human; one worktree per session; attach through tmux | Diff, PR | Go to the human |

### Frameworks and protocols

| Name | What matters here |
|---|---|
| Microsoft Agent Framework 1.0 | `request_info` mints a `request_id`. A sub-workflow's request goes to the parent executor by default, or to the outer caller with `propagate_request=True`. The closest match to this design |
| A2A 1.0 | Task states: SUBMITTED, WORKING, INPUT_REQUIRED, AUTH_REQUIRED, COMPLETED, FAILED, CANCELED, REJECTED. The client answers with the same `taskId`. Results come back as Artifacts. A follow-up to a finished task starts a new task |
| MCP 2026-07-28 | `InputRequiredResult` ends the call. The client retries with answers keyed by IDs the server minted. Sampling is deprecated. The tasks extension adds states |
| LangGraph | Interrupts propagate to the top graph, and `Command(resume=…)` resumes. A parent answers only if you code it to |
| OpenAI Agents SDK | A handoff transfers control; agents-as-tools keep it with the caller. Nested approvals surface on the outer run, for the human only |
| Google ADK 2.0 | Task-mode agents must be leaves and end with `finish_task`. They may ask only for clarification |
| CrewAI | A manager agent delegates. `human_input` prompts the user |

### Lessons

1. **Questions split two camps.** Claude Projects, Codex, the OpenAI Agents SDK, and LangGraph send them to the human. T3 Code, Devin, and Microsoft Agent Framework's default route them to the parent. Rex agents joins the parent camp.
2. **No tool routes approvals through the parent agent.** Projects keeps prompts in the thread, T3 Code does not route them, and Managed Agents send them to the client. Agent teams come closest: teammate prompts show in the lead's session, but the human still answers. This supports principle 5.
3. **Blocked children pause with a handle the asker minted:** A2A `taskId`, MCP `inputRequests` keys, LangGraph interrupt IDs, Microsoft Agent Framework's `request_id`. This supports principles 3 and 4 and argues against a blocking ask.
4. **Children start with only their prompt and return one final message.** Task files must stand on their own.
5. **Depth is capped by convention.** One level in Cursor, Factory, and VS Code, three in Claude by default, and ADK makes task agents leaves.
6. **Isolation means a worktree per thread or a VM.** Worktrees: background sessions, Conductor, Claude Squad, Cursor. VMs: cloud Projects threads, Devin, Jules, Copilot.
7. **Watching and attaching are features everywhere.** A Rex pane already provides both.

## Approaches considered

| # | Approach | Verdict | Why |
|---|---|---|---|
| 1 | Escalation ladder: a subagent returns its question, and the task owner relays it and resumes the subagent | Chosen | No new infrastructure. Works in both harnesses. Matches lessons 1–3 |
| 2 | Blocking ask: `reason-network send --from <you>/q-<id>`, then `listen --as q-<id> --wait N` | Not now | The Codex sandbox blocks the Reason CLI (verified). Claude's Bash tool times out at 10 minutes, and `listen` gives up after 600 s by default. It holds a live wait (lesson 3) |
| 3 | Host-run headless workers: `claude -p --permission-prompts host`, Codex `exec` or the app server | Rejected | Needs a host process per worker. Loses interactive panes |
| 4 | Each harness's own teams: agent teams, background sessions, Codex v2 | Not the base | Single-harness only. Two cleanups. Keep watching |
| 5 | Pre-approve work and isolate it: worktree plus a permissive mode | Candidate, opt-in | Removes most pane stalls. Costs a flag and the worktree lifecycle |
| 6 | Shared question files under a per-worker directory | Rejected | A second channel. Reason messages already carry files |

## Direction

### Phase 1: route subagent questions (done, verified live 2026-10-30)

- `hook()`: keep ignoring cross-harness children. Let `agent_id` payloads reach `alert()` for blocking events, and keep skipping SessionStart for them.
- `alert()`: in an owned pane, deny a subagent's `ask_user` with a new reason: "End your turn and put the question in your final reply. The agent that launched you will relay it." Keep `RELAY` for the task owner itself.
- Permission prompts stay as they are: notify the human, and the prompt waits in the pane.
- Skill task template gets one rule: "Use native subagents freely. Tell them to return questions in their final reply. Relay those questions to me, then resume the subagent with my answer."
- Tests:
  - A subagent's `ask_user` is denied with the subagent reason.
  - A subagent's permission prompt sends a notification.
  - A subagent's SessionStart writes no locator.
- Live checks: the open questions below.

### Phase 2: a report-back contract (skill text only)

Borrow A2A's states as message prefixes, so the driver can tell messages apart at a glance:

- `QUESTION:` the task owner needs an answer and stops until the driver replies.
- `DONE:` the result, with files attached.
- `FAILED:` what blocked the work and what the task owner tried.

Today the skill uses only `DONE`.

### Phase 3: fewer stalls (opt-in)

A launch option that gives each task owner a worktree and a permissive mode: Claude `acceptEdits` or auto mode, Codex `workspace-write` with no approval prompts.

- **Buys:** most pane stalls disappear, and parallel task owners stop colliding in one checkout.
- **Costs:** a new flag, a worktree lifecycle that cleanup must handle, and weaker guard rails.

Build it only if pane stalls prove to be the bottleneck.

### Watch

- **Claude Projects:** threads whose prompts route to the coordinator, or an API for local threads.
- **Agent teams:** if it leaves experimental and can run Codex workers.
- **Codex v2:** `followup_task` and `agent_message_board`.
- **Reason:** an `ask_user` that can target an agent would give a blocking ask with signed answers.

## Non-goals

- A daemon, an SDK host, an MCP server, or polling.
- A second level of panes.
- Routing permission prompts through the driver.
- Automatic cleanup on Stop or SessionEnd.

## Open questions

1. Claude: does a subagent's hook payload carry the parent's `session_id`? The subagent transcript records the parent's `sessionId`, but no live run has logged the payload itself. A notification from a subagent's permission prompt would settle it.
2. Claude: does PermissionRequest carry `agent_id` for subagents? The docs don't say. Either way, the prompt now reaches `alert()`. Not exercised live: auto mode raised no prompt.
3. ~~Codex: does a subagent see `mcp__reason_network__ask_user`?~~ Yes, in Codex 0.166.0.
4. ~~Does a subagent see the deny reason and act on it?~~ Yes, in both harnesses: each returned the question, and resuming it delivered the answer.
5. ~~Do foreground and background subagents die when their pane closes?~~ Yes: after each pane closed, no worker process remained, in either harness.
6. Codex v2 records subagent depth but may not enforce it (one user's reading of the code). Should the task template cap depth?
7. Claude's Explore and Plan subagents cannot resume, so a question from one costs a fresh subagent. Is that acceptable?

## Sources

Claude:
- https://claude.com/blog/projects-redesigned
- https://code.claude.com/docs/en/claude-projects.md
- https://support.claude.com/en/articles/9517075-what-are-projects
- https://code.claude.com/docs/en/sub-agents.md
- https://code.claude.com/docs/en/hooks.md
- https://code.claude.com/docs/en/agent-teams.md
- https://code.claude.com/docs/en/cross-session-messaging.md
- https://code.claude.com/docs/en/agent-view.md
- https://code.claude.com/docs/en/workflows.md
- https://code.claude.com/docs/en/claude-code-on-the-web.md
- https://code.claude.com/docs/en/agent-sdk/subagents.md
- https://platform.claude.com/docs/en/managed-agents/multiagent-orchestration
- https://www.anthropic.com/engineering/multi-agent-research-system

Codex:
- https://learn.chatgpt.com/docs/agent-configuration/subagents
- https://learn.chatgpt.com/docs/hooks
- https://developers.openai.com/api/docs/guides/responses-multi-agent.md
- https://github.com/openai/codex/issues/16475
- https://github.com/openai/codex/issues/22268
- https://github.com/openai/codex/pull/22782
- https://github.com/openai/codex/issues/32027

Other tools:
- https://raw.githubusercontent.com/pingdotgg/t3code/main/docs/orchestration-v2/orchestrator-mcp-server.md
- https://cognition.com/blog/devin-can-now-manage-devins
- https://cursor.com/docs/subagents
- https://docs.factory.com/harness/subagents
- https://code.visualstudio.com/docs/copilot/agents/subagents
- https://ampcode.com/docs/models-and-subagents

Frameworks and protocols:
- https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop
- https://a2a-protocol.org/latest/specification/
- https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr
- https://docs.langchain.com/oss/python/langgraph/use-subgraphs
- https://openai.github.io/openai-agents-python/human_in_the_loop/
- https://adk.dev/workflows/collaboration/
