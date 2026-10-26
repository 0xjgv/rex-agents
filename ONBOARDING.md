# Rex agents onboarding

Rex agents connects interactive Claude Code and Codex conversations inside Rex. You can discover workers, give them tasks, exchange messages, and optionally navigate to their panes. Reason handles messaging. Rex handles terminals. This integration connects each native conversation to its exact pane.

## Current local setup

The integration is installed from `/Users/juan/Code/rex-agents`. The `rex-agents` command is linked into `~/.local/bin`. Claude Code and Codex have the integration skill and lifecycle hooks. Reason's native messaging integrations remain responsible for delivery.

Workers remain native interactive Claude Code or Codex conversations in **background split panes**. Owned launches alternate `right`, `below`, `right`, using the last successful launch direction, even after a worker pane is manually closed. A launch splits the newest live owned pane in the same server, session, and tab, or the driver's pane when none remains. Workers do not open new tabs or take focus. A split can resize the existing layout and end Rex's zoom mode.

**Navigation is off by default. Rex Remote Control is also disabled on this machine.** This lets you move among panes and tabs without agents moving your view. Messaging and worker launches work with navigation off. Live cross-machine behavior has not been validated; no second machine is enrolled.

## Choose the delegation route

When the worker uses the driver's own harness, prefer native subagents if they support the requested model and effort. A Codex driver can use its native subagent tool for Sol work without opening a pane. Claude can use its native subagents for supported Claude work. Native subagents return results through their harness and need no Rex cleanup.

Use `rex-agents launch` when crossing harnesses, when you explicitly want a visible interactive worker, or when native subagents cannot select the requested model and effort. Keep the requested model rather than silently substituting another. The CLI is an explicit pane launcher; the shared skill makes this routing choice before calling it.

## First use

Check the installation and discover the agents that Reason currently sees:

```sh
rex-agents doctor
rex-agents list
```

`list` shows the Reason address, machine, activity, repository, and available Rex pane. `list --json` also includes native conversation IDs and navigation diagnostics. An agent can receive Reason messages even when it has no accessible Rex pane.

Create a task file and launch a worker from a Rex terminal:

```sh
cat > /tmp/review-task.txt <<'TASK'
Read this project and identify three simplification opportunities.
Do not change files. Give file references and concrete reasons.
Finish with a final answer; do not wait in a loop.
TASK

rex-agents launch claude \
  --name reviewer \
  --cwd /Users/juan/Code/rex-agents \
  --model claude-opus-5-5 --effort xhigh \
  --task-file /tmp/review-task.txt
```

For cross-harness work, Codex drivers can call Claude workers with `--model claude-opus-5-5 --effort xhigh`. Claude drivers can call Codex workers with `--model gpt-6.1-sol --effort high`:

```sh
rex-agents launch codex --name helper --cwd /absolute/project \
  --model gpt-6.1-sol --effort high --task-file /tmp/task.txt
```

`--model` and `--effort` are independently optional. Omitted values inherit native settings. The native harness validates actual model and effort availability. Selectors apply to this worker and change no global defaults or permissions. The directory must already exist. The launcher creates no worktree. It passes the initial task once as one prompt argument. Names use letters, digits, underscores, or hyphens, up to 64 characters.

The launch result returns pane IDs immediately and says `registration: pending`. Wait for the worker to appear in `rex-agents list` before messaging it. A worker started without a task may not create its native conversation until the first prompt. A new Codex installation may first show its hook trust dialog.

When an agent shell does not export Rex variables, the integration uses that agent's existing native-ID locator. If an agent has no live locator, it must provide explicit context; it cannot use the user's currently focused pane as a substitute. Explicit context options go before the command:

```sh
rex-agents --session SESSION_ID --block BLOCK_ID launch codex \
  --name helper --cwd /absolute/project --task-file /tmp/task.txt
```

## Collect results and close owned workers

A human-launched Claude Code or Codex conversation can drive one level of owned workers. An owned Rex worker cannot launch more Rex workers. This restriction does not manage native subagents. Ownership follows the driver's native identity, even with explicit Rex context. Missing or conflicting agent identity fails explicitly. Human launches have no agent owner and require manual pane management.

Collect every worker's completed result before cleanup. Save results outside the worker panes when needed. Then run this command from the same driver conversation before its final answer:

```sh
rex-agents cleanup
```

Cleanup cancels unfinished owned workers as well as closing completed workers. Only known completed results and saved native transcripts persist. Do not assume unfinished work is safe. Reason activity or a delivery receipt does not prove completion.

Cleanup is local-only and uses the driver's native identity without Reason. It closes only that driver's recorded panes and protects the driver pane and unrelated panes. It prints JSON with `closed`, `gone`, and `uncertain` collections. It exits 0 when `uncertain` is empty, otherwise 1. Unknown pane states remain reserved. A worker resumed elsewhere or a pane reused by another native conversation is also reported as uncertain and left open. Inspect the reported uncertainty, restore Rex access or recover the pane manually, and retry cleanup safely.

No Stop or SessionEnd hook runs cleanup. A driver crash leaves visible panes for manual recovery. Resuming the same native identity retains ownership. Claude `/clear` creates a new identity, so recover the old workers manually. Complete cleanup resets the next batch's direction to `right`.

## Messages and replies

Copy the current address from `list`. Use a full address when names are ambiguous:

```sh
rex-agents send person/reviewer --message-file /tmp/message.txt
rex-agents send person/reviewer --message-file /tmp/reply.txt --reply-to MESSAGE_ID
rex-agents send person/reviewer --message-file /tmp/note.txt --fyi
```

These CLI sends are for agent shells. They require a native conversation ID and a current Reason result confirming `is_me`. Missing identity fails explicitly. A human should use Rex's **Message Agent** action, which sends as Reason's terminal identity:

```sh
rex do rex_agents_send target=person/reviewer message='Review the latest changes.'
```

The terminal sender name is a routing identity, not proof that a human typed the message. Local agents can run commands with the same operating-system authority. Messages do not grant approval to change the receiver's permissions.

Message files preserve multiline text, quotes, paths with spaces, and shell syntax. Nothing evaluates the message as shell code. `--reply-to` carries the original message ID so the recipient can associate the response with its request. Reason excludes the sender from recipient selection; test with two different conversations.

Normal messages may wake an idle recipient. `--fyi` requests no wake and waits for the recipient's next natural pause. Messages sent while busy can be queued until a tool boundary or turn end. **Delivered or queued does not mean the work finished.** Ask for an explicit completion reply when you need one.

Reason's native hooks and MCP handle incoming messages. This integration never reads or acknowledges another agent's inbox. Do not build a second polling loop around it.

## Rex actions

Search Rex's command palette for these actions:

- **List Agents** opens a listing in a pane.
- **Message Agent** prompts for a target and message when arguments are missing. End a multiline message with a line containing only `.`.
- **Launch Agent** prompts for agent type, name, and working directory when missing.
- **Focus Agent** navigates only when navigation is enabled and Rex accepts app control.
- **Toggle Agent Navigation** changes this integration's navigation preference.

Prompt panes also open without taking focus. Select the new pane manually to answer. No default keyboard shortcuts are installed.

Model and effort selectors are CLI options. The fixed Lua action arguments remain unchanged. Cleanup is an explicit agent CLI command, with no palette action.

## Navigation toggle

Check or change this integration's navigation preference:

```sh
rex-agents navigation status
rex-agents navigation off
rex-agents navigation on
```

`on` permits explicit `focus` requests; it does not cause automatic focus on launch or message receipt. It does not enable Rex Remote Control. To use app navigation later, deliberately enable **Settings > Rex Server > Remote Control** in Rex as well:

```sh
rex-agents focus person/reviewer
```

Leave both controls off while actively moving among panes yourself. The current installation leaves them off. If several Rex apps are connected, specify the initiating app with `rex-agents --client CLIENT focus ADDRESS`. Inaccessible remote panes produce a navigation error while messaging remains available.

## How identity and launch work

Each conversation has a native ID assigned by Claude Code or Codex. Its hooks record that ID with the Rex server, session, and pane IDs in an atomic JSON file under `~/.cache/rex-agents/sessions`. Startup recording does not wait for Reason registration.

Reason's roster contains names and addresses but no native conversation ID. The integration queries Reason with the recorded native ID and requires an active local `is_me` match. Later hooks and lookups resolve pending mappings. Only the worker's own hooks assign its requested Reason name; discovery never renames another conversation. Nested-agent hooks with inherited parent identities do not take over the parent's pane. Names can change without changing identity. Directory names, pane titles, and agent display names never establish sender identity.

A resumed conversation updates its locator. A new conversation in the same pane invalidates the old mapping. Ended native sessions and closed panes cannot be used for navigation. Every send refreshes the roster and supplies the exact native sender with Reason's `--from` option, preventing its terminal fallback.

Launch metadata and a short per-machine file lock prevent duplicate active worker names, including workers still registering. A failed command can be retried after a definite failure. A timeout leaves an uncertain reservation because Rex may already have created the pane. Inspect the returned reservation token and Rex block list before retrying; do not submit the initial task twice.

Codex workers use its supported `--no-daemon` option. In the tested version, the shared app server drops the launching terminal's Rex environment before hooks run. The dedicated process preserves hook context and native interactivity. Optional model and effort selectors apply to the worker without changing permission settings or global defaults. This starts the normal interactive agent, not another integration service.

## Install on another machine

Copy or check out this project on the machine. It needs Python 3.9 or newer, Rex, the Reason engine, and whichever agent CLIs you use. No Python packages are required.

1. Enable Claude Code and Codex through Reason's supported setup. With the engine installed, run `~/.reason/bin/reason-network setup` and select those agents. If absent, `reason network setup` bootstraps it; inspect its report because the wrapper can configure other detected agents during bootstrap.
2. Run `./bin/rex-agents install`, then `rex config check` and `rex config reload`.
3. In Codex, review and trust the new hooks through its native dialog or `/hooks`. Trust after the final installation because changed hooks need renewed trust.
4. Run `rex-agents doctor`, launch a worker, and verify a two-conversation message exchange.
5. Enroll both machines in the same Reason network and configure the remote host in Rex before testing remote use.

For an already configured Rex host:

```sh
rex-agents launch codex --name remote-reviewer \
  --cwd /absolute/path/on/remote --task-file /tmp/task.txt --host HOST_LABEL
```

The task is sent through Rex; the directory is interpreted on the remote machine. The remote installation uses its own agent settings. Remote launch rejects `--model` and `--effort`; remote cleanup is unsupported. Manage remote worker panes manually. With several remote sessions, invoke Launch Agent in the intended session. Discovery asks each configured host for its local registry through the existing authenticated Rex connection. There is no new network listener.

CLI and skill files are symlinks into this checkout. The lifecycle changes need no new dependencies or installation steps on this existing setup. Lua and hook definitions remain unchanged.

## Troubleshooting

**No native identity or no `is_me` match:** run the command inside the intended agent conversation. Check hook trust and Reason integration. Restart or resume old conversations if they have not loaded the new hooks. For an existing shared-server Codex conversation, resume with `codex --no-daemon resume SESSION_ID` in its Rex pane. Never substitute another conversation's ID.

**Registration remains pending:** inspect the returned pane. It may be waiting for its first prompt, workspace trust, hook trust, login, or an agent startup error. `doctor` distinguishes missing dependencies and pending or failed registration. Do not create another worker with the same name.

**Navigation is off:** this is the current intentional default. Use the integration toggle only when you want explicit agent-driven navigation. Rex's separate Remote Control setting must also be enabled for app actions.

**Reason wrapper says “this link names only this computer, which can't let itself in”:** local engine messaging can still work. This machine's account enrollment remains unresolved; use supported Reason enrollment before cross-machine testing. Ordinary integration commands use the installed engine directly.

**Launch outcome uncertain:** inspect Rex for the reservation token in the pane label. Only remove the corresponding file in `~/.cache/rex-agents/launches` after confirming that no worker pane was created. Closing a known failed pane permits a fresh launch.

**Rex or agent executable moved:** rerun `install`, `rex config check`, and `rex config reload`. The Lua module captures local executable lookup paths at installation.

## Remove or inspect the installation

```sh
rex-agents uninstall
rex config check
rex config reload
```

Removal deletes only this project's hooks, CLI and skill links, Lua module, managed `require` entry, navigation preference, and cache. Existing Reason integrations, active conversations, unrelated configuration, and backups remain intact. Already loaded locator hooks become inert after uninstall.

Source lives in `rex_agents/core.py` (identity, messaging, launch, focus), `rex_agents/install.py` (installation and navigation preference), `rex_agents/cli.py` (commands and diagnostics), `lua/rex_agents.lua` (Rex actions), and `skill/SKILL.md` (agent instructions). Run `python3 -m unittest discover -s tests -v` for regression tests. See `VERIFICATION.md` for measured results and remaining limits.
