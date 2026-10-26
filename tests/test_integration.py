import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rex_agents.core import CLI, CommandError, Error, Integration, atomic, clean_env, identity_env, native_identity, read, run
from rex_agents.install import EVENTS, MARKER, edit_hooks, install


def session(address="juan/one", name="one", me=False, **kw):
    return dict(address=address, name=name, person="juan", machine="mac", agent="codex",
                cwd="/same/repo", repo="repo", status="idle", is_me=me, **kw)


class Fake(Integration):
    def __init__(self, cache):
        super().__init__(cache=cache, server="local", session="session:one", block="block:parent")
        self.rows = [session(), session("juan/two", "two")]
        self.native = {"id-one": "juan/one", "id-two": "juan/two"}
        self.sent = []
        self.closed = set()
        self.host_rows = []
        self.calls = []
        self.launch_error = False
        self.blocks = {"block:parent": "window:parent"}

    def reason(self, *args, identity=None, human=False, stdin=None):
        self.calls.append((args, identity, human))
        if args[0] == "who":
            rows = copy.deepcopy(self.rows)
            for row in rows:
                row["is_me"] = bool(identity and self.native.get(identity[1]) == row["address"])
            return json.dumps(dict(sessions=rows, machine="mac", person="juan"))
        if args[0] == "send":
            self.sent.append((args, stdin, identity, human))
            return "message-id: pushed\n"
        if args[0] == "status":
            for row in self.rows:
                if self.native.get(identity[1]) == row["address"]:
                    row["name"] = args[2]
                    row["address"] = "juan/" + args[2]
                    self.native[identity[1]] = row["address"]
            return "renamed"
        raise AssertionError(args)

    def hosts(self):
        return self.host_rows

    def rex(self, *args, server=None, timeout=12):
        self.calls.append((args, server))
        if args[:2] == ("block", "call"):
            if args[5] in self.closed:
                raise Error("pane missing")
            return json.dumps({"child": {"pid": 100}, "last_exit": None})
        if args[:2] == ("block", "ls"):
            return json.dumps({"blocks": [{"block_id": block, "window_id": window}
                                          for block, window in self.blocks.items()
                                          if block not in self.closed]})
        if args[0] == "split":
            if self.launch_error:
                raise Error("timeout")
            self.blocks["block:new"] = "window:parent"
            self.closed.discard("block:new")
            return json.dumps({"block_ids": ["block:new"], "window_id": "window:new"})
        if args[:2] == ("client", "ls"):
            return json.dumps({"clients": [{"client_id": "client:app", "info": {"kind": "app"}}]})
        if args[:2] == ("do", "rex_agents_registry"):
            if server == "missing":
                raise Error("host unavailable")
            return json.dumps({"mappings": [{"address": "juan/two", "person": "juan", "machine": "mac",
                "native_id": "remote-two", "kind": "codex", "location": {"server": "unix:remote", "session": "session:remote", "block": "block:remote"}}]})
        if args[:2] == ("do", "rex_agents_remote_launch"):
            return json.dumps({"registration": "pending", "block_ids": ["block:remote"]})
        return "{}"


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = Fake(Path(self.tmp.name)/"cache")
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        nav = patch("rex_agents.install.navigation", return_value={"enabled": True})
        nav.start()
        self.addCleanup(nav.stop)

    def hook(self, native="id-one", block="block:one", event="SessionStart"):
        self.app.block = block
        self.app.hook("codex", event, {"session_id": native})

    def test_same_repository_exact_native_identity(self):
        self.hook()
        self.hook("id-two", "block:two")
        rows = self.app.listing()["sessions"]
        self.assertEqual([r["rex"]["location"]["block"] for r in rows], ["block:one", "block:two"])

    def test_rename_refreshes_address(self):
        self.hook()
        self.app.rows[0].update(address="juan/renamed", name="renamed")
        self.app.native["id-one"] = "juan/renamed"
        self.assertEqual(self.app.registry()["mappings"][0]["address"], "juan/renamed")

    def test_resume_moves_native_identity(self):
        self.hook()
        self.hook(block="block:resumed")
        self.assertEqual(len(self.app.locators()), 1)
        self.assertEqual(self.app.registry()["mappings"][0]["location"]["block"], "block:resumed")

    def test_clear_invalidates_previous_conversation(self):
        self.hook()
        self.hook("id-two")
        self.assertEqual(len(self.app.registry()["mappings"]), 1)

    def test_end_from_old_pane_does_not_invalidate_resumed_session(self):
        self.hook()
        self.hook(block="block:resumed")
        self.hook(block="block:one", event="SessionEnd")
        self.assertEqual(self.app.registry()["mappings"][0]["location"]["block"], "block:resumed")

    def test_end_invalidates_navigation(self):
        self.hook()
        self.hook(event="SessionEnd")
        self.assertEqual(self.app.registry()["mappings"], [])

    def test_start_records_without_network(self):
        with patch.object(self.app, "reason", side_effect=AssertionError("network")):
            self.hook()
        self.assertEqual(len(self.app.locators()), 1)

    def test_unregistered_mapping_stays_pending(self):
        self.hook("unregistered")
        self.assertEqual(self.app.registry()["mappings"], [])
        self.assertTrue(self.app.locators())

    def test_nested_codex_does_not_take_claude_pane(self):
        self.app.hook("claude-code", "SessionStart", {"session_id": "claude-parent"})
        os.environ["CLAUDECODE"] = "1"
        self.app.hook("codex", "SessionStart", {"session_id": "codex-child"})
        records = self.app.locators()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["native_id"], "claude-parent")
        self.assertFalse(records[0]["ended"])

    def test_nested_claude_does_not_take_codex_pane(self):
        self.hook()
        os.environ["CODEX_THREAD_ID"] = "id-one"
        self.app.hook("claude-code", "SessionStart", {"session_id": "claude-child"})
        self.assertEqual(len(self.app.locators()), 1)
        self.assertFalse(self.app.locators()[0]["ended"])

    def test_claude_subagent_does_not_take_parent_pane(self):
        self.app.hook("claude-code", "SessionStart", {"session_id": "parent"})
        self.app.hook("claude-code", "SessionStart", {"session_id": "child", "agent_id": "subagent"})
        self.assertEqual(len(self.app.locators()), 1)
        self.assertFalse(self.app.locators()[0]["ended"])

    def test_nested_claude_rejected_but_clear_can_replace_parent(self):
        self.app.hook("claude-code", "SessionStart", {"session_id": "parent"})
        os.environ.update(REX_AGENTS_KIND="claude-code", REX_AGENTS_NATIVE_ID="parent")
        self.app.hook("claude-code", "SessionStart", {"session_id": "child", "source": "startup"})
        self.assertEqual(len(self.app.locators()), 1)
        self.app.hook("claude-code", "SessionStart", {"session_id": "new", "source": "clear"})
        active = [r for r in self.app.locators() if not r["ended"]]
        self.assertEqual([r["native_id"] for r in active], ["new"])

    def test_registry_does_not_rename_agents(self):
        atomic(self.app.cache/"launches/token.json", {"name": "worker"})
        os.environ["REX_AGENTS_LAUNCH"] = "token"
        self.hook()
        self.app.registry()
        self.assertFalse(any(c[0][0] == "status" for c in self.app.calls))

    def test_roster_survives_unreachable_rex_server(self):
        with patch.object(self.app, "hosts", side_effect=Error("server unavailable")):
            data = self.app.listing()
        self.assertEqual(len(data["sessions"]), 2)
        self.assertIn("Rex hosts unavailable", data["warnings"][0])

    def test_rex_request_timeout_honors_long_remote_budget(self):
        with patch("rex_agents.core.run", return_value="{}") as runner:
            Integration(cache=self.app.cache).rex("do", "rex_agents_remote_launch", timeout=27)
        self.assertIn("25s", runner.call_args.args[0])
        self.assertEqual(runner.call_args.kwargs["timeout"], 27)

    def test_closed_session_does_not_block_relaunch(self):
        with patch("shutil.which", return_value="/bin/codex"):
            self.app.launch("codex", "worker", self.tmp.name)
            original = self.app.rex
            def after_close(*args, **kwargs):
                if args[:2] in (("block", "call"), ("block", "ls")):
                    raise CommandError('Error: session target "session:gone" not found')
                return original(*args, **kwargs)
            with patch.object(self.app, "rex", side_effect=after_close):
                result = self.app.launch("codex", "worker", self.tmp.name)
        self.assertEqual(result["registration"], "pending")

    def test_remote_timeout_reports_uncertain_creation(self):
        self.app.host_rows = [{"label": "remote"}]
        with patch.object(self.app, "rex", side_effect=Error("timeout")):
            with self.assertRaisesRegex(Error, "Remote launch outcome uncertain on remote"):
                self.app.launch("codex", "worker", "/remote", host="remote")

    def test_no_directory_fallback(self):
        self.app.server = self.app.session = self.app.block = None
        self.app.hook("codex", "SessionStart", {"session_id": "id-one", "cwd": "/same/repo"})
        self.assertEqual(self.app.locators(), [])

    def test_missing_identity_prevents_send(self):
        with self.assertRaisesRegex(Error, "No native agent identity"):
            self.app.send("two", "hello")
        self.assertFalse(self.app.sent)

    def test_conflicting_inherited_native_identities_fail_closed(self):
        os.environ.update(CODEX_THREAD_ID="id-one", CLAUDE_CODE_SESSION_ID="claude-parent")
        with self.assertRaisesRegex(Error, "Conflicting inherited"):
            self.app.send("two", "hello")
        self.assertFalse(self.app.sent)

    def blocked(self, owner="codex:id-one", kind="codex", event="PermissionRequest", **payload):
        atomic(self.app.cache/"launches"/"tok.json", dict(token="tok", name="two", owner=owner))
        os.environ["REX_AGENTS_LAUNCH"] = "tok"
        self.app.block = "block:two"
        self.app.hook(kind, event, dict(session_id="id-two", **payload))
        return [(args, stdin, identity) for args, stdin, identity, human in self.app.sent]

    def test_owned_worker_permission_prompt_notifies_driver(self):
        sent = self.blocked(tool_name="Bash", tool_input={"command": "rm x"})
        self.assertEqual(sent, [(("send", "juan/one", "--fyi", "--notify", "--from", "codex:id-two"),
                                 "two is waiting in its Rex pane: approve Bash: rm x", ("codex", "id-two"))])

    def test_owned_claude_worker_question_lists_options(self):
        self.app.rows[1]["agent"] = "claude-code"
        sent = self.blocked(kind="claude-code", event="PreToolUse", tool_name="AskUserQuestion",
                            tool_input={"questions": [{"question": "Which DB?", "options": [{"label": "Postgres"}, {"label": "SQLite"}]}]})
        self.assertEqual(sent[0][1], "two is waiting in its Rex pane: Which DB? [Postgres, SQLite]")

    def test_malformed_question_payload_still_alerts(self):
        for questions in ("abc", None, ["x"], [{"question": "Q", "options": None}], [{"question": "Q", "options": ["a"]}]):
            self.app.sent.clear()
            with self.subTest(questions=questions):
                sent = self.blocked(tool_name="AskUserQuestion", tool_input={"questions": questions})
                self.assertEqual(len(sent), 1)

    def test_human_launched_worker_prompt_notifies_its_person(self):
        sent = self.blocked(owner=None, tool_name="Bash", tool_input={})
        self.assertEqual(sent[0][0], ("send", "juan", "--notify", "--from", "codex:id-two"))

    def test_blocking_prompt_alerts_only_launched_workers(self):
        self.hook(event="PermissionRequest")
        self.assertEqual(self.app.sent, [])

    def test_unresolvable_driver_does_not_break_worker_hook(self):
        self.app.rows[0]["status"] = "offline"
        self.assertEqual(self.blocked(tool_name="Bash"), [])

    def test_claude_hook_identity_supersedes_stale_clear_environment(self):
        os.environ.update(CLAUDE_CODE_SESSION_ID="old", REX_AGENTS_KIND="claude-code", REX_AGENTS_NATIVE_ID="new")
        self.assertEqual(native_identity(), ("claude-code", "new"))

    def test_unregistered_sender_never_falls_back_to_terminal(self):
        os.environ["CODEX_THREAD_ID"] = "unknown"
        with self.assertRaisesRegex(Error, "is_me"):
            self.app.send("two", "hello")
        self.assertFalse(self.app.sent)

    def test_literal_message_fyi_and_reply_id(self):
        os.environ["CODEX_THREAD_ID"] = "id-one"
        message = "line one\n'quotes' \"x\" $(touch /tmp/never) `false`; $HOME\\\n"
        self.assertEqual(self.app.send("two", message, fyi=True, reply_to="original-id"), "message-id: pushed\n")
        args, text, identity, human = self.app.sent[0]
        self.assertEqual(text, message)
        self.assertEqual(identity, ("codex", "id-one"))
        self.assertIn("codex:id-one", args)
        self.assertIn("--fyi", args)
        self.assertIn("original-id", args)
        self.assertFalse(human)

    def test_human_action_has_no_agent_identity(self):
        os.environ["CODEX_THREAD_ID"] = "id-one"
        self.app.send("two", "hi", human=True)
        self.assertTrue(self.app.sent[0][3])
        self.assertIsNone(self.app.sent[0][2])
        self.assertNotIn("--from", self.app.sent[0][0])

    def test_ambiguous_target(self):
        self.app.rows[1]["name"] = "one"
        with self.assertRaisesRegex(Error, "ambiguous"):
            self.app.send("one", "hi", human=True)
        self.app.send("juan/two", "hi", human=True)

    def test_navigation_off_performs_no_rex_action(self):
        with patch("rex_agents.install.navigation", return_value={"enabled": False}):
            with self.assertRaisesRegex(Error, "navigation is off"):
                self.app.focus("one")
        self.assertFalse(self.app.calls)

    def test_agent_launch_uses_its_native_locator_when_rex_environment_is_missing(self):
        self.hook()
        self.app.session = self.app.block = None
        os.environ["CODEX_THREAD_ID"] = "id-one"
        with patch("shutil.which", return_value="/bin/codex"):
            self.app.launch("codex", "worker", self.tmp.name)
        args = next(c[0] for c in self.app.calls if c[0][0] == "split")
        self.assertEqual(args[args.index("-b")+1], "block:one")

    def test_unmapped_agent_cannot_split_the_users_focused_pane(self):
        self.app.session = self.app.block = None
        os.environ["CODEX_THREAD_ID"] = "unmapped"
        with patch("shutil.which", return_value="/bin/codex"):
            with self.assertRaisesRegex(Error, "pass --session and --block"):
                self.app.launch("codex", "worker", self.tmp.name)
        self.assertFalse(any(c[0][0] == "split" for c in self.app.calls))

    def test_worker_opens_background_pane_at_explicit_anchor(self):
        with patch("shutil.which", return_value="/bin/codex"):
            self.app.launch("codex", "worker", self.tmp.name)
        args = next(c[0] for c in self.app.calls if c[0][0] == "split")
        self.assertEqual(args[args.index("-b")+1], "block:parent")
        self.assertIn("--focus=false", args)
        self.assertIn("--split=right", args)

    def test_closed_pane_does_not_prevent_messaging(self):
        self.hook()
        self.app.closed.add("block:one")
        with self.assertRaisesRegex(Error, "Navigation unavailable"):
            self.app.focus("one")
        self.app.send("one", "hi", human=True)
        self.assertTrue(self.app.sent)

    def test_remote_unavailable_still_lists_agents(self):
        self.app.host_rows = [{"label": "missing"}]
        data = self.app.listing()
        self.assertEqual(len(data["sessions"]), 2)
        self.assertIn("navigation unavailable", data["warnings"][0])

    def test_remote_mapping_uses_configured_host_for_pane(self):
        self.app.host_rows = [{"label": "remote"}]
        self.app.focus("two")
        self.assertTrue(any(c[0][0] == "focus" and c[1] == "remote" for c in self.app.calls))
        self.assertTrue(any(c[0][:3] == ("-C", "client:app", "do") and c[1] is None for c in self.app.calls))

    def test_remote_launch_does_not_interpret_local_path(self):
        self.app.host_rows = [{"label": "remote"}]
        result = self.app.launch("codex", "remote-worker", "/only/on/remote", "task\n'$(literal)'", "remote")
        self.assertEqual(result["block_ids"], ["block:remote"])

    def test_unknown_host_is_rejected(self):
        with self.assertRaisesRegex(Error, "Unknown configured"):
            self.app.launch("codex", "worker", "/tmp", host="unknown")

    def test_duplicate_active_name_creates_no_pane(self):
        with patch("shutil.which", return_value="/bin/codex"):
            with self.assertRaisesRegex(Error, "already exists"):
                self.app.launch("codex", "one", self.tmp.name)
        self.assertFalse(any(c[0][0] == "split" for c in self.app.calls))

    def test_pending_launch_cannot_duplicate_pane(self):
        with patch("shutil.which", return_value="/bin/codex"):
            result = self.app.launch("codex", "worker", self.tmp.name, "initial task")
            self.assertEqual(result["registration"], "pending")
            with self.assertRaisesRegex(Error, "already launched"):
                self.app.launch("codex", "worker", self.tmp.name, "initial task")
        self.assertEqual(sum(c[0][0] == "split" for c in self.app.calls), 1)

    def test_definite_launch_failure_allows_retry(self):
        original = self.app.rex
        with patch("shutil.which", return_value="/bin/codex"):
            with patch.object(self.app, "rex", side_effect=CommandError("invalid terminal layout")):
                with self.assertRaisesRegex(Error, "invalid terminal layout"):
                    self.app.launch("codex", "worker", self.tmp.name)
            result = self.app.launch("codex", "worker", self.tmp.name)
        self.assertEqual(result["block_ids"], ["block:new"])
        self.assertEqual(sum(c[0][0] == "split" for c in self.app.calls), 1)

    def test_closed_worker_can_be_relaunched(self):
        with patch("shutil.which", return_value="/bin/codex"):
            self.app.launch("codex", "worker", self.tmp.name)
            self.app.closed.add("block:new")
            self.app.launch("codex", "worker", self.tmp.name)
        self.assertEqual(sum(c[0][0] == "split" for c in self.app.calls), 2)

    def test_unavailable_existing_worker_does_not_create_duplicate(self):
        with patch("shutil.which", return_value="/bin/codex"):
            self.app.launch("codex", "worker", self.tmp.name)
            with patch.object(self.app, "live_location", side_effect=Error("host unreachable")):
                with patch.object(self.app, "rex", side_effect=Error("host unreachable")):
                    with self.assertRaisesRegex(Error, "creation is uncertain"):
                        self.app.launch("codex", "worker", self.tmp.name)
        self.assertEqual(sum(c[0][0] == "split" for c in self.app.calls), 1)

    def test_closed_process_in_existing_pane_is_not_navigable(self):
        with patch.object(self.app, "rex", return_value=json.dumps({"child": None, "last_exit": {"code": 1}})):
            with self.assertRaisesRegex(Error, "process has ended"):
                self.app.live_location({"server": "local", "session": "session:one", "block": "block:one"})

    def test_missing_engine_never_calls_installing_wrapper(self):
        with patch("os.access", return_value=False), patch("shutil.which", return_value=None):
            with patch("rex_agents.core.run") as runner:
                with self.assertRaisesRegex(Error, "engine missing"):
                    Integration(cache=self.app.cache).roster()
                runner.assert_not_called()

    def test_uncertain_launch_cannot_duplicate_task(self):
        self.app.launch_error = True
        with patch("shutil.which", return_value="/bin/codex"):
            with self.assertRaisesRegex(Error, "uncertain"):
                self.app.launch("codex", "worker", self.tmp.name, "initial task")
            with self.assertRaisesRegex(Error, "uncertain"):
                self.app.launch("codex", "worker", self.tmp.name, "initial task")
        self.assertEqual(sum(c[0][0] == "split" for c in self.app.calls), 1)

    def test_initial_prompt_passed_once_as_argument(self):
        atomic(self.app.cache/"launches/token.json", {"name": "worker"})
        import base64
        task = "multiple\nlines; $(literal) 'quote'"
        payload = base64.urlsafe_b64encode(json.dumps(dict(kind="claude", name="worker", task=task, token="token")).encode()).decode()
        with patch("os.execvpe") as execute:
            self.app.worker(payload)
        self.assertEqual(execute.call_args.args[1], ["claude", "--name", "worker", "--", task])
        self.assertNotIn("CODEX_THREAD_ID", execute.call_args.args[2])

    def test_codex_worker_retains_terminal_context_without_changing_permissions(self):
        import base64
        atomic(self.app.cache/"launches/token.json", {"name": "worker"})
        payload = base64.urlsafe_b64encode(json.dumps(dict(kind="codex", name="worker", task="once", token="token")).encode()).decode()
        with patch("os.execvpe") as execute:
            self.app.worker(payload)
        self.assertEqual(execute.call_args.args[1], ["codex", "--no-daemon", "--", "once"])

    def test_send_failure_is_not_success(self):
        original = self.app.reason
        def fail(*args, **kw):
            if args[0] == "send":
                raise Error("delivery failed")
            return original(*args, **kw)
        with patch.object(self.app, "reason", side_effect=fail):
            with self.assertRaisesRegex(Error, "delivery failed"):
                self.app.send("one", "hi", human=True)

    def test_worker_name_is_assigned_only_once(self):
        atomic(self.app.cache/"launches/token.json", {"name": "worker"})
        os.environ["REX_AGENTS_LAUNCH"] = "token"
        self.hook()
        self.hook(event="PostToolUse")
        self.app.registry()
        self.app.rows[0].update(name="user-renamed", address="juan/user-renamed")
        self.app.native["id-one"] = "juan/user-renamed"
        self.app.registry()
        self.assertEqual(self.app.rows[0]["name"], "user-renamed")

    def test_argument_arrays_preserve_spaces_and_shell_syntax(self):
        text = "quotes ' \"; `x` $(x)\nsecond line"
        self.assertEqual(run(["/usr/bin/printf", "%s", text]), text)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="rex agents ' ")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.claude = self.home/".claude/settings.json"
        self.codex = self.home/".codex/hooks.json"
        self.init = self.home/".config/rex/init.lua"
        self.original = {"custom": True, "hooks": {"Stop": [{"matcher": "*", "hooks": [{"type": "command", "command": "unrelated"}]}]}}
        atomic(self.claude, self.original)
        atomic(self.codex, self.original)
        atomic(self.init, '-- unrelated\nrex.action{name="existing",title="Existing",run=function() end}\n')

    def test_repeated_install_remove_preserves_unrelated_config(self):
        original_lua = self.init.read_text()
        install(self.home)
        install(self.home)
        for path in (self.claude, self.codex):
            data = read(path)
            self.assertEqual(len(data["hooks"]["Stop"]), 2)
        self.assertEqual(self.init.read_text().count(MARKER), 1)
        data = read(self.claude)
        data["new_setting"] = 42
        atomic(self.claude, data)
        install(self.home, remove=True)
        install(self.home, remove=True)
        self.assertEqual(read(self.codex), self.original)
        self.assertEqual(read(self.claude), dict(self.original, new_setting=42))
        self.assertEqual(self.init.read_text(), original_lua)
        self.assertFalse((self.home/".local/bin/rex-agents").exists())

    def test_mixed_hook_group_preserves_others(self):
        data = edit_hooks({}, "codex")
        data["hooks"]["Stop"][0]["hooks"].append({"type": "command", "command": "other"})
        clean = edit_hooks(data, "codex", True)
        self.assertEqual(clean["hooks"]["Stop"][0]["hooks"], [{"type": "command", "command": "other"}])

    def test_blocking_prompt_hooks_match_each_harness(self):
        claude, codex = edit_hooks({}, "claude-code")["hooks"], edit_hooks({}, "codex")["hooks"]
        self.assertEqual(claude["PreToolUse"][0]["matcher"], "AskUserQuestion")
        self.assertNotIn("matcher", claude["PermissionRequest"][0])
        self.assertIn("PermissionRequest", codex)
        self.assertNotIn("PreToolUse", codex)

    def test_conflicting_cli_aborts_before_hook_edits(self):
        atomic(self.home/".local/bin/rex-agents", "unrelated")
        with self.assertRaisesRegex(Error, "unrelated"):
            install(self.home)
        self.assertEqual(read(self.codex), self.original)

    def test_invalid_json_is_not_overwritten(self):
        atomic(self.codex, "{invalid}")
        with self.assertRaisesRegex(Error, "Cannot read"):
            install(self.home)
        self.assertEqual(self.codex.read_text(), "{invalid}")


class ProcessBoundaryTests(unittest.TestCase):
    def test_cli_preserves_message_bytes_and_explicit_sender(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory(prefix="rex agents ' ") as directory:
            root = Path(directory)
            engine = root/"fake reason"
            output = root/"sent.json"
            engine.write_text('''#!'''+sys.executable+'''
import json,os,sys
if sys.argv[1] == "who":
    rows=[]
    for name in ("one","two"):
        rows.append(dict(address="juan/"+name,name=name,person="juan",machine="mac",agent="codex",status="idle",is_me=name=="one" and os.environ.get("REASON_NETWORK_SESSION")=="native-one"))
    print(json.dumps(dict(person="juan",machine="mac",sessions=rows)))
else:
    open(os.environ["REX_AGENTS_TEST_SENT"],"w").write(json.dumps(dict(argv=sys.argv[1:],message=sys.stdin.read())))
    print("message boundary-id: queued")
''')
            engine.chmod(0o700)
            message = "first line\n'single' \"double\" $(printf literal); `printf literal` $HOME\\\n"
            message_file = root/"message with spaces.txt"
            message_file.write_text(message)
            env = dict(clean_env(), CODEX_THREAD_ID="native-one", REX_AGENTS_REASON=str(engine), REX_AGENTS_TEST_SENT=str(output))
            result = subprocess.run([sys.executable, str(CLI), "send", "two", "--message-file", str(message_file), "--fyi", "--reply-to", "original-id"], env=env, capture_output=True,text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = read(output)
            self.assertEqual(data["message"], message)
            self.assertEqual(data["argv"], ["send", "juan/two", "--from", "codex:native-one", "--fyi", "--reply-to", "original-id"])
            self.assertIn("boundary-id: queued", result.stdout)

    def test_uninstalled_hook_cannot_recreate_cache(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = dict(os.environ, XDG_DATA_HOME=str(root/"data"), XDG_CACHE_HOME=str(root/"cache"),
                       REX_SERVER="local", REX_SESSION="session:one", REX_BLOCK="block:one")
            result = subprocess.run([sys.executable, str(CLI), "_hook", "codex", "SessionStart"],
                                    input=json.dumps({"session_id":"native"}),env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse((root/"cache").exists())


class NavigationTests(unittest.TestCase):
    def test_default_off_and_toggle_persists_without_controlling_rex(self):
        from rex_agents.install import navigation, state_path
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"XDG_DATA_HOME": directory}):
                with patch("rex_agents.core.run", side_effect=AssertionError("must not control Rex")):
                    self.assertFalse(navigation()["enabled"])
                    atomic(state_path(), {"backup": "preserve-this"})
                    self.assertTrue(navigation("on")["enabled"])
                    self.assertTrue(navigation()["enabled"])
                    self.assertFalse(navigation("toggle")["enabled"])
                    self.assertEqual(read(state_path())["backup"], "preserve-this")
                    with self.assertRaisesRegex(Error, "Navigation mode"):
                        navigation("unexpected")

    def test_reinstall_preserves_navigation_preference(self):
        from rex_agents.install import navigation
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            with patch.dict(os.environ, {"XDG_DATA_HOME": str(home/"data")}, clear=True):
                install(home)
                navigation("on")
                install(home)
                self.assertTrue(navigation()["enabled"])
                install(home, remove=True)
                self.assertFalse(navigation()["enabled"])


if __name__ == "__main__":
    unittest.main()
