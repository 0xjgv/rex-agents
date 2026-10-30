"""Launch native workers into labeled Rex panes and close the ones a driver owns."""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin/rex-agents"
# A worker pane's label is its only record: rex-agents:<owner>:<name>, at most 128 characters.
PREFIX = "rex-agents:"
HUMAN = "-"
NAME = r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}"
SELECTOR = r"[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}(?:\[[A-Za-z0-9_-]+\])?"
# The model picks the native CLI that runs the worker.
HARNESS = {"claude-": "claude", "gpt-": "codex"}
# Hook events that mean a prompt is blocking the worker. Earlier versions registered others.
BLOCKING = ("PreToolUse", "PermissionRequest")
# Reason's MCP tool that pops a question up on the human's screen. Codex turns the server's hyphen into an underscore.
ASK_USER = {"claude-code": "mcp__reason-network__ask_user", "codex": "mcp__reason_network__ask_user"}
# Only the driver talks to the human, so an owned worker's question goes to the driver instead.
RELAY = ("You are a rex-agents worker, and only your driver talks to the human. Send this question to your "
         "driver with MCP send_message, at the Reason address in your task, then wait for its reply.")
# Rex's own SessionStart hook tells every agent to name its session, but a worker shares its driver's.
KEEP_NAME = ("You are a rex-agents worker in your driver's Rex session. Leave the session's name alone: do not run "
             "`rex session rename`, even if another instruction tells you to name the session.")
# An owned worker owns its task: subagents work under it, and questions climb one level at a time to the driver.
OWNER = ("You own your task. Use native subagents freely, and tell each one to put any question in its final reply "
         "instead of asking the user. Answer what you can. Send the rest, and your result, to your driver with MCP "
         "send_message at the Reason address in your task.")
# A subagent cannot receive a Reason reply, so its question goes back to the worker that launched it.
RETURN = ("You are a subagent of a rex-agents worker, and only its driver talks to the human. Do not ask the user. "
          "End your turn and put the question in your final reply; the agent that launched you will get it answered.")
NOT_FOUND = r'(block|session) target "[^"\n]+" not found'
TERMINAL = "com.superlogical.terminal.shell"


class Error(Exception):
    pass


class CommandError(Error):
    """The subprocess exited unsuccessfully, rather than timing out locally."""


def run(argv, *, env=None, stdin=None, timeout=12):
    try:
        result = subprocess.run([str(a) for a in argv], input=stdin, text=True,
                                capture_output=True, env=env, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Error(f"{argv[0]}: {exc}") from exc
    if result.returncode:
        raise CommandError((result.stderr or result.stdout).strip() or
                    f"{argv[0]} exited {result.returncode}")
    return result.stdout


def decode(text):
    try:
        return json.loads(text)
    except (ValueError, TypeError) as exc:
        raise Error("Incompatible API: expected JSON") from exc


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (ValueError, OSError) as exc:
        raise Error(f"Cannot read {path}: {exc}") from exc


def native_identity():
    """The calling agent conversation as (kind, id), or None for a human shell."""
    codex = os.environ.get("CODEX_THREAD_ID")
    claude = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if codex and (claude or os.environ.get("CLAUDECODE")):
        raise Error("Conflicting inherited agent identities; use a clean worker or resume the intended conversation")
    if codex:
        return "codex", codex
    if claude:
        return "claude-code", claude
    if os.environ.get("CLAUDECODE"):
        raise Error("Incomplete native agent identity")
    return None


def owner(identity):
    return hashlib.sha256(":".join(identity).encode()).hexdigest()[:16] if identity else HUMAN


def parse(label):
    """(owner, name) for a worker pane label, else None."""
    if not isinstance(label, str) or not label.startswith(PREFIX):
        return None
    found, _, name = label[len(PREFIX):].partition(":")
    return (found, name) if found and name else None


def node_id(node):
    return node.get("block_id") or node["split"]["split_id"]


def leaves(node):
    """Block IDs under a Rex layout node, left to right and top to bottom."""
    split = node.get("split")
    return leaves(split["before"]) + leaves(split["after"]) if split else [node["block_id"]]


def columns(node):
    """Side-by-side parts of a Rex layout node, left to right."""
    split = node.get("split")
    return columns(split["before"]) + columns(split["after"]) if split and split["direction"] == "horizontal" else [node]


def parents(node, found=None):
    """Node ID -> parent split, across a Rex layout tree."""
    found = {} if found is None else found
    if split := node.get("split"):
        for child in (split["before"], split["after"]):
            found[node_id(child)] = split
            parents(child, found)
    return found


class Integration:
    def __init__(self, *, cache=None, server=None, session=None, block=None):
        self.cache = Path(cache or os.environ.get("XDG_CACHE_HOME", str(Path.home()/".cache")))
        if cache is None:
            self.cache /= "rex-agents"
        self.server = server or os.environ.get("REX_SERVER")
        self.session = session or os.environ.get("REX_SESSION")
        self.block = block or os.environ.get("REX_BLOCK")

    def rex(self, *args, stdin=None, timeout=12):
        argv = [os.environ.get("REX_AGENTS_REX", "rex"), "--autostart=false", "--timeout", f"{max(1, timeout - 2)}s"]
        if self.server:
            argv += ["-S", self.server]
        return run(argv + list(args), stdin=stdin, timeout=timeout)

    def reason(self, *args, identity, stdin=None):
        engine = os.environ.get("REX_AGENTS_REASON") or str(Path.home()/".reason/bin/reason-network")
        if not os.access(engine, os.X_OK):
            engine = shutil.which("reason-network")
        if not engine:
            raise Error("Reason engine missing. Run supported Reason setup explicitly; ordinary commands never install it.")
        env = dict(os.environ, REASON_NETWORK_AGENT=identity[0], REASON_NETWORK_SESSION=identity[1])
        return run([engine, *args], env=env, stdin=stdin)

    def locator(self, identity):
        return self.cache/"sessions"/f"{owner(identity)}.json"

    def hook(self, kind, event, payload):
        native_id = payload.get("session_id") or payload.get("conversation_id") or payload.get("sessionId")
        if not isinstance(native_id, str) or not native_id:
            raise Error("Hook payload has no native session ID")
        # The other harness's children inherit the pane's Rex context, but do not own its pane.
        if (kind == "codex" and os.environ.get("CLAUDECODE")) or (kind == "claude-code" and os.environ.get("CODEX_THREAD_ID")):
            return
        location = dict(server=self.server, session=self.session, block=self.block)
        if not all(location.values()):
            return
        if event == "SessionStart":
            # A native subagent shares its parent's session and pane; only its blocking prompts matter.
            if payload.get("agent_id"):
                return
            # Codex tool shells lose REX_*; launch and cleanup find the pane here instead.
            atomic(self.locator((kind, native_id)), location)
            with contextlib.suppress(Error, LookupError, TypeError):
                if worker := self.worker():
                    context = KEEP_NAME if worker[0] == HUMAN else f"{KEEP_NAME}\n\n{OWNER}"
                    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
            return
        if event not in BLOCKING:
            return
        try:
            return self.alert((kind, native_id), payload)
        except (Error, LookupError, TypeError):
            pass

    def worker(self):
        """(owner, name) from the label of the hook's own pane, else None."""
        pane = next((b for b in self.panes(self.session) if b["block_id"] == self.block), {})
        return parse(pane.get("label"))

    def alert(self, identity, payload):
        """Send an owned worker's question to its driver; pop up other blocking prompts, since the pane may go unseen."""
        worker = self.worker()
        if not worker:
            return
        if payload.get("tool_name") in ("AskUserQuestion", ASK_USER[identity[0]]) and worker[0] != HUMAN:
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                    "permissionDecisionReason": RETURN if payload.get("agent_id") else RELAY}}
        if payload.get("tool_name") == ASK_USER[identity[0]]:
            return  # Reason pops it up itself.
        def dicts(value):
            return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
        tool = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
        if payload.get("tool_name") == "AskUserQuestion":
            detail = "; ".join(f"{q.get('question')} [{', '.join(str(o.get('label')) for o in dicts(q.get('options')))}]"
                               for q in dicts(tool.get("questions")))
        else:
            detail = f"approve {payload.get('tool_name')}: " + str(tool.get("description") or tool.get("command") or tool)[:300]
        person = decode(self.reason("who", "--json", identity=identity))["person"]
        self.reason("send", person, "--notify", "--from", ":".join(identity), identity=identity,
                    stdin=f"{worker[1]} is waiting in its Rex pane: {detail}")

    def where(self, identity):
        """Fill the driver's pane from its SessionStart locator when the shell lacks Rex context."""
        if self.session and self.block:
            return
        location = read(self.locator(identity), None) if identity else None
        if not location:
            raise Error("No Rex pane known for this conversation; pass --session and --block")
        self.server = self.server or location["server"]
        self.session = self.session or location["session"]
        self.block = self.block or location["block"]

    def own(self, identity):
        """Panes the caller may be running in; an explicit --block must not hide the real one."""
        found = {self.block, os.environ.get("REX_BLOCK")}
        if identity:
            found.add(read(self.locator(identity), {}).get("block"))
        return found - {None}

    def panes(self, session=None):
        """Blocks in one session, or all sessions, oldest first: Rex block IDs are UUIDv7."""
        if session:
            sessions = [session]
        else:
            listing = decode(self.rex("ls", "--json"))
            sessions = [s["session_id"] for s in (listing.get("sessions", []) if isinstance(listing, dict) else listing)]
        rows = []
        for name in sessions:
            try:
                data = decode(self.rex("block", "ls", "-s", name, "--json"))
            except CommandError as exc:
                # A session can close between `ls` and its block listing.
                if session or not re.search(NOT_FOUND, str(exc)):
                    raise
                continue
            if not isinstance(data, dict) or not isinstance(data.get("blocks"), list):
                raise Error("Incompatible Rex block listing")
            rows += [dict(row, session=name) for row in data["blocks"]]
        return sorted(rows, key=lambda row: row["block_id"])

    def place(self, driver, mine):
        """(anchor, direction, ratio, moved) for the next worker, in balanced columns of up to three on the driver's right."""
        listing = decode(self.rex("window", "ls", "-s", driver["session"], "--json")) if mine else {"windows": []}
        try:
            window = next((w for w in listing["windows"] if w["window_id"] == driver.get("window_id")), {})
            tree = {}
            for layer in window.get("layers", ()):
                parents(layer["layout"], tree)
            # The workers' area is what the driver's own split put on its right.
            split = tree.get(driver["block_id"], {})
            beside = split.get("direction") == "horizontal" and node_id(split["before"]) == driver["block_id"]
            area = split["after"] if beside else None
            if not area or not set(leaves(area)) <= {b["block_id"] for b in mine}:
                return driver["block_id"], "horizontal", 2 / 3, None
            stacks = columns(area)
            column = min(stacks, key=lambda c: len(leaves(c)))  # the leftmost of the shortest
            if (rows := len(leaves(column))) < 3:
                return node_id(column), "vertical", rows / (rows + 1), None
            # Every column is full: open one as wide as each, and move in the last column's lowest unfocused worker.
            moved = next(b for b in reversed(leaves(stacks[-1])) if b != window.get("focused_block_id"))
            return node_id(area), "horizontal", len(stacks) / (len(stacks) + 1), moved
        except (KeyError, TypeError) as exc:
            raise Error(f"Cannot place the worker in Rex's layout: missing {exc}") from exc

    @contextlib.contextmanager
    def lock(self):
        self.cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(self.cache/"launch.lock", "a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def launch(self, name, cwd, model, task=None, effort=None):
        if not re.fullmatch(NAME, name):
            raise Error("Worker name must be 1–64 letters, digits, underscores, or hyphens")
        for label, value in (("model", model), ("effort", effort)):
            if value is not None and not re.fullmatch(SELECTOR, value):
                raise Error(f"Invalid {label}: expected a model or effort identifier")
        kind = next((k for prefix, k in HARNESS.items() if model.startswith(prefix)), None)
        if not kind:
            raise Error(f"Unknown model family {model}: expected claude-* or gpt-*")
        directory = Path(cwd).expanduser().resolve()
        if not directory.is_dir():
            raise Error(f"Working directory does not exist: {directory}")
        # The pane runs the login shell's environment, which may lack the caller's PATH.
        executable = shutil.which(kind)
        if not executable:
            raise Error(f"Missing executable: {kind}")
        identity = native_identity()
        me = owner(identity)
        self.where(identity)
        own = self.own(identity)
        argv = [executable, "--name", name] if kind == "claude" else [executable, "--no-daemon"]
        argv += ["--model" if kind == "claude" else "-m", model]
        if effort is not None:
            argv += ["--effort", effort] if kind == "claude" else ["-c", "model_reasoning_effort=" + json.dumps(effort)]
        if task is not None:
            argv += ["--", task]
        label = f"{PREFIX}{me}:{name}"
        with self.lock():
            blocks = self.panes()
            driver = next((b for b in blocks if b["block_id"] == self.block), None)
            if driver is None:
                raise Error(f"Driver pane {self.block} not found in Rex")
            if any((parent := parse(b.get("label"))) and parent[0] != HUMAN for b in blocks if b["block_id"] in own):
                raise Error("Owned workers cannot launch nested workers")
            if any((worker := parse(b.get("label"))) and worker[1] == name for b in blocks):
                raise Error(f"Worker {name} already has a Rex pane; close it before relaunching")
            mine = [b for b in blocks if (w := parse(b.get("label"))) and w[0] == me and b["block_id"] not in own
                    and b["session"] == driver["session"] and b.get("window_id") == driver.get("window_id")]
            # The caller's PATH goes first, as `rex split` sends it.
            options = dict(command=argv, cwd=str(directory),
                           path_prepend=[p for p in os.environ.get("PATH", "").split(os.pathsep) if p])
            # `rex split` takes only a pane as anchor; the API also takes a split, which a full column needs.
            anchor, direction, ratio, moved = self.place(driver, mine)
            request = dict(session_id=driver["session"], anchor_id=anchor, direction=direction, side="after",
                           ratio=ratio, focus=False, layout={"block": dict(flavor=TERMINAL, label=label, options=options)})
            try:
                result = decode(self.rex("api", "call", "session.new_split", "-", stdin=json.dumps(request)))
            except Error as exc:
                raise Error(f"Launch outcome uncertain for {name}: {exc}. "
                            f"A pane labeled {label} exists if Rex created it; a retry refuses while it does.") from exc
            if moved:
                # The new column takes a second worker, and the columns now share half the tab.
                new = result["block_ids"][0]
                steps = (("session.move_block", dict(block_id=moved, anchor_block_id=new, direction="vertical",
                                                     side="before")),
                         ("session.resize_pane", dict(direction="horizontal", before_block_id=driver["block_id"],
                                                      after_block_id=new, ratio=0.5)))
                try:
                    for method, request in steps:
                        self.rex("api", "call", method, "-", stdin=json.dumps(dict(request, session_id=driver["session"])))
                except Error as exc:
                    raise Error(f"{name} launched, but Rex did not finish balancing the columns: {exc}") from exc
            return dict(result, session_id=driver["session"], name=name, label=label, registration="pending")

    def cleanup(self):
        identity = native_identity()
        if not identity:
            raise Error("No native agent identity. Run cleanup from the driver conversation.")
        me = owner(identity)
        with contextlib.suppress(Error):
            self.where(identity)
        own = self.own(identity)
        result = dict(closed=[], gone=[], uncertain=[])
        with self.lock():
            try:
                owned = [(b, w) for b in self.panes() if (w := parse(b.get("label"))) and w[0] == me]
            except Error as exc:
                result["uncertain"].append(dict(error=f"Rex panes unavailable: {exc}"))
                return result
            for pane, worker in owned:
                item = dict(name=worker[1], session=pane["session"], block=pane["block_id"])
                if pane["block_id"] in own:
                    result["uncertain"].append(dict(item, error="Refusing to close the driver's own pane"))
                    continue
                try:
                    self.rex("block", "close", "-s", pane["session"], pane["block_id"])
                    result["closed"].append(item)
                except CommandError as exc:
                    gone = re.search(NOT_FOUND, str(exc))
                    result["gone" if gone else "uncertain"].append(item if gone else dict(item, error=str(exc)))
                except Error as exc:
                    result["uncertain"].append(dict(item, error=str(exc)))
            # A close request alone does not prove the pane went away.
            try:
                rows, error = self.panes(), "Pane still present after close"
            except Error as exc:
                rows, error = None, f"Pane absence unconfirmed: {exc}"
            for item in list(result["closed"]):
                if rows is None or item["block"] in {b["block_id"] for b in rows}:
                    result["closed"].remove(item)
                    result["uncertain"].append(dict(item, error=error))
            # A session outlives its last pane; close the ones this cleanup emptied.
            emptied = set() if rows is None else {i["session"] for i in result["closed"] + result["gone"]} - {
                b["session"] for b in rows}
            for session in emptied:
                with contextlib.suppress(Error):
                    self.rex("session", "kill", session)
        return result
