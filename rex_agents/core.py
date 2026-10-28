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
# Reason's MCP tool that pops a question up on the human's screen.
ASK_USER = "mcp__reason-network__ask_user"
# Only the driver talks to the human, so an owned worker's question goes to the driver instead.
RELAY = ("You are a rex-agents worker, and only your driver talks to the human. Send this question to your "
         "driver with MCP send_message, at the Reason address in your task, then wait for its reply.")
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
        with os.fdopen(fd, "w") as stream:
            stream.write(value if isinstance(value, str) else json.dumps(value, indent=2) + "\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read(path, default=None):
    try:
        return json.loads(path.read_text())
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


def columns(node):
    """Side-by-side parts of a Rex layout node."""
    split = node.get("split")
    return columns(split["before"]) + columns(split["after"]) if split and split["direction"] == "horizontal" else 1


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
        # Tool-launched children inherit their parent's Rex context, but do not own its pane.
        if ((kind == "codex" and os.environ.get("CLAUDECODE"))
                or (kind == "claude-code" and os.environ.get("CODEX_THREAD_ID"))
                or payload.get("agent_id")):
            return
        location = dict(server=self.server, session=self.session, block=self.block)
        if not all(location.values()):
            return
        if event == "SessionStart":
            # Codex tool shells lose REX_*; launch and cleanup find the pane here instead.
            atomic(self.locator((kind, native_id)), location)
            return
        if event not in BLOCKING:
            return
        try:
            return self.alert((kind, native_id), payload)
        except (Error, LookupError, TypeError):
            pass

    def alert(self, identity, payload):
        """Send an owned worker's question to its driver; pop up other blocking prompts, since the pane may go unseen."""
        pane = next((b for b in self.panes(self.session) if b["block_id"] == self.block), {})
        worker = parse(pane.get("label"))
        if not worker:
            return
        if payload.get("tool_name") in ("AskUserQuestion", ASK_USER) and worker[0] != HUMAN:
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                    "permissionDecisionReason": RELAY}}
        if payload.get("tool_name") == ASK_USER:
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

    def place(self, newest):
        """(anchor, direction, ratio) for the next worker: below the newest one, or a new column once its column holds two."""
        listing = decode(self.rex("window", "ls", "-s", newest["session"], "--json"))
        try:
            for window in listing["windows"]:
                for layer in window["layers"] if window["window_id"] == newest.get("window_id") else ():
                    column = parents(root := layer["layout"]).get(newest["block_id"])
                    if column and column["direction"] == "vertical":
                        # Open a column beside all the others, as wide as each of them.
                        return node_id(root), "horizontal", columns(root) / (columns(root) + 1)
        except (KeyError, TypeError) as exc:
            raise Error(f"Cannot place the worker in Rex's layout: missing {exc}") from exc
        return newest["block_id"], "vertical", 0.5

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
            mine = [b for b in blocks if (w := parse(b.get("label"))) and w[0] == me and b["block_id"] not in own]
            # The caller's PATH goes first, as `rex split` sends it.
            options = dict(command=argv, cwd=str(directory),
                           path_prepend=[p for p in os.environ.get("PATH", "").split(os.pathsep) if p])
            layout = {"block": dict(flavor=TERMINAL, label=label, options=options)}
            if mine:
                # `rex split` takes only a pane as anchor; the API also takes a split, which a new column needs.
                newest = mine[-1]
                anchor, direction, ratio = self.place(newest)
                method = "session.new_split"
                request = dict(session_id=newest["session"], anchor_id=anchor, direction=direction, side="after",
                               ratio=ratio, focus=False, layout=layout)
            else:
                # The first worker opens a session of its own, so the driver's pane never splits.
                # Workers may rename the session; the window label keeps the driver's name.
                title = decode(self.rex("session", "inspect", driver["session"], "--json")).get("label") or "rex-agents"
                method = "session.create"
                request = dict(label=f"{title}-workers"[:128],
                               initial_windows=[{"window_label": f"workers of {title}"[:128], "layout": layout}])
            try:
                result = decode(self.rex("api", "call", method, "-", stdin=json.dumps(request)))
            except Error as exc:
                raise Error(f"Launch outcome uncertain for {name}: {exc}. "
                            f"A pane labeled {label} exists if Rex created it; a retry refuses while it does.") from exc
            if mine:
                result = dict(result, session_id=newest["session"])
            else:
                result = dict(session_id=result["session_id"], **result["initial_windows"][0])
            return dict(result, name=name, label=label, registration="pending")

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
            # A workers session outlives its last pane; close the ones this cleanup emptied.
            emptied = set() if rows is None else {i["session"] for i in result["closed"] + result["gone"]} - {
                b["session"] for b in rows}
            for session in emptied:
                with contextlib.suppress(Error):
                    self.rex("session", "kill", session)
        return result
