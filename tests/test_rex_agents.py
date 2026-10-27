import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from rex_agents import cli, core, install
from rex_agents.core import CLI, CommandError, Error, Integration, owner

DRIVER = ("claude-code", "drv")
ME = owner(DRIVER)


class Fake(Integration):
    """In-memory Rex: sessions hold blocks with sortable IDs, labels, and windows."""

    def __init__(self, cache, **kw):
        super().__init__(cache=cache, **kw)
        self.sessions, self.calls, self.close, self.n = {}, [], {}, 0
        self.split_error, self.split_creates, self.down = None, True, False
        self.ghosts = []  # sessions `ls` reports that close before their block listing

    def add(self, session, label="shell", window="w1"):
        self.n += 1
        block = f"block:{self.n:04d}"
        self.sessions.setdefault(session, []).append(dict(block_id=block, label=label, window_id=window))
        return block

    def labels(self):
        return [b["label"] for blocks in self.sessions.values() for b in blocks]

    def splits(self):
        return [c for c in self.calls if c[0] == "split"]

    def rex(self, *args, timeout=12):
        self.calls.append(args)
        if self.down:
            raise Error("rex: timed out")
        if args == ("ls", "--json"):
            return json.dumps({"sessions": [{"session_id": s} for s in [*self.sessions, *self.ghosts]]})
        if args[:2] == ("block", "ls"):
            if args[3] not in self.sessions:
                raise CommandError(f'session target "{args[3]}" not found')
            return json.dumps({"blocks": self.sessions[args[3]]})
        if args[0] == "split":
            session, anchor = args[2], args[4]
            window = next(b["window_id"] for b in self.sessions[session] if b["block_id"] == anchor)
            if self.split_creates:
                block = self.add(session, args[args.index("--label") + 1], window)
            if self.split_error:
                raise self.split_error
            return json.dumps({"anchor_id": anchor, "block_ids": [block]})
        if args[:2] == ("block", "close"):
            session, block = args[3], args[4]
            mode = self.close.get(block)
            if mode == "error":
                raise CommandError("close refused")
            if mode == "stay":
                return ""
            blocks = self.sessions.get(session, [])
            found = [b for b in blocks if b["block_id"] == block]
            if not found or mode == "notfound":
                for b in found:
                    blocks.remove(b)
                raise CommandError(f'block target "{block}" not found')
            blocks.remove(found[0])
            return ""
        raise AssertionError(args)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp/"h me's"
        self.home.mkdir()
        env = mock.patch.dict(os.environ, {"HOME": str(self.home)}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        which = mock.patch.object(core.shutil, "which", return_value="/bin/agent")
        which.start()
        self.addCleanup(which.stop)
        self.cwd = self.tmp/"work"
        self.cwd.mkdir()
        self.app = Fake(self.tmp/"cache", server="unix:s", session="session:a")
        self.app.block = self.driver = self.app.add("session:a")

    def agent(self, kind="claude-code", native_id="drv"):
        os.environ["CODEX_THREAD_ID" if kind == "codex" else "CLAUDE_CODE_SESSION_ID"] = native_id

    def launch(self, name, model="claude-opus-5-5", **kw):
        return self.app.launch(name, str(self.cwd), model, **kw)

    def argv(self, call):
        return list(call[call.index("--") + 1:])

    def option(self, call, flag):
        return call[call.index(flag) + 1]


class LaunchTests(Base):
    def test_claude_argv_passes_task_once_literally(self):
        self.agent()
        task = 'say "q" \'s\' $(id) `id` $HOME /a b/\n-- --model x'
        result = self.launch("w1", task=task, model="claude-opus-5-5", effort="xhigh")
        call = self.app.splits()[0]
        self.assertEqual(self.argv(call), ["/bin/agent", "--name", "w1", "--model", "claude-opus-5-5",
                                           "--effort", "xhigh", "--", task])
        self.assertIn("--focus=false", call)
        self.assertEqual(self.option(call, "--label"), f"rex-agents:{ME}:w1")
        self.assertEqual(self.option(call, "-b"), self.driver)
        self.assertEqual(self.option(call, "-c"), str(self.cwd.resolve()))
        self.assertEqual(result["registration"], "pending")

    def test_gpt_model_runs_codex(self):
        self.agent()
        self.launch("w1", model="gpt-6.1-sol", effort="high")
        self.assertEqual(self.argv(self.app.splits()[0]),
                         ["/bin/agent", "--no-daemon", "-m", "gpt-6.1-sol", "-c", 'model_reasoning_effort="high"'])

    def test_invalid_input_rejected_before_rex(self):
        self.agent()
        for kw in ({"name": "bad name"}, {"name": "x" * 65}, {"name": "w", "model": "a b"},
                   {"name": "w", "model": "llama-4"}, {"name": "w", "effort": "$(id)"}):
            name = kw.pop("name")
            with self.assertRaises(Error):
                self.launch(name, **kw)
        with self.assertRaises(Error):
            self.app.launch("w", str(self.tmp/"missing"), "claude-opus-5-5")
        self.assertEqual(self.app.calls, [])

    def test_cli_launch_requires_model(self):
        self.agent()
        argv = ["launch", "--name", "w1", "--cwd", str(self.cwd)]
        with mock.patch.object(cli, "Integration", return_value=self.app), mock.patch("sys.stdout"), \
                mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                cli.main(argv)
            self.assertEqual(cli.main([*argv, "--model", "gpt-6-astra"]), 0)
        self.assertEqual(self.argv(self.app.splits()[0]), ["/bin/agent", "--no-daemon", "-m", "gpt-6-astra"])

    def test_duplicate_name_refused_for_any_owner_and_session(self):
        self.agent()
        other = self.app.add("session:b", "rex-agents:feedfacefeedface:w1")
        with self.assertRaisesRegex(Error, "already has a Rex pane"):
            self.launch("w1")
        self.app.sessions["session:b"].clear()
        self.launch("w1")
        self.assertIn(f"rex-agents:{ME}:w1", self.app.labels())
        self.assertNotEqual(other, self.app.splits()[0])

    def test_failed_split_is_uncertain_and_retry_refused_if_created(self):
        self.agent()
        for error in (CommandError("connection reset"), Error("rex: timed out")):
            self.app.split_error = error
            name = f"w{len(self.app.splits())}"
            with self.assertRaisesRegex(Error, "outcome uncertain"):
                self.launch(name)
            self.app.split_error = None
            with self.assertRaisesRegex(Error, "already has a Rex pane"):
                self.launch(name)
        self.assertFalse((self.app.cache/"splits").exists())

    def test_failed_split_without_pane_allows_retry(self):
        self.agent()
        self.app.split_error, self.app.split_creates = CommandError("unknown flag"), False
        with self.assertRaises(Error):
            self.launch("w1")
        self.app.split_error, self.app.split_creates = None, True
        self.launch("w1")
        self.assertEqual(len(self.app.splits()), 2)

    def test_owned_worker_cannot_nest_but_human_worker_can(self):
        self.agent()
        self.app.sessions["session:a"][0]["label"] = "rex-agents:feedfacefeedface:parent"
        with self.assertRaisesRegex(Error, "nested"):
            self.launch("w1")
        self.app.sessions["session:a"][0]["label"] = "rex-agents:-:parent"
        self.launch("w1")

    def test_explicit_block_does_not_escape_nesting_guard(self):
        self.agent()
        worker = self.app.add("session:a", "rex-agents:feedfacefeedface:parent")
        os.environ["REX_BLOCK"] = worker
        with self.assertRaisesRegex(Error, "nested"):
            self.launch("w1")
        del os.environ["REX_BLOCK"]
        core.atomic(self.app.locator(DRIVER), dict(server="unix:s", session="session:a", block=worker))
        with self.assertRaisesRegex(Error, "nested"):
            self.launch("w1")
        self.assertEqual(self.app.splits(), [])

    def test_session_closing_mid_scan_is_skipped(self):
        self.agent()
        self.app.ghosts.append("session:gone")
        self.launch("w1")
        self.assertEqual(len(self.app.splits()), 1)

    def test_alternation_and_anchor(self):
        self.agent()
        seen = []
        for name in ("w1", "w2", "w3"):
            self.launch(name)
            call = self.app.splits()[-1]
            seen.append((self.option(call, "-b"), call[5]))
        w1, w2 = self.app.sessions["session:a"][1]["block_id"], self.app.sessions["session:a"][2]["block_id"]
        self.assertEqual(seen, [(self.driver, "--split=right"), (w1, "--split=below"), (w2, "--split=right")])
        self.app.sessions["session:a"].pop()  # manual close of w3
        self.app.add("session:a", f"rex-agents:{ME}:elsewhere", window="w2")
        self.launch("w4")
        call = self.app.splits()[-1]
        self.assertEqual((self.option(call, "-b"), call[5]), (w2, "--split=below"))

    def test_human_launch_always_right_from_driver(self):
        self.app.add("session:a", "rex-agents:-:old")
        for name in ("h1", "h2"):
            self.launch(name)
            call = self.app.splits()[-1]
            self.assertEqual((self.option(call, "-b"), call[5]), (self.driver, "--split=right"))
            self.assertEqual(self.option(call, "--label"), f"rex-agents:-:{name}")
        self.assertFalse((self.app.cache/"splits").exists())

    def test_locator_supplies_pane_for_codex_shell(self):
        self.agent("codex", "cx")
        app = Fake(self.tmp/"cache")
        app.sessions, app.n = self.app.sessions, self.app.n
        core.atomic(app.locator(("codex", "cx")), dict(server="unix:s", session="session:a", block=self.driver))
        app.launch("w1", str(self.cwd), "claude-opus-5-5")
        call = app.splits()[0]
        self.assertEqual((call[2], self.option(call, "-b")), ("session:a", self.driver))
        os.environ["CODEX_THREAD_ID"] = "unknown"
        with self.assertRaisesRegex(Error, "--session and --block"):
            Fake(self.tmp/"cache").launch("w2", str(self.cwd), "claude-opus-5-5")

    def test_identity_conflicts(self):
        os.environ.update(CODEX_THREAD_ID="cx", CLAUDECODE="1")
        with self.assertRaisesRegex(Error, "Conflicting"):
            self.launch("w1")
        del os.environ["CODEX_THREAD_ID"]
        with self.assertRaisesRegex(Error, "Incomplete"):
            self.launch("w1")
        self.assertEqual(self.app.calls, [])


class CleanupTests(Base):
    def test_closes_only_own_panes_across_sessions(self):
        self.agent()
        mine = [self.app.add("session:a", f"rex-agents:{ME}:a"), self.app.add("session:b", f"rex-agents:{ME}:b")]
        kept = [self.app.add("session:a", "rex-agents:feedfacefeedface:x"),
                self.app.add("session:b", "rex-agents:-:human"), self.app.add("session:b", "shell")]
        result = self.app.cleanup()
        self.assertEqual([i["block"] for i in result["closed"]], mine)
        self.assertEqual((result["gone"], result["uncertain"]), ([], []))
        left = [b["block_id"] for blocks in self.app.sessions.values() for b in blocks]
        self.assertEqual(sorted(left), sorted([self.driver, *kept]))
        self.assertEqual(self.app.cleanup(), dict(closed=[], gone=[], uncertain=[]))

    def test_uncertain_outcomes_keep_split_state(self):
        self.agent()
        self.launch("w1")
        splits = self.app.cache/"splits"/f"{ME}.json"
        self.app.sessions["session:a"][0]["label"] = f"rex-agents:{ME}:self"
        gone, stay, refused = (self.app.add("session:a", f"rex-agents:{ME}:{n}") for n in ("g", "s", "r"))
        self.app.close.update({gone: "notfound", stay: "stay", refused: "error"})
        result = self.app.cleanup()
        self.assertEqual([i["name"] for i in result["closed"]], ["w1"])
        self.assertEqual([i["block"] for i in result["gone"]], [gone])
        errors = {i["block"]: i["error"] for i in result["uncertain"]}
        self.assertIn("driver's own pane", errors[self.driver])
        self.assertIn("still present", errors[stay])
        self.assertIn("close refused", errors[refused])
        self.assertTrue(splits.exists())
        self.app.sessions["session:a"][0]["label"] = "shell"
        self.app.close.clear()
        self.assertEqual(self.app.cleanup()["uncertain"], [])
        self.assertFalse(splits.exists())

    def test_explicit_block_does_not_expose_running_pane(self):
        self.agent()
        running = self.app.add("session:a", f"rex-agents:{ME}:resumed")
        core.atomic(self.app.locator(DRIVER), dict(server="unix:s", session="session:a", block=running))
        os.environ["REX_BLOCK"] = running
        result = self.app.cleanup()
        self.assertIn(running, [b["block_id"] for b in self.app.sessions["session:a"]])
        self.assertEqual([i["block"] for i in result["uncertain"]], [running])
        del os.environ["REX_BLOCK"]
        self.app.cleanup()
        self.assertIn(running, [b["block_id"] for b in self.app.sessions["session:a"]])

    def test_rex_unavailable_is_uncertain(self):
        self.agent()
        self.app.down = True
        result = self.app.cleanup()
        self.assertEqual(len(result["uncertain"]), 1)
        self.assertIn("unavailable", result["uncertain"][0]["error"])

    def test_requires_agent_identity(self):
        with self.assertRaisesRegex(Error, "No native agent identity"):
            self.app.cleanup()

    def test_cli_exit_status_tracks_uncertainty(self):
        for uncertain, code in (([], 0), ([{"error": "x"}], 1)):
            fake = mock.Mock()
            fake.cleanup.return_value = dict(closed=[], gone=[], uncertain=uncertain)
            with mock.patch.object(cli, "Integration", return_value=fake), mock.patch("sys.stdout"):
                self.assertEqual(cli.main(["cleanup"]), code)


class HookTests(Base):
    def setUp(self):
        super().setUp()
        engine = self.tmp/"reason"
        engine.write_text("#!/bin/sh\n")
        engine.chmod(0o755)
        os.environ["REX_AGENTS_REASON"] = str(engine)
        self.sent = []
        def run(argv, *, env=None, stdin=None, timeout=12):
            self.sent.append((argv[1:], env, stdin))
            return json.dumps({"person": "juan"}) if argv[1] == "who" else ""
        patch = mock.patch.object(core, "run", side_effect=run)
        self.run = patch.start()
        self.addCleanup(patch.stop)
        self.app.block = self.app.add("session:a", "rex-agents:feedfacefeedface:helper")

    def locator(self, native_id="s1"):
        return core.read(self.app.locator(("claude-code", native_id)))

    def test_session_start_records_location(self):
        self.app.hook("claude-code", "SessionStart", {"session_id": "s1"})
        self.assertEqual(self.locator(), dict(server="unix:s", session="session:a", block=self.app.block))

    def test_session_start_skips_children_and_missing_context(self):
        self.app.hook("claude-code", "SessionStart", {"session_id": "s1", "agent_id": "sub"})
        Fake(self.tmp/"cache").hook("claude-code", "SessionStart", {"session_id": "s1"})
        os.environ["CODEX_THREAD_ID"] = "cx"
        self.app.hook("claude-code", "SessionStart", {"session_id": "s1"})
        del os.environ["CODEX_THREAD_ID"]
        os.environ["CLAUDECODE"] = "1"
        self.app.hook("codex", "SessionStart", {"session_id": "s1"})
        self.assertIsNone(self.locator())
        self.assertIsNone(core.read(self.app.locator(("codex", "s1"))))

    def test_blocking_prompt_alerts_human(self):
        self.app.hook("claude-code", "PermissionRequest",
                      {"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "rm -rf build"}})
        args, env, stdin = self.sent[-1]
        self.assertEqual(args, ["send", "juan", "--notify", "--from", "claude-code:s1"])
        self.assertEqual((env["REASON_NETWORK_AGENT"], env["REASON_NETWORK_SESSION"]), ("claude-code", "s1"))
        self.assertIn("helper is waiting", stdin)
        self.assertIn("rm -rf build", stdin)

    def test_owned_worker_question_goes_to_driver(self):
        for tool in ("AskUserQuestion", "mcp__reason-network__ask_user"):
            result = self.app.hook("claude-code", "PreToolUse", {"session_id": "s1", "tool_name": tool,
                                   "tool_input": {"questions": [{"question": "Ship?", "options": [{"label": "Yes"}]}]}})
            decision = result["hookSpecificOutput"]
            self.assertEqual((decision["hookEventName"], decision["permissionDecision"]), ("PreToolUse", "deny"))
            self.assertIn("send_message", decision["permissionDecisionReason"])
        self.assertEqual(self.sent, [])

    def test_human_launched_worker_question_alerts_human(self):
        self.app.sessions["session:a"][-1]["label"] = "rex-agents:-:helper"
        result = self.app.hook("claude-code", "PreToolUse", {"session_id": "s1", "tool_name": "AskUserQuestion",
                               "tool_input": {"questions": [{"question": "Ship?", "options": [{"label": "Yes"}, {"label": "No"}]}]}})
        self.assertIsNone(result)
        self.assertIn("Ship? [Yes, No]", self.sent[-1][2])

    def test_human_launched_worker_reason_question_is_left_to_reason(self):
        self.app.sessions["session:a"][-1]["label"] = "rex-agents:-:helper"
        self.assertIsNone(self.app.hook("claude-code", "PreToolUse", {"session_id": "s1",
                          "tool_name": "mcp__reason-network__ask_user", "tool_input": {"question": "Ship?"}}))
        self.assertEqual(self.sent, [])

    def test_cli_prints_hook_decision(self):
        fake = mock.Mock()
        fake.hook.return_value = {"hookSpecificOutput": {"permissionDecision": "deny"}}
        with mock.patch.object(cli, "Integration", return_value=fake), mock.patch.object(cli, "installed", return_value=True), \
                mock.patch("sys.stdin", io.StringIO('{"session_id": "s1"}')), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(cli.main(["_hook", "claude-code", "PreToolUse"]), 0)
        self.assertEqual(json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_non_worker_pane_and_reason_failure_are_quiet(self):
        self.app.sessions["session:a"][-1]["label"] = "shell"
        self.app.hook("claude-code", "PermissionRequest", {"session_id": "s1", "tool_name": "Bash"})
        self.assertEqual(self.sent, [])
        self.app.sessions["session:a"][-1]["label"] = "rex-agents:-:helper"
        self.run.side_effect = CommandError("daemon down")
        self.app.hook("claude-code", "PermissionRequest", {"session_id": "s1", "tool_name": "Bash"})
        self.run.side_effect = lambda argv, **kw: "{}"  # Reason output without `person`
        self.app.hook("claude-code", "PermissionRequest", {"session_id": "s1", "tool_name": "Bash"})

    def test_events_from_earlier_installs_send_nothing(self):
        for event in ("UserPromptSubmit", "PostToolUse", "Stop", "SessionEnd"):
            self.app.hook("claude-code", event, {"session_id": "s1", "tool_name": "Bash"})
        self.assertEqual(self.sent, [])


class InstallTests(Base):
    def setUp(self):
        super().setUp()
        legacy = install.hook_command("claude-code", "UserPromptSubmit")
        self.claude = self.home/".claude/settings.json"
        self.codex = self.home/".codex/hooks.json"
        core.atomic(self.claude, {"theme": "dark", "hooks": {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": legacy}, {"type": "command", "command": "other"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": install.hook_command("claude-code", "Stop")}]}]}})
        core.atomic(self.codex, {"hooks": {"SessionEnd": [{"hooks": [
            {"type": "command", "command": install.hook_command("codex", "SessionEnd")}]}]}})
        self.init = self.home/".config/rex/init.lua"
        self.init.parent.mkdir(parents=True)
        self.init.write_text("x = 1\n" + install.LEGACY_MARKER)
        (self.init.parent/"rex_agents.lua").write_text("-- Managed by rex-agents.\nreturn {}\n")

    def ours(self, path):
        document = core.read(path)
        return {event: [g.get("matcher") for g in groups for h in g["hooks"] if h["command"].startswith(str(CLI))]
                for event, groups in document.get("hooks", {}).items()} if document else {}

    def test_install_migrates_and_is_idempotent(self):
        install.install(self.home)
        first = (self.claude.read_text(), self.codex.read_text())
        install.install(self.home)
        self.assertEqual((self.claude.read_text(), self.codex.read_text()), first)
        claude = core.read(self.claude)
        self.assertEqual(claude["theme"], "dark")
        self.assertEqual(claude["hooks"]["UserPromptSubmit"][0]["hooks"], [{"type": "command", "command": "other"}])
        self.assertNotIn("Stop", claude["hooks"])
        self.assertEqual({k: v for k, v in self.ours(self.claude).items() if v},
                         {"SessionStart": [None], "PreToolUse": ["AskUserQuestion|mcp__reason-network__ask_user"],
                          "PermissionRequest": [None]})
        self.assertEqual(self.ours(self.codex), {"SessionStart": [None], "PermissionRequest": [None]})
        self.assertEqual(self.init.read_text(), "x = 1\n")
        self.assertFalse((self.init.parent/"rex_agents.lua").exists())
        self.assertEqual((self.home/".local/bin/rex-agents").resolve(), CLI.resolve())
        self.assertTrue(install.installed())

    def test_unrelated_paths_survive(self):
        module = self.init.parent/"rex_agents.lua"
        module.write_text("-- mine\n")
        install.install(self.home)
        self.assertEqual(module.read_text(), "-- mine\n")
        link = self.home/".agents/skills/rex-agents"
        install.install(self.home, remove=True)
        link.parent.mkdir(parents=True, exist_ok=True)
        link.write_text("unrelated")
        with self.assertRaisesRegex(Error, "unrelated path"):
            install.install(self.home)

    def test_uninstall_removes_only_ours(self):
        install.install(self.home)
        (self.home/".cache/rex-agents").mkdir(parents=True)
        install.install(self.home, remove=True)
        self.assertEqual({k: v for k, v in self.ours(self.claude).items() if v}, {})
        self.assertEqual(core.read(self.claude)["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"], "other")
        self.assertNotIn("hooks", core.read(self.codex))
        self.assertFalse((self.home/".local/bin/rex-agents").is_symlink())
        self.assertFalse((self.home/".cache/rex-agents").exists())
        self.assertFalse(install.installed())

    def test_hook_inert_when_not_installed(self):
        os.environ.update(REX_SERVER="unix:s", REX_SESSION="session:a", REX_BLOCK="block:0001")
        with mock.patch("sys.stdin") as stdin:
            self.assertEqual(cli.main(["_hook", "claude-code", "SessionStart"]), 0)
            stdin.read.assert_not_called()
        self.assertFalse((self.home/".cache/rex-agents").exists())


class ProcessBoundaryTests(Base):
    def test_real_cli(self):
        env = {"HOME": str(self.home), "PATH": os.defpath, "REX_SERVER": "unix:s",
               "REX_SESSION": "session:a", "REX_BLOCK": "block:0001"}
        hook = subprocess.run([sys.executable, str(CLI), "_hook", "claude-code", "SessionStart"],
                              input='{"session_id": "s1"}', capture_output=True, text=True, env=env)
        self.assertEqual((hook.returncode, hook.stderr), (0, ""))
        self.assertFalse((self.home/".cache").exists())
        helped = subprocess.run([sys.executable, str(CLI), "--help"], capture_output=True, text=True, env=env)
        self.assertEqual(helped.returncode, 0)
        self.assertIn("launch", helped.stdout)
        self.assertNotIn("focus", helped.stdout)


if __name__ == "__main__":
    unittest.main()
