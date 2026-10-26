"""Identity, discovery, messaging, and interactive worker lifecycle."""
import base64
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
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin/rex-agents"
IDENTITY_VARS = (
    "REASON_NETWORK_AGENT", "REASON_NETWORK_SESSION", "CLAUDECODE",
    "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CODEX_SESSION_ID",
    "REX_AGENTS_NATIVE_ID", "REX_AGENTS_KIND", "REX_AGENTS_LAUNCH",
)


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


def clean_env():
    env = dict(os.environ)
    for key in IDENTITY_VARS:
        env.pop(key, None)
    return env


def identity_env(kind, native_id):
    env = clean_env()
    env.update(REASON_NETWORK_AGENT=kind, REASON_NETWORK_SESSION=native_id)
    return env


def native_identity(*, allow_human=False):
    codex = os.environ.get("CODEX_THREAD_ID")
    hook_kind = os.environ.get("REX_AGENTS_KIND")
    hook_id = os.environ.get("REX_AGENTS_NATIVE_ID")
    if ((hook_kind is not None or hook_id is not None)
            and (hook_kind not in ("codex", "claude-code") or not hook_id)):
        raise Error("Incomplete or invalid native agent identity")
    if hook_kind == "codex":
        if codex and codex != hook_id:
            raise Error("Conflicting inherited agent identities")
        codex = hook_id
    # SessionStart refreshes this hook identity after Claude /clear as well as resume.
    claude = hook_id if hook_kind == "claude-code" else None
    claude = claude or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if codex and (claude or os.environ.get("CLAUDECODE")):
        raise Error("Conflicting inherited agent identities; use a clean worker or resume the intended conversation")
    for value in (codex, claude):
        if value is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", value):
            raise Error("Invalid native agent identity")
    reason_kind = os.environ.get("REASON_NETWORK_AGENT")
    reason_id = os.environ.get("REASON_NETWORK_SESSION")
    if reason_kind is not None or reason_id is not None:
        if not reason_kind or not reason_id:
            raise Error("Incomplete native agent identity")
        expected = ("codex", codex) if codex else ("claude-code", claude)
        if (reason_kind, reason_id) != expected:
            raise Error("Conflicting inherited agent identities")
    if os.environ.get("CODEX_SESSION_ID") and os.environ["CODEX_SESSION_ID"] != codex:
        raise Error("Conflicting inherited agent identities")
    if codex:
        return "codex", codex
    if claude:
        return "claude-code", claude
    hints = (key for key in IDENTITY_VARS if key != "REX_AGENTS_LAUNCH")
    if any(key in os.environ for key in hints):
        raise Error("Incomplete native agent identity")
    if allow_human:
        return None
    raise Error("No native agent identity. Use an agent shell or a human Rex action.")


class Integration:
    def __init__(self, *, cache=None, server=None, session=None, block=None, client=None):
        self.cache = Path(cache or os.environ.get("XDG_CACHE_HOME", str(Path.home()/".cache")))
        if cache is None:
            self.cache /= "rex-agents"
        self.server = server or os.environ.get("REX_SERVER")
        self.session = session or os.environ.get("REX_SESSION")
        self.block = block or os.environ.get("REX_BLOCK")
        self.client = client or os.environ.get("REX_CLIENT")

    def rex(self, *args, server=None, timeout=12):
        argv = [os.environ.get("REX_AGENTS_REX", "rex"), "--autostart=false", "--timeout", f"{max(1, timeout - 2)}s"]
        if server or self.server:
            argv += ["-S", server or self.server]
        return run(argv + list(args), timeout=timeout)

    def local_server(self):
        # Resolve the default Unix endpoint without a CLI or inherited server override.
        env = dict(os.environ)
        env.pop("REX_SERVER", None)
        data = decode(run([os.environ.get("REX_AGENTS_REX", "rex"), "--autostart=false",
                           "--timeout", "10s", "whoami", "--json"], env=env))
        endpoint = data.get("endpoint") if isinstance(data, dict) else None
        if not isinstance(endpoint, str) or not endpoint.startswith("unix:") or len(endpoint) <= 5:
            raise Error("Local Rex server unknown")
        return endpoint

    def reason(self, *args, identity=None, human=False, stdin=None):
        engine = os.environ.get("REX_AGENTS_REASON") or str(Path.home()/".reason/bin/reason-network")
        if not os.access(engine, os.X_OK):
            engine = shutil.which("reason-network")
        if not engine:
            raise Error("Reason engine missing. Run supported Reason setup explicitly; ordinary commands never install it.")
        env = identity_env(*identity) if identity else clean_env() if human else None
        return run([engine, *args], env=env, stdin=stdin)

    def roster(self, identity=None):
        data = decode(self.reason("who", "--json", identity=identity, human=identity is None))
        if not isinstance(data, dict) or not isinstance(data.get("sessions"), list):
            raise Error("Incompatible Reason roster: sessions array missing")
        required = {"address", "name", "machine", "person", "agent", "status", "is_me"}
        if any(not required <= set(row) for row in data["sessions"]):
            raise Error("Incompatible Reason session fields")
        return data

    def me(self, kind, native_id):
        data = self.roster((kind, native_id))
        rows = [r for r in data["sessions"] if r["is_me"] is True
                and r["agent"] == kind and r["machine"] == data["machine"]
                and r["person"] == data["person"] and r["status"] != "offline"]
        if len(rows) != 1:
            raise Error(f"Native session {kind}:{native_id} is not uniquely registered as is_me")
        return rows[0]

    def locator_path(self, kind, native_id):
        key = hashlib.sha256(f"{kind}:{native_id}".encode()).hexdigest()
        return self.cache / "sessions" / f"{key}.json"

    def locators(self):
        return [record for p in sorted((self.cache/"sessions").glob("*.json")) if (record := read(p)) is not None]

    def hook(self, kind, event, payload):
        native_id = payload.get("session_id") or payload.get("conversation_id") or payload.get("sessionId")
        if not isinstance(native_id, str) or not native_id:
            raise Error("Hook payload has no native session ID")
        # Tool-launched children inherit their parent's Rex context, but do not own its pane.
        if ((kind == "codex" and os.environ.get("CLAUDECODE"))
                or (kind == "claude-code" and os.environ.get("CODEX_THREAD_ID"))
                or payload.get("agent_id")):
            return
        inherited = os.environ.get("REX_AGENTS_NATIVE_ID")
        if (kind == "claude-code" and inherited and inherited != native_id
                and payload.get("source") != "clear"):
            return
        path = self.locator_path(kind, native_id)
        old = read(path, {})
        if event == "SessionEnd":
            ending = {"server": self.server, "session": self.session, "block": self.block}
            if old and old["location"] == ending:
                old["ended"] = True
                atomic(path, old)
            return
        token = os.environ.get("REX_AGENTS_LAUNCH")
        launch = read(self.cache/"launches"/f"{token}.json", {}) if token else {}
        location = {"server": self.server, "session": self.session, "block": self.block}
        if not all(location.values()):
            location = old.get("location") or launch.get("location")
        if not location or not all(location.values()):
            return
        # A new conversation in this pane invalidates an older /clear or resumed mapping.
        for previous in self.locators():
            if previous["native_id"] != native_id and previous["location"] == location:
                previous["ended"] = True
                atomic(self.locator_path(previous["kind"], previous["native_id"]), previous)
        record = dict(old, kind=kind, native_id=native_id, location=location,
                      ended=False, updated=time.time(), launch=token or old.get("launch"))
        atomic(path, record)
        if kind == "claude-code" and event == "SessionStart" and os.environ.get("CLAUDE_ENV_FILE"):
            import shlex
            with open(os.environ["CLAUDE_ENV_FILE"], "a") as stream:
                stream.write(f"\nexport REX_AGENTS_KIND=claude-code\nexport REX_AGENTS_NATIVE_ID={shlex.quote(native_id)}\n")
        # Recording identity never waits for network registration at startup.
        if event != "SessionStart":
            try:
                self.resolve(record)
            except Error:
                pass

    def resolve(self, record):
        if record.get("ended"):
            raise Error("Native session ended")
        row = self.me(record["kind"], record["native_id"])
        token = record.get("launch")
        launch = read(self.cache/"launches"/f"{token}.json", {}) if token else {}
        if launch and not record.get("named"):
            self.reason("status", "--name", launch["name"], identity=(record["kind"], record["native_id"]))
            path = self.locator_path(record["kind"], record["native_id"])
            latest = read(path, record)
            latest["named"] = True
            atomic(path, latest)
            row = self.me(record["kind"], record["native_id"])
        return row

    def live_location(self, location, server=None):
        scope = ["-s", location["session"], "-b", location["block"]]
        state = decode(self.rex("block", "call", *scope, "process", server=server or location["server"]))
        if not state.get("child") or state.get("last_exit") is not None:
            raise Error("Mapped pane's process has ended")

    @staticmethod
    def valid_location(location):
        return (isinstance(location, dict)
                and all(isinstance(location.get(key), str) and location[key].strip()
                        for key in ("server", "session", "block"))
                and re.fullmatch(r"session:[A-Za-z0-9][A-Za-z0-9_-]*", location["session"]) is not None
                and re.fullmatch(r"block:[A-Za-z0-9][A-Za-z0-9_-]*", location["block"]) is not None)

    def pane_blocks(self, location):
        data = decode(self.rex("block", "ls", "-s", location["session"], "--json", server=location["server"]))
        if (not isinstance(data, dict) or not isinstance(data.get("blocks"), list)
                or any(not isinstance(row, dict) or not isinstance(row.get("block_id"), str)
                       or not re.fullmatch(r"block:[A-Za-z0-9][A-Za-z0-9_-]*", row["block_id"])
                       for row in data["blocks"])):
            raise Error("Incompatible Rex block listing")
        if len({row["block_id"] for row in data["blocks"]}) != len(data["blocks"]):
            raise Error("Incompatible Rex block listing: duplicate block IDs")
        return data["blocks"]

    def pane_state(self, location):
        """Only an exact listing or an absent session proves a pane is gone."""
        if not self.valid_location(location):
            return "unknown"
        try:
            blocks = self.pane_blocks(location)
            if not any(row["block_id"] == location["block"] for row in blocks):
                return "gone"
            state = decode(self.rex("block", "call", "-s", location["session"],
                                    "-b", location["block"], "process", server=location["server"]))
            if not isinstance(state, dict) or "child" not in state or "last_exit" not in state:
                return "unknown"
            if ((state["child"] is not None and not isinstance(state["child"], dict))
                    or (state["last_exit"] is not None and not isinstance(state["last_exit"], dict))):
                return "unknown"
            if state["child"] is not None and (type(state["child"].get("pid")) is not int
                                                or state["child"]["pid"] <= 0):
                return "unknown"
            if state["child"] is None or state["last_exit"] is not None:
                return "exited"
            return "live"
        except CommandError as exc:
            if re.search(r'session target "[^"\n]+" not found', str(exc)):
                return "gone"
        except Error:
            pass
        return "unknown"

    def registry(self):
        mappings, warnings = [], []
        for record in self.locators():
            if record.get("ended"):
                continue
            try:
                row = self.me(record["kind"], record["native_id"])
            except Error as exc:
                warnings.append(str(exc))
                continue
            location = record["location"]
            issue = None
            try:
                self.live_location(location)
            except Error as exc:
                issue = str(exc)
            mappings.append({"address": row["address"], "person": row["person"], "machine": row["machine"],
                             "native_id": record["native_id"], "kind": record["kind"],
                             "location": location if not issue else None, "navigation_error": issue})
        return {"mappings": mappings, "warnings": warnings}

    def hosts(self):
        data = decode(self.rex("hosts", "--json"))
        return data.get("hosts", [])

    def listing(self, remote=True):
        try:
            sender = native_identity()
        except Error:
            sender = None
        data = self.roster(sender)
        exported = self.registry()
        mappings = exported["mappings"]
        warnings = exported["warnings"]
        if remote:
            try:
                hosts = self.hosts()
            except Error as exc:
                hosts = []
                warnings.append(f"Rex hosts unavailable: {exc}")
            for host in hosts:
                label = host["label"]
                try:
                    result = decode(self.rex("do", "rex_agents_registry", "--json", server=label))
                    for mapping in result["mappings"]:
                        mapping["host"] = label
                    mappings.extend(result["mappings"])
                    warnings.extend(result.get("warnings", []))
                except Error as exc:
                    warnings.append(f"Host {label}: navigation unavailable: {exc}")
        for row in data["sessions"]:
            found = [m for m in mappings if all(m[k] == row[k] for k in ("address", "person", "machine"))]
            row["rex"] = found[0] if len(found) == 1 else None
            if len(found) > 1:
                warnings.append(f"Ambiguous Rex mapping for {row['address']}")
        data["warnings"] = warnings
        return data

    @staticmethod
    def target(rows, target):
        rows = [r for r in rows if r["status"] != "offline"]
        matches = [r for r in rows if r["address"] == target]
        if not matches:
            matches = [r for r in rows if r["name"] == target]
        if len(matches) != 1:
            raise Error(f"Target {target!r}: {'ambiguous; use a full address' if matches else 'not registered'}")
        return matches[0]

    def send(self, target, message, *, fyi=False, reply_to=None, human=False):
        if not message.strip():
            raise Error("Empty message")
        sender = None
        if not human:
            sender = native_identity()
            self.me(*sender)
        # Fetch immediately before sending: display names and addresses may change.
        row = self.target(self.roster(sender)["sessions"], target)
        args = ["send", row["address"]]
        if sender:
            args += ["--from", ":".join(sender)]
        if fyi:
            args += ["--fyi"]
        if reply_to:
            args += ["--reply-to", reply_to]
        return self.reason(*args, identity=sender, human=human, stdin=message)

    def focus(self, target):
        from .install import navigation
        if not navigation()["enabled"]:
            raise Error("Agent navigation is off. Enable explicitly with rex-agents navigation on; Rex Remote Control must also be enabled.")
        row = self.target(self.listing()["sessions"], target)
        mapping = row.get("rex")
        if not mapping or not mapping.get("location"):
            raise Error("Navigation unavailable: no live Rex pane; Reason messaging remains available")
        location = mapping["location"]
        host = mapping.get("host")
        self.live_location(location, host)
        client = self.client
        if not client:
            clients = decode(self.rex("client", "ls", "--json"))["clients"]
            apps = [c for c in clients if c.get("info", {}).get("kind") == "app"]
            if len(apps) != 1:
                raise Error("Set --client to the initiating Rex app; available apps are ambiguous")
            client = apps[0]["client_id"]
        # Select on the initiating server/app, even for a pane on another host.
        self.rex("-C", client, "do", "session.select", f"session_id={location['session']}")
        self.rex("focus", "-s", location["session"], location["block"], server=host or location["server"])
        return location

    @contextlib.contextmanager
    def launch_lock(self):
        self.cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(self.cache/"launch.lock", "a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def launch(self, kind, name, cwd, task=None, host=None, model=None, effort=None):
        sender = native_identity(allow_human=True)
        owner = ":".join(sender) if sender else None
        own = read(self.locator_path(*sender), {}) if sender else {}
        # An inherited token is not proof that this native conversation is a worker.
        if sender and own.get("kind") == sender[0] and own.get("native_id") == sender[1]:
            token = own.get("launch")
            parent = read(self.cache/"launches"/f"{token}.json", {}) if token else {}
            if parent.get("owner"):
                raise Error("Owned workers cannot launch nested workers")
        for label, value in (("model", model), ("effort", effort)):
            if value is not None and (not isinstance(value, str) or not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}(?:\[[A-Za-z0-9_-]+\])?", value)):
                raise Error(f"Invalid {label}: expected a model or effort identifier")
        if host and (model is not None or effort is not None):
            raise Error("Remote model and effort selection is not supported yet")
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", name):
            raise Error("Worker name must be 1–64 letters, digits, underscores, or hyphens")
        if host:
            if host not in [h["label"] for h in self.hosts()]:
                raise Error(f"Unknown configured Rex host: {host}")
            payload = json.dumps(dict(kind=kind, name=name, cwd=cwd, task=task))
            try:
                return decode(self.rex("do", "rex_agents_remote_launch", "--args", payload, "--json", server=host, timeout=27))
            except Error as exc:
                raise Error(f"Remote launch outcome uncertain on {host}; inspect its panes before retrying: {exc}") from exc
        directory = Path(cwd).expanduser().resolve()
        if not directory.is_dir():
            raise Error(f"Working directory does not exist: {directory}")
        if not shutil.which(kind):
            raise Error(f"Missing executable: {kind}")
        if not self.session or not self.block:
            if sender:
                if not own or own.get("ended") or not self.valid_location(own.get("location")):
                    raise Error("No live Rex locator for this agent; pass --session and --block explicitly")
                location = own["location"]
                self.server = self.server or location["server"]
                self.session = self.session or location["session"]
                self.block = self.block or location["block"]
        local_server = self.local_server() if model is not None or effort is not None else None
        if local_server and self.server and self.server != local_server:
            raise Error("Remote model and effort selection is not supported yet")
        if not self.session:
            sessions = decode(self.rex("ls", "--json"))
            sessions = sessions.get("sessions", []) if isinstance(sessions, dict) else sessions
            if len(sessions) != 1:
                raise Error("Set --session to the Rex session for this worker")
            self.session = sessions[0]["session_id"]
        if not self.block:
            view = decode(self.rex("session", "inspect", self.session, "--json"))
            window = next((w for w in view["windows"] if w["window_id"] == view["active_window_id"]), None)
            if not window or not window.get("focused_block_id"):
                raise Error("Set --block to the pane beside which the worker should start")
            self.block = window["focused_block_id"]
        server = self.server or local_server or decode(self.rex("whoami", "--json"))["endpoint"]
        with self.launch_lock():
            if any(r["name"] == name and r["status"] != "offline" for r in self.roster()["sessions"]):
                raise Error(f"Active worker name already exists: {name}")
            records = [read(path) for path in (self.cache/"launches").glob("*.json")]
            for old in records:
                if old["name"] != name or (old.get("failed") and not old.get("location")):
                    continue
                if old.get("location"):
                    state = self.pane_state(old["location"])
                    if state == "gone":
                        continue
                raise Error(f"Worker {name} already launched or creation is uncertain; inspect Rex before retrying")
            owned = sorted((r for r in records if owner and r.get("owner") == owner
                            and not r.get("failed") and self.valid_location(r.get("location"))
                            and r.get("split") in ("right", "below")),
                           key=lambda r: (r.get("created", 0), r.get("token", "")), reverse=True)
            direction = "below" if owned and owned[0]["split"] == "right" else "right"
            anchor = self.block
            location = dict(server=server, session=self.session, block=self.block)
            try:
                blocks = self.pane_blocks(location)
            except Error:
                blocks = []
            window = next((b.get("window_id") for b in blocks if b["block_id"] == self.block), None)
            # Stay in the driver's tab; a moved worker must not redirect later splits.
            if window:
                same_window = {b["block_id"] for b in blocks if b.get("window_id") == window}
                for previous in owned:
                    target = previous["location"]
                    if (target["server"] == server and target["session"] == self.session
                            and target["block"] in same_window and self.pane_state(target) == "live"):
                        anchor = target["block"]
                        break
            token = str(uuid.uuid4())
            path = self.cache/"launches"/f"{token}.json"
            record = dict(token=token, name=name, kind=kind, created=time.time(), has_task=task is not None,
                          owner=owner, split=direction)
            atomic(path, record)
            payload = base64.urlsafe_b64encode(json.dumps(dict(kind=kind, name=name, task=task, token=token,
                                                             model=model, effort=effort)).encode()).decode()
            try:
                result = decode(self.rex("split", "-s", self.session, "-b", anchor, f"--split={direction}", "-c", str(directory),
                                         "--label", f"rex-agents:{token}", "--focus=false", "--json",
                                         "--", str(CLI), "_worker", payload))
                if (not isinstance(result, dict) or not isinstance(result.get("block_ids"), list)
                        or not result["block_ids"] or not isinstance(result["block_ids"][0], str)
                        or not result["block_ids"][0].startswith("block:")):
                    raise Error("Incompatible Rex split result")
            except Error as exc:
                # Transport failures can occur after the server created the pane.
                definite = isinstance(exc, CommandError) and any(
                    word in str(exc).lower() for word in
                    ("unknown flag", "unknown command", "invalid", "not found", "does not exist"))
                if definite:
                    record["failed"] = str(exc)
                    atomic(path, record)
                    raise
                raise Error(f"Launch outcome uncertain for {name}; reservation {token}. Inspect Rex before retrying.") from exc
            record = read(path, record)
            record["location"] = dict(server=server, session=self.session, block=result["block_ids"][0])
            atomic(path, record)
            return dict(result, name=name, registration="pending", launch=token)

    def cleanup(self):
        sender = native_identity()
        owner = ":".join(sender)
        own = read(self.locator_path(*sender), {})
        own_location = own.get("location")
        result = dict(closed=[], gone=[], uncertain=[])
        with self.launch_lock():
            owned = [(path, record) for path in sorted((self.cache/"launches").glob("*.json"))
                     if (record := read(path)).get("owner") == owner]
            if not owned:
                return result
            try:
                server = self.local_server()
            except Error:
                server = None
            current = dict(server=server, session=self.session, block=self.block)
            for path, record in owned:
                location = record.get("location")
                if server and self.valid_location(location) and location["server"] != server:
                    continue
                item = dict(name=record.get("name"), launch=path.stem, location=location)
                if not server:
                    result["uncertain"].append(dict(item, error="Local Rex server unknown"))
                    continue
                if not self.valid_location(location):
                    result["uncertain"].append(dict(item, error="Missing or invalid pane location"))
                    continue
                if location == current or location == own_location:
                    result["uncertain"].append(dict(item, error="Refusing to close the driver's own pane"))
                    continue
                locators = self.locators()
                active = [locator for locator in locators if not locator.get("ended")]
                if any(locator.get("location") == location and locator.get("launch") != path.stem
                       for locator in active):
                    result["uncertain"].append(dict(item, error="Pane belongs to another native conversation"))
                    continue
                if any(locator.get("launch") == path.stem and locator.get("location") != location
                       for locator in active):
                    result["uncertain"].append(dict(item, error="Worker native conversation moved to another pane"))
                    continue
                state = self.pane_state(location)
                if state == "unknown":
                    result["uncertain"].append(dict(item, error="Pane state unknown"))
                    continue
                outcome = "gone"
                if state in ("live", "exited"):
                    error = "Pane absence could not be confirmed after close"
                    try:
                        self.rex("block", "close", "-s", location["session"], location["block"],
                                 server=location["server"])
                    except Error as exc:
                        error = str(exc)
                    if self.pane_state(location) != "gone":
                        result["uncertain"].append(dict(item, error=error))
                        continue
                    outcome = "closed"
                for locator in self.locators():
                    if locator.get("launch") == path.stem and locator.get("location") == location:
                        locator["ended"] = True
                        atomic(self.locator_path(locator["kind"], locator["native_id"]), locator)
                path.unlink()
                result[outcome].append(item)
        return result

    def worker(self, payload):
        value = decode(base64.urlsafe_b64decode(payload).decode())
        path = self.cache/"launches"/f"{value['token']}.json"
        record = read(path, {})
        record["location"] = dict(server=self.server, session=self.session, block=self.block)
        atomic(path, record)
        env = clean_env()
        env["REX_AGENTS_LAUNCH"] = value["token"]
        argv = [value["kind"]]
        if value["kind"] == "claude":
            argv += ["--name", value["name"]]
        else:
            # The shared app server does not carry the launching terminal environment into hooks.
            argv += ["--no-daemon"]
        if value.get("model") is not None:
            argv += ["--model" if value["kind"] == "claude" else "-m", value["model"]]
        if value.get("effort") is not None:
            argv += (["--effort", value["effort"]] if value["kind"] == "claude" else
                     ["-c", "model_reasoning_effort=" + json.dumps(value["effort"])])
        if value.get("task") is not None:
            argv += ["--", value["task"]]
        try:
            os.execvpe(argv[0], argv, env)
        except OSError as exc:
            record["failed"] = str(exc)
            atomic(path, record)
            raise Error(f"Worker failed to start: {exc}") from exc
