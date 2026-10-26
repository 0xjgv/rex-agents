# Verification record

Verified locally on 2026-10-26 with Rex `0.0.1792787366-g623b2d` (API revision 7), Claude Code `2.1.310`, Codex `0.164.0`, Reason Network `0.12.13`, and Python's standard library. Reason source commit `5a6d0835868e1e648bed9144360d29455ebe8e6f` supplied the API contract; installed CLI help and live behavior were checked separately.

## Automated checks

`python3 -m unittest discover -s tests -v` passes 55 behavior tests. They cover exact identity in a shared repository, renaming, resuming and stale end hooks, missing registration, conflicting inherited identities, closed panes, remote host failures, ambiguous targets, failed sends, explicit native senders, literal subprocess arguments and stdin, duplicate names and pending launches, definite failure retries, uncertain creation, background pane anchoring, one initial prompt, Codex terminal context, additive repeated install/removal, mixed hook groups, conflicts, invalid JSON, inert hooks after uninstall, and the persisted navigation toggle. Added regressions cover nested-agent mapping ownership, a closed session's launch reservation, discovery without Rex, read-only name discovery, and remote timeout diagnostics. The suite also passed with inherited Claude and Codex identity variables in its parent environment.

`rex config check` accepts seven actions, zero key bindings, and zero diagnostics. The installer was exercised repeatedly against live configuration and isolated configurations containing unrelated hooks and actions. Removal was exercised in isolated configurations, preserving unrelated settings and leaving no active locator hooks. `rex-agents doctor` reports installed dependencies, working Reason integration, loaded actions, and verified identities for active workers.

## Live messaging

Claude conversation `44489f22-8916-40ac-8c75-f430110ab740` and Codex conversation `01a177d4-eda6-7ce0-8bf3-8ad45520b151` both ran interactively in Rex and acquired exact native-ID mappings.

Claude sent request `01M5VXCWS7WEXSY222K3661VHC` to `0xjgv/rex-test-codex` through the new CLI. Codex replied through the CLI with message `01M5VXDAZE3KJ8BJ9146FJPWP3`, body `CODEX_ACK_REX_ROUNDTRIP_1026`, and `reply_to="01M5VXCWS7WEXSY222K3661VHC"`. Claude's conversation displayed the correct sender, body, and reply ID. The integration did not poll or acknowledge either inbox.

While Codex was idle with zero unread messages, FYI message `01M5VXHVZ4DVHM4EHRNBWH0NWY` was sent. A later roster query still showed `idle` and one unread message. A normal request then woke the conversation. Its final answer reproduced the queued multiline message, including quotes, literal `$(printf literal)`, backticks, `$HOME`, and a path with spaces.

During a controlled 25-second shell wait, Reason reported Codex as `busy`. Message `01M5VXK1BMBXSCPCEPZNSCFGBJ` returned a queued delivery result. After the wait, Codex sent acknowledgment `01M5VXM1JZ7V693W09TT5DDZ0A` to Claude. Delivery acceptance and completed work were observed separately.

Reason rejected an attempted self-send. This is an upstream recipient-selection rule, not evidence of broken identity. Subsequent tests used two distinct conversations.

## Pane behavior and navigation

The user's later instruction changed worker and prompt creation from tabs to background panes. Live launches returned `anchor_id` and `split_ids`; the review worker occupied the same window as the launching pane, and the tab count stayed at four. A repeated launch with the same pending name failed without increasing pane count. Tests also assert `--focus=false` and the explicit anchor block. The live List Agents action opened a background pane at the explicit anchor, displayed the Reason roster, and left the tab count unchanged; its temporary pane was closed after inspection.

An attempted app focus returned: `Rex.app is not accepting actions. Turn on Remote Control in its Settings under Rex Server.` The user explicitly requested leaving that setting disabled and adding a navigation toggle. Navigation now defaults off, and disabled focus fails before any Rex action. The preference persists across installation. **Enabled app navigation remains fixture-tested, not live-validated.** No claim of live app focus success is made.

## Installation findings and remaining limits

Reason's wrapper installed the engine and initially configured detected agents, then failed account enrollment with `this link names only this computer, which can't let itself in`. The engine's supported interactive setup retained Claude Code and Codex and removed its additions for Cursor, OpenCode, and cloud Reason. The prior launchd disable was reversed. `auto_update = false` was preserved. Local messaging works; the machine is not enrolled in a Reason team.

Codex's shared app server did not preserve Rex environment variables for the integration's hook context. Using the supported `--no-daemon` option allowed the native startup hook to create the exact locator. Tool shells may still omit Rex variables; subsequent commands can recover location through the native-ID locator. Hook trust must occur after configuration settles, since changed definitions invalidate native trust hashes.

No remote Rex hosts are configured. Remote routing, unavailable-host behavior, and local-app versus remote-pane selection have controlled fixture coverage. Live cross-machine messaging and navigation remain deferred until another machine is enrolled.

Local raw evidence is under `.verification/`, excluded from version control. The named verification conversations and pane IDs are historical observations; closed panes are not treated as live navigation targets.

## Claude review through the integration

The requested review ran in an interactive Claude pane and arrived through Reason. It found six issues and three small code simplifications. All six were addressed and tested. See reviews/README.md for the resolution and reviews/2026-10-26-claude.md for the unmodified report.
