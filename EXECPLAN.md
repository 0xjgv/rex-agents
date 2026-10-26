# Connect interactive agents through Rex and Reason

This living ExecPlan follows `/Users/juan/.codex/PLANS.md`. Keep Progress, Surprises & Discoveries, Decision Log, and Outcomes & Retrospective current.

## Purpose / Big Picture

Build `/Users/juan/Code/rex-agents` so Juan can discover Claude Code and Codex conversations, send messages through Reason, open interactive workers in background Rex panes, and navigate to their panes. Reason remains the only messaging service. The project stores only the association between a native conversation ID and a Rex pane. This supports autonomous work while keeping conversations inspectable.

## Progress

- [x] (2026-10-26) Read workspace rules, ExecPlan guidance, installed Rex guide, and prior Reason removal evidence. Named the current Rex session.
- [x] (2026-10-26) Verified APIs against Rex 0.0.1792787366-g623b2d, Claude 2.1.310, Codex 0.164.0, and Reason source 5a6d0835868e1e648bed9144360d29455ebe8e6f.
- [x] (2026-10-26) Implemented CLI, registry, installer, six Lua actions, and agent skill.
- [x] (2026-10-26) Initial 28 isolated tests passed. Temporary Rex configuration passed with six actions, zero bindings, and zero diagnostics. More live-discovered regressions may follow.
- [x] (2026-10-26) Enabled Reason for Claude/Codex through supported setup, installed locally, and validated seven Rex actions with no bindings or diagnostics.
- [x] (2026-10-26) Verified interactive Claude/Codex launch, exact identity, bidirectional messages, matching reply IDs, idle FYI and busy delivery.
- [x] (2026-10-26) Added the requested default-off navigation toggle. App navigation remains disabled by explicit user instruction; enabled navigation is fixture-tested only.
- [x] (2026-10-26) Changed workers and action prompts to background panes, per the user's later instruction; live tab count remained unchanged.
- [x] (2026-10-26) Wrote ONBOARDING.md and VERIFICATION.md; documented deferred live remote validation and unresolved Reason account enrollment.
- [x] (2026-10-26) Claude reviewed through Reason; six findings were fixed and three code simplifications applied. The final 55 tests pass normally and with inherited Claude/Codex identity variables.

## Surprises & Discoveries

The tool shell does not inherit the Rex variables advertised by the terminal context. `rex whoami --json` confirms the local endpoint and session existence. Explicit supplied IDs work. The Reason engine is absent, matching the previous removal. Do not invoke commands that bootstrap it before isolated tests pass.

## Decision Log

The current user request explicitly authorizes re-enabling Reason after implementation and tests; the previous removal describes starting state, not a permanent prohibition. Ordinary integration commands must invoke the installed engine directly and fail when absent, never trigger wrapper installation.

Native conversation IDs, never directory or display names, associate a conversation with a pane. Sender verification requires Reason's `is_me` result after supplying the native identity. Names are user-facing target selectors only and ambiguity is an error.

## Outcomes & Retrospective

The integration is implemented and installed. Local delivery, replies, and background panes work. Automated behavior coverage has grown to 55 tests. Navigation is intentionally off and Rex Remote Control remains disabled, per the user. Live remote validation is deferred until a second machine is enrolled. Claude completed the requested review through Reason. All six findings are reconciled in reviews/README.md; the original review is preserved beside it.

## Context and Orientation

This is a new standalone project, outside the Corgea checkout. Python uses only its standard library; Lua runs inside Rex. A locator is a JSON file mapping agent type and native session ID to Rex server, session, and block IDs. Reason's roster is the authoritative set of active agents and current messaging addresses. A stale or absent locator must not disable messaging. The initial machine has Rex, Claude, Codex, and the Reason wrapper, but no Reason engine or Rex configuration directory.

## Plan of Work

First inspect installed CLI help and primary upstream source to pin exact APIs. Create `rex_agents/` modules for command dispatch, Reason/Rex interaction, atomic locator files, and additive installation. Add `bin/rex-agents`, `lua/rex_agents.lua`, `skill/SKILL.md`, and `tests/`. Keep external commands as argument arrays. A launch passes task text once as the initial prompt, opens a background split beside the launching pane, preserves current focus, and returns pane IDs before registration. Hooks record native IDs without waiting for Reason and preserve all existing hooks. Removal deletes only owned entries and cache, preserving Reason and running workers.

Implement short Lua actions for list, send, focus, launch, and local registry export through the existing Rex authenticated connection. Missing action arguments open terminal prompts instead of blocking the action. Remote machine discovery uses configured Rex hosts and per-host registry exports; no new listener is permitted.

## Concrete Steps

Work in `/Users/juan/Code/rex-agents`. Run `python3 -m unittest discover -s tests -v` after implementation. Run `bin/rex-agents doctor` before and after setup. Only after isolated tests pass, back up affected configuration, run Reason's supported Claude/Codex setup, run `bin/rex-agents install`, and run `rex config check`. Record exact verified setup commands here after API discovery. Use Rex to launch test workers with harmless bounded prompts in this project, then inspect their roster identity and panes.

## Validation and Acceptance

Tests must distinguish two sessions in the same repository; survive names changing and resumed native IDs; reject missing sender identity, ambiguous targets, inactive sessions, closed panes, and duplicate worker names; preserve literal messages and paths; propagate send failures and reply IDs; recover launch failures without duplicate tasks or panes; preserve unrelated configuration across repeated install/uninstall; and route remote fixture results correctly even when navigation is unavailable. Live validation must show Claude and Codex workers registered, messages exchanged in both directions, replies in the correct conversations, busy/idle behavior distinguished from task completion, and successful pane navigation. `rex config check` must pass. Tests alone do not establish live messaging success.

## Idempotence and Recovery

Back up live configuration before setup and installation. Install and uninstall must be repeatable and operate only on exact owned entries. Atomic writes prevent partial locator files. Check pane state before retrying an uncertain launch. Never consume or acknowledge agent inboxes. Leave Reason and active sessions intact on uninstall. Preserve failed verification evidence and report external limitations explicitly.

## Artifacts and Notes

The initiating session is `session:01a177ab-d6f4-73e8-94dd-44888dbd601b`, block `block:01a177b1-8f84-7cc5-94dc-c77f11a4ba42`, endpoint `unix:///Users/juan/Library/Application%20Support/rex/server.sock`. These are verification context, not defaults to embed in the application.

## Interfaces and Dependencies

Public commands are `list [--json]`, `send TARGET --message-file FILE [--fyi]`, `launch claude|codex --name NAME --cwd DIR [--task-file FILE] [--host HOST]`, `focus TARGET`, `doctor`, `install`, and `uninstall`. Internal hook, registry export, worker bootstrap, and prompt commands may support these interfaces. Dependencies are Python, Rex, the Reason engine, and the requested native agent CLI. No Python packages or additional background services are required.

Revision 2026-10-26: Created the executable plan before implementation. API details and measured evidence will be added as discovered.

Revision 2026-10-26: Reason roster has no native ID field. Resolve each locator by calling `who --json` with `REASON_NETWORK_AGENT` and `REASON_NETWORK_SESSION`, requiring one local active `is_me`. Send explicitly with `--from agent:native-id` to prevent Reason's terminal fallback. `--reply-to` preserves reply IDs. Setup begins only after isolated tests and Lua validation passed.

Revision 2026-10-26: The Reason wrapper installed engine 0.12.13 and initially wired all detected integrations, then failed cloud enrollment: "this link names only this computer, which can't let itself in". Continue through the engine's supported interactive setup to retain only Claude/Codex. The prior launchd disable requires explicit `launchctl enable gui/501/com.reasonmachines.network`. Team enrollment remains separate from local delivery and will be reported.

Revision 2026-10-26: Live Codex 0.164.0 shared-server execution drops all Rex environment variables, preventing locator hooks from associating the native session with its pane. Codex workers therefore use its supported `--no-daemon` option. Model and permission settings remain inherited. Hook trust must occur after the final additive installation, because native trust hashes include the hook definition. Reason rejects self-addressed sends; use two conversations for bidirectional verification.

Revision 2026-10-26: User requested a default-off navigation toggle, background panes instead of tabs, an onboarding document, and a Claude review through the new capability. The toggle uses the existing installation manifest rather than another state file. ONBOARDING.md explains the full workflow; README.md now points to it instead of duplicating the guide. VERIFICATION.md separates measured local messaging from unverified app navigation and remote behavior.

Revision 2026-10-26: Reconciled Claude's six findings: nested hooks cannot take a parent pane through inherited identities; closed Rex sessions no longer permanently reserve names; subprocess tests isolate inherited identity; discovery no longer renames other conversations; remote request timeouts honor their budget; and unreachable Rex host discovery preserves the Reason roster. Applied the suggested small code removals. Final automated evidence covers 55 tests, including an inherited-identity run.

Revision 2026-10-26: An agent without a live native-ID locator must supply its Rex session and pane explicitly. This prevents an old shared-server conversation from splitting whichever unrelated pane the user currently has focused. A regression test brings the final count to 55.
