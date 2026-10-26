"""Lifecycle behavior against a stateful Rex boundary; no native processes run."""
import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rex_agents.core import CommandError, Error, Integration, atomic, read


def location(block="driver", session="one", server="local"):
    return dict(server=server, session="session:" + session, block="block:" + block)


class LifecycleFake(Integration):
    def __init__(self, cache):
        super().__init__(cache=cache, **location())
        self.panes = {}
        self.sessions = {("local", "session:one")}
        self.calls = []
        self.reason_calls = []
        self.rows = []
        self.unavailable = set()
        self.list_reply = None
        self.process_reply = None
        self.split_error = None
        self.split_reply = None
        self.close_error = None
        self.keep_on_close = False
        self.unknown_after_close = False
        self.serial = 0
        self.add_pane(location())

    def add_pane(self, target, *, window="window:driver", exited=False):
        self.sessions.add((target["server"], target["session"]))
        self.panes[tuple(target[k] for k in ("server", "session", "block"))] = dict(
            window_id=window, child=None if exited else {"pid": 100},
            last_exit={"code": 0} if exited else None)

    def remove_pane(self, target):
        self.panes.pop(tuple(target[k] for k in ("server", "session", "block")), None)

    def reason(self, *args, **kwargs):
        self.reason_calls.append((args, kwargs))
        if args[0] == "who":
            return json.dumps(dict(sessions=self.rows, person="person", machine="machine"))
        raise AssertionError((args, kwargs))

    def hosts(self):
        return [{"label": "remote"}]

    def local_server(self):
        return "local"

    def rex(self, *args, server=None, timeout=12):
        server = server or self.server or "local"
        self.calls.append((args, server))
        if server in self.unavailable:
            raise Error("host unreachable")
        if args[:2] == ("do", "rex_agents_remote_launch"):
            return json.dumps(dict(block_ids=["block:remote"]))
        if args[0] == "whoami":
            return json.dumps(dict(endpoint=server))
        if args[0] == "ls":
            return json.dumps(dict(sessions=[dict(session_id=s) for host, s in self.sessions if host == server]))
        if args[:2] == ("session", "inspect"):
            return json.dumps(dict(active_window_id="window:driver", windows=[dict(
                window_id="window:driver", focused_block_id="block:driver")]))
        session = args[args.index("-s") + 1]
        if (server, session) not in self.sessions:
            raise CommandError(f'Error: session target "{session}" not found')
        if args[:2] == ("block", "ls"):
            if self.list_reply is not None:
                return self.list_reply
            return json.dumps(dict(blocks=[dict(block_id=block, window_id=pane["window_id"])
                for (host, sess, block), pane in self.panes.items() if (host, sess) == (server, session)]))
        if args[0] == "split":
            if self.split_error:
                raise self.split_error
            if self.split_reply is not None:
                return self.split_reply
            anchor = args[args.index("-b") + 1]
            pane = self.panes[(server, session, anchor)]
            self.serial += 1
            target = dict(server=server, session=session, block=f"block:worker-{self.serial}")
            self.add_pane(target, window=pane["window_id"])
            return json.dumps(dict(block_ids=[target["block"], anchor], window_id=pane["window_id"]))
        if args[:2] == ("block", "call"):
            if self.process_reply is not None:
                return self.process_reply
            block = args[args.index("-b") + 1]
            pane = self.panes.get((server, session, block))
            if pane is None:
                raise CommandError(f'block target "{block}" not found')
            return json.dumps({k: pane[k] for k in ("child", "last_exit")})
        if args[:2] == ("block", "close"):
            if not self.keep_on_close:
                self.panes.pop((server, session, args[-1]), None)
            if self.unknown_after_close:
                self.unavailable.add(server)
            if self.close_error:
                raise self.close_error
            return "{}"
        raise AssertionError((args, server))


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"CODEX_THREAD_ID": "driver"}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        binaries = patch("shutil.which", side_effect=lambda name: "/bin/" + name)
        binaries.start()
        self.addCleanup(binaries.stop)
        self.app = LifecycleFake(Path(self.tmp.name)/"cache")

    def launch(self, name="worker", **kwargs):
        return self.app.launch("codex", name, self.tmp.name, **kwargs)

    def records(self):
        return [read(p) for p in (self.app.cache/"launches").glob("*.json")]

    def record(self, token, target=None, **kwargs):
        value = dict(token=token, name=token, kind="codex", owner="codex:driver", split="right",
                     created=len(self.records()) + 1, location=target)
        value.update(kwargs)
        atomic(self.app.cache/"launches"/f"{token}.json", value)
        return value

    def locator(self, native="driver", target=None, launch=None, **kwargs):
        value = dict(kind="codex", native_id=native, location=target or location(), ended=False, launch=launch)
        value.update(kwargs)
        atomic(self.app.locator_path("codex", native), value)
        return value

    def splits(self):
        return [args for args, _ in self.app.calls if args[0] == "split"]

    def test_explicit_context_still_records_native_owner(self):
        result = self.launch()
        record = read(self.app.cache/"launches"/f"{result['launch']}.json")
        self.assertEqual(record["owner"], "codex:driver")
        self.assertEqual(record["split"], "right")
        self.assertEqual(self.splits()[0][self.splits()[0].index("-b") + 1], "block:driver")
        self.assertIn("--focus=false", self.splits()[0])

    def test_claude_driver_owns_and_cleans_workers_after_clear_identity_refresh(self):
        with patch.dict(os.environ, dict(CLAUDE_CODE_SESSION_ID="stale", REX_AGENTS_KIND="claude-code",
                                        REX_AGENTS_NATIVE_ID="current"), clear=True):
            self.launch()
            self.assertEqual(self.records()[0]["owner"], "claude-code:current")
            self.assertEqual(len(self.app.cleanup()["closed"]), 1)

    def test_new_native_identity_does_not_own_previous_drivers_workers(self):
        self.launch()
        os.environ["CODEX_THREAD_ID"] = "new-driver"
        self.assertEqual(self.app.cleanup(), dict(closed=[], gone=[], uncertain=[]))
        self.assertEqual(len(self.records()), 1)

    def test_human_launch_has_no_owner_and_does_not_share_a_layout(self):
        os.environ.clear()
        self.launch("first")
        self.launch("second")
        self.assertTrue(all(r["owner"] is None for r in self.records()))
        self.assertTrue(all("--split=right" in args for args in self.splits()))

    def test_human_launch_can_resolve_one_session_without_agent_identity(self):
        os.environ.clear()
        self.app.session = self.app.block = None
        self.launch()
        self.assertEqual(self.splits()[0][self.splits()[0].index("-b") + 1], "block:driver")

    def test_native_locator_supplies_missing_context(self):
        self.locator()
        self.app.server = self.app.session = self.app.block = None
        self.launch()
        self.assertEqual(self.splits()[0][self.splits()[0].index("-b") + 1], "block:driver")

    def test_unmapped_agent_does_not_fall_back_to_human_focus(self):
        self.app.session = self.app.block = None
        with self.assertRaisesRegex(Error, "No live Rex locator"):
            self.launch()
        self.assertEqual(self.app.calls, [])

    def test_human_launched_driver_and_resumed_identity_can_drive(self):
        self.record("human-launch", location(), owner=None)
        self.locator(launch="human-launch", ended=True)
        first = self.launch("first")
        self.assertEqual(read(self.app.cache/"launches"/f"{first['launch']}.json")["owner"], "codex:driver")
        self.app.block = "block:resumed"
        self.app.add_pane(location("resumed"))
        self.locator(target=location("resumed"), launch="human-launch")
        result = self.app.cleanup()
        self.assertEqual([r["launch"] for r in result["closed"]], [first["launch"]])
        self.assertIn(("local", "session:one", "block:driver"), self.app.panes)

    def test_nested_worker_rejected_with_explicit_context(self):
        self.record("parent", location(), owner="codex:other")
        self.locator(launch="parent")
        with self.assertRaisesRegex(Error, "nested"):
            self.launch()
        self.assertEqual(self.app.calls, [])
        self.assertEqual(self.app.reason_calls, [])

    def test_inherited_launch_token_is_not_a_nested_identity(self):
        self.record("unrelated", location("other"), owner="codex:other")
        os.environ["REX_AGENTS_LAUNCH"] = "unrelated"
        self.launch()
        self.assertEqual(len(self.splits()), 1)

    def test_locator_content_must_match_callers_exact_native_identity(self):
        self.record("parent", location(), owner="codex:other")
        self.locator(launch="parent", kind="claude-code")
        self.launch()
        self.assertEqual(len(self.splits()), 1)

    def test_partial_conflicting_and_malformed_identity_fail_before_rex(self):
        invalid = [dict(CLAUDECODE="1"), dict(REX_AGENTS_NATIVE_ID="id"),
                   dict(REX_AGENTS_KIND="claude-code"), dict(REX_AGENTS_KIND="unknown", REX_AGENTS_NATIVE_ID="id"),
                   dict(CODEX_THREAD_ID=""), dict(CODEX_SESSION_ID="orphan"),
                   dict(CODEX_THREAD_ID="id", CLAUDE_CODE_SESSION_ID="other"),
                   dict(CODEX_THREAD_ID="id", REX_AGENTS_KIND="claude-code", REX_AGENTS_NATIVE_ID="other"),
                   dict(CODEX_THREAD_ID="bad\nid"), dict(REASON_NETWORK_AGENT="codex"),
                   dict(CODEX_THREAD_ID="id", REASON_NETWORK_AGENT="codex"),
                   dict(CODEX_THREAD_ID="id", REASON_NETWORK_AGENT="codex", REASON_NETWORK_SESSION="other")]
        for values in invalid:
            with self.subTest(values=values), patch.dict(os.environ, values, clear=True):
                with self.assertRaises(Error):
                    self.launch()
                with self.assertRaises(Error):
                    self.app.cleanup()
        self.assertEqual(self.app.calls, [])
        self.assertEqual(self.app.reason_calls, [])

    def test_cleanup_requires_sender_before_any_rex_call(self):
        os.environ.clear()
        with self.assertRaisesRegex(Error, "No native agent identity"):
            self.app.cleanup()
        self.assertEqual(self.app.calls, [])

    def test_cleanup_without_owned_workers_needs_no_server(self):
        self.app.server = None
        with patch.object(self.app, "local_server", side_effect=AssertionError("unnecessary server call")):
            self.assertEqual(self.app.cleanup(), dict(closed=[], gone=[], uncertain=[]))

    def test_unknown_local_server_retains_owned_reservations(self):
        self.record("worker", location("worker"))
        self.app.server = None
        for reply in ("[]", "{}", "broken", '{"endpoint": "tcp://remote:1234"}',
                      '{"endpoint": "unix:"}'):
            with patch("rex_agents.core.run", return_value=reply), \
                    patch.object(self.app, "local_server", lambda: Integration.local_server(self.app)):
                self.assertEqual(len(self.app.cleanup()["uncertain"]), 1)
        with patch.object(self.app, "local_server", side_effect=Error("host unreachable")):
            self.assertEqual(len(self.app.cleanup()["uncertain"]), 1)
        self.assertEqual(len(self.records()), 1)

    def test_local_server_ignores_explicit_and_inherited_remote_server(self):
        self.app.server = "remote"
        endpoint = "unix:///Users/example/Library/Application%20Support/rex/server.sock"
        with patch.dict(os.environ, {"REX_SERVER": "another-remote"}), \
                patch("rex_agents.core.run", return_value=json.dumps(dict(endpoint=endpoint))) as execute:
            self.assertEqual(Integration.local_server(self.app), endpoint)
        argv = execute.call_args.args[0]
        self.assertEqual(argv[-2:], ["whoami", "--json"])
        self.assertNotIn("-S", argv)
        self.assertNotIn("--server", argv)
        self.assertNotIn("REX_SERVER", execute.call_args.kwargs["env"])

    def test_direct_remote_selectors_fail_before_creating_a_reservation(self):
        self.app.server = "remote"
        for key in ("model", "effort"):
            with self.subTest(key=key), self.assertRaisesRegex(Error, "Remote model and effort"):
                self.launch(**{key: "high"})
        self.assertEqual(self.records(), [])
        self.assertEqual(self.app.calls, [])

    def test_unverified_server_alias_cannot_select_model_or_close_panes(self):
        self.app.server = "local-alias"
        self.record("alias-worker", location("worker", server="local-alias"))
        self.app.add_pane(location("worker", server="local-alias"))
        with self.assertRaisesRegex(Error, "Remote model and effort"):
            self.launch(model="gpt-6.1-sol")
        self.assertEqual(self.app.cleanup(), dict(closed=[], gone=[], uncertain=[]))
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(self.app.calls, [])

    def test_unknown_local_endpoint_blocks_selectors_without_a_reservation(self):
        with patch.object(self.app, "local_server", side_effect=Error("Local Rex server unknown")):
            with self.assertRaisesRegex(Error, "Local Rex server unknown"):
                self.launch(model="gpt-6.1-sol")
        self.assertEqual(self.records(), [])
        self.assertEqual(self.app.calls, [])

    def test_cleanup_ignores_remote_override_and_leaves_remote_records(self):
        self.app.server = "remote"
        self.app.add_pane(location(server="remote"))
        worker = self.launch()
        target = dict(location(server="remote"), block=worker["block_ids"][0])
        self.assertEqual(self.app.cleanup(), dict(closed=[], gone=[], uncertain=[]))
        self.assertIn(tuple(target[k] for k in ("server", "session", "block")), self.app.panes)
        self.assertEqual(len(self.records()), 1)
        self.assertFalse(any(args[:2] == ("block", "close") for args, _ in self.app.calls))

    def test_cleanup_protects_local_driver_even_with_remote_override_and_no_locator(self):
        self.app.server = "remote"
        self.record("driver", location())
        result = self.app.cleanup()
        self.assertEqual([r["name"] for r in result["uncertain"]], ["driver"])
        self.assertEqual(len(self.records()), 1)

    def test_local_unix_endpoint_supports_selectors_and_cleanup(self):
        endpoint = "unix:///Users/example/Library/Application%20Support/rex/server.sock"
        self.app.server = endpoint
        self.app.add_pane(location(server=endpoint))
        with patch("rex_agents.core.run", return_value=json.dumps(dict(endpoint=endpoint))), \
                patch.object(self.app, "local_server", lambda: Integration.local_server(self.app)):
            self.launch(model="gpt-6.1-sol", effort="high")
            self.assertEqual(len(self.app.cleanup()["closed"]), 1)

    def test_alternation_uses_chronology_after_partial_manual_close(self):
        a = self.launch("a")["block_ids"][0]
        b = self.launch("b")["block_ids"][0]
        self.app.remove_pane(dict(location(), block=b))
        c = self.launch("c")["block_ids"][0]
        splits = self.splits()
        self.assertEqual([next(x for x in args if x.startswith("--split=")) for args in splits],
                         ["--split=right", "--split=below", "--split=right"])
        self.assertEqual([args[args.index("-b") + 1] for args in splits], ["block:driver", a, a])
        self.app.remove_pane(dict(location(), block=a))
        self.app.remove_pane(dict(location(), block=c))
        self.launch("d")
        self.assertIn("--split=below", self.splits()[-1])
        self.assertEqual(self.splits()[-1][self.splits()[-1].index("-b") + 1], "block:driver")

    def test_anchor_ignores_other_owner_server_session_tab_and_exited_panes(self):
        a = self.launch("a")["block_ids"][0]
        targets = [location("other-tab"), location("other-session", session="two"),
                   location("other-server", server="foreign"), location("exited"), location("other-owner")]
        for number, target in enumerate(targets):
            self.app.add_pane(target, window="window:other" if number == 0 else "window:driver", exited=number == 3)
            self.record("record-" + str(number), target,
                        owner="codex:someone" if number == 4 else "codex:driver", created=100 + number)
        self.launch("next")
        self.assertEqual(self.splits()[-1][self.splits()[-1].index("-b") + 1], a)

    def test_cleanup_resets_layout_after_last_owned_reservation(self):
        self.launch("a")
        self.launch("b")
        self.app.cleanup()
        self.launch("new")
        self.assertIn("--split=right", self.splits()[-1])
        self.assertEqual(self.splits()[-1][self.splits()[-1].index("-b") + 1], "block:driver")

    def test_pane_state_live_exited_gone_and_exact_id_lookup(self):
        self.assertEqual(self.app.pane_state(location()), "live")
        self.app.add_pane(location("exited"), exited=True)
        self.assertEqual(self.app.pane_state(location("exited")), "exited")
        self.assertEqual(self.app.pane_state(location("drive")), "gone")
        self.assertEqual(self.app.pane_state(location("gone", session="absent")), "gone")

    def test_pane_state_unknown_for_unavailable_or_malformed_api(self):
        self.app.unavailable.add("local")
        self.assertEqual(self.app.pane_state(location()), "unknown")
        self.app.unavailable.clear()
        for reply in ("not json", "null", "[]", "{}", '{"blocks": {}}', '{"blocks": [{}]}',
                      '{"blocks": [{"block_id": "not-an-id"}]}',
                      '{"blocks": [{"block_id": "block:driver"}, {"block_id": "block:driver"}]}'):
            self.app.list_reply = reply
            with self.subTest(list_reply=reply):
                self.assertEqual(self.app.pane_state(location()), "unknown")
        self.app.list_reply = None
        for reply in ("broken", "null", "[]", "{}", '{"child": false, "last_exit": null}',
                      '{"child": null, "last_exit": []}', '{"child": {}, "last_exit": {}}',
                      '{"child": {"pid": true}, "last_exit": null}'):
            self.app.process_reply = reply
            with self.subTest(process_reply=reply):
                self.assertEqual(self.app.pane_state(location()), "unknown")
        self.assertEqual(self.app.pane_state({}), "unknown")

    def test_duplicate_names_block_live_exited_and_unknown_panes(self):
        self.app.add_pane(location("worker"))
        self.record("worker", location("worker"))
        for state in ("live", "exited", "unknown"):
            with self.subTest(state=state):
                self.app.add_pane(location("worker"), exited=state == "exited")
                self.app.list_reply = "{}" if state == "unknown" else None
                with self.assertRaisesRegex(Error, "already launched"):
                    self.launch()
        self.assertEqual(self.splits(), [])

    def test_only_true_absence_releases_duplicate_name(self):
        self.record("worker", location("worker"))
        self.launch()
        self.assertEqual(len(self.splits()), 1)

    def test_failed_native_exec_with_retained_pane_keeps_name_reserved(self):
        self.app.add_pane(location("worker"), exited=True)
        self.record("worker", location("worker"), failed="native executable failed")
        with self.assertRaisesRegex(Error, "already launched"):
            self.launch()
        self.assertEqual(self.splits(), [])

    def test_active_reason_name_blocks_creation(self):
        self.app.rows = [dict(name="worker", status="idle", address="person/worker", person="person",
                             machine="machine", agent="codex", is_me=False)]
        with self.assertRaisesRegex(Error, "already exists"):
            self.launch()
        self.assertEqual(self.splits(), [])

    def test_uncertain_launch_reservation_blocks_retry_and_cleanup(self):
        self.app.split_error = Error("timeout")
        with self.assertRaisesRegex(Error, "uncertain"):
            self.launch(task="only once")
        with self.assertRaisesRegex(Error, "uncertain"):
            self.launch(task="only once")
        result = self.app.cleanup()
        self.assertEqual(len(result["uncertain"]), 1)
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(len(self.splits()), 1)

    def test_malformed_split_reply_is_uncertain_not_a_released_reservation(self):
        self.app.split_reply = '{"block_ids": []}'
        with self.assertRaisesRegex(Error, "uncertain"):
            self.launch()
        with self.assertRaisesRegex(Error, "uncertain"):
            self.launch()
        self.assertEqual(len(self.splits()), 1)

    def test_definite_precreation_failure_allows_retry(self):
        self.app.split_error = CommandError("invalid layout")
        with self.assertRaisesRegex(Error, "invalid layout"):
            self.launch()
        self.app.split_error = None
        self.launch()
        self.assertEqual(len(self.splits()), 2)

    def test_cleanup_closes_live_and_retained_ended_workers_without_reason(self):
        a = self.launch("a")
        b = self.launch("b")
        second = dict(location(), block=b["block_ids"][0])
        self.app.add_pane(second, exited=True)
        self.locator("worker-a", dict(location(), block=a["block_ids"][0]), a["launch"])
        self.locator("worker-b", second, b["launch"], ended=True)
        with patch.object(self.app, "reason", side_effect=AssertionError("cleanup contacted Reason")):
            result = self.app.cleanup()
            again = self.app.cleanup()
        self.assertEqual(len(result["closed"]), 2)
        self.assertEqual(result["gone"], [])
        self.assertEqual(result["uncertain"], [])
        self.assertTrue(all(row["ended"] for row in self.app.locators()))
        self.assertEqual(self.records(), [])
        self.assertEqual(again, dict(closed=[], gone=[], uncertain=[]))
        self.assertIn(("local", "session:one", "block:driver"), self.app.panes)

    def test_cleanup_removes_confirmed_gone_and_ends_locator_without_close(self):
        self.record("missing", location("missing"))
        self.locator("missing-native", location("missing"), "missing")
        result = self.app.cleanup()
        self.assertEqual([r["name"] for r in result["gone"]], ["missing"])
        self.assertTrue(self.app.locators()[0]["ended"])
        self.assertFalse(any(args[:2] == ("block", "close") for args, _ in self.app.calls))

    def test_cleanup_preserves_other_owner_human_foreign_and_driver(self):
        for token, owner, target in (("other", "codex:other", location("other")),
                ("human", None, location("human")), ("foreign", "codex:driver", location("foreign", server="remote")),
                ("driver", "codex:driver", location())):
            self.app.add_pane(target)
            self.record(token, target, owner=owner)
        result = self.app.cleanup()
        self.assertEqual(len(self.records()), 4)
        self.assertEqual([r["name"] for r in result["uncertain"]], ["driver"])
        self.assertFalse(any(args[:2] == ("block", "close") for args, _ in self.app.calls))

    def test_cleanup_uses_driver_locator_to_protect_driver_and_scope_server(self):
        self.locator()
        self.app.server = "foreign"
        self.app.block = "block:explicit"
        self.record("driver", location())
        self.record("foreign", location("worker", server="foreign"))
        result = self.app.cleanup()
        self.assertEqual([r["name"] for r in result["uncertain"]], ["driver"])
        self.assertFalse(any(args[:2] == ("block", "close") for args, _ in self.app.calls))

    def test_cleanup_preserves_repurposed_worker_pane(self):
        worker = self.launch()
        target = dict(location(), block=worker["block_ids"][0])
        self.locator("worker-native", target, worker["launch"], ended=True)
        self.locator("unrelated-native", target)
        result = self.app.cleanup()
        self.assertEqual(len(result["uncertain"]), 1)
        self.assertEqual(result["closed"], [])
        self.assertEqual(len(self.records()), 1)
        self.assertIn(tuple(target[k] for k in ("server", "session", "block")), self.app.panes)
        self.assertFalse(any(args[:2] == ("block", "close") for args, _ in self.app.calls))

    def test_cleanup_preserves_resumed_worker_locator_and_old_pane(self):
        worker = self.launch()
        old = dict(location(), block=worker["block_ids"][0])
        resumed = location("resumed")
        self.app.add_pane(resumed)
        self.locator("worker-native", resumed, worker["launch"])
        for old_gone in (False, True):
            if old_gone:
                self.app.remove_pane(old)
            with self.subTest(old_gone=old_gone):
                result = self.app.cleanup()
                self.assertEqual(len(result["uncertain"]), 1)
                self.assertEqual(result["gone"], [])
                self.assertFalse(read(self.app.locator_path("codex", "worker-native"))["ended"])
                self.assertEqual(len(self.records()), 1)
        self.assertFalse(any(args[:2] == ("block", "close") for args, _ in self.app.calls))

    def test_cleanup_allows_clear_with_same_launch_token(self):
        worker = self.launch()
        target = dict(location(), block=worker["block_ids"][0])
        self.locator("before-clear", target, worker["launch"], ended=True)
        self.locator("after-clear", target, worker["launch"])
        self.assertEqual(len(self.app.cleanup()["closed"]), 1)
        self.assertTrue(all(row["ended"] for row in self.app.locators()))

    def test_cleanup_keeps_unknown_missing_and_invalid_locations_reserved(self):
        self.record("missing")
        self.record("invalid", {"server": "local", "session": "session:one"})
        self.record("unknown", location("unknown"))
        self.app.unavailable.add("local")
        result = self.app.cleanup()
        self.assertEqual(len(result["uncertain"]), 3)
        self.assertEqual(len(self.records()), 3)
        self.assertFalse(any(args[:2] == ("block", "close") for args, _ in self.app.calls))

    def test_cleanup_retries_failed_close_without_releasing_reservation(self):
        self.launch()
        self.app.keep_on_close = True
        self.app.close_error = CommandError("close rejected")
        result = self.app.cleanup()
        self.assertEqual(len(result["uncertain"]), 1)
        self.assertEqual(len(self.records()), 1)
        self.app.keep_on_close = False
        self.app.close_error = None
        self.assertEqual(len(self.app.cleanup()["closed"]), 1)

    def test_close_success_without_absence_is_uncertain(self):
        self.launch()
        self.app.keep_on_close = True
        result = self.app.cleanup()
        self.assertEqual(len(result["uncertain"]), 1)
        self.assertEqual(len(self.records()), 1)

    def test_unavailable_post_close_preserves_reservation_and_locator(self):
        worker = self.launch()
        self.locator("worker-native", dict(location(), block=worker["block_ids"][0]), worker["launch"])
        self.app.unknown_after_close = True
        self.assertEqual(len(self.app.cleanup()["uncertain"]), 1)
        self.assertFalse(self.app.locators()[0]["ended"])
        self.assertEqual(len(self.records()), 1)
        self.app.unavailable.clear()
        self.assertEqual(len(self.app.cleanup()["gone"]), 1)

    def test_close_error_after_actual_removal_is_confirmed(self):
        self.launch()
        self.app.close_error = Error("response lost")
        self.assertEqual(len(self.app.cleanup()["closed"]), 1)
        self.assertEqual(self.records(), [])

    def test_no_cleanup_on_stop_or_session_end(self):
        self.locator()
        self.record("worker", location("worker"))
        self.app.add_pane(location("worker"))
        with patch.object(self.app, "cleanup", side_effect=AssertionError("hook cleanup")):
            self.app.hook("codex", "Stop", dict(session_id="driver"))
            self.app.hook("codex", "SessionEnd", dict(session_id="driver"))
        self.assertEqual(len(self.records()), 1)
        self.assertFalse(any(args[:2] == ("block", "close") for args, _ in self.app.calls))

    def test_models_allow_provider_identifiers_and_aliases(self):
        for number, model in enumerate(("gpt-6.1-sol", "opus", "opus[1m]", "openai/gpt-6.1-sol",
                "us.anthropic.claude-opus-4-5-20251101-v1:0", "provider/model@version+alias")):
            self.launch("worker-" + str(number), model=model, effort="high")
        self.assertEqual(len(self.splits()), 6)

    def test_invalid_selectors_and_remote_overrides_fail_before_rex(self):
        for value in ("--model", "-x", "", "space model", "line\nmodel", "$(id)", "a;id", "a[]", "a[1m", 10):
            for key in ("model", "effort"):
                with self.subTest(value=value, key=key), self.assertRaisesRegex(Error, "Invalid"):
                    self.launch(**{key: value})
        for key in ("model", "effort"):
            with self.assertRaisesRegex(Error, "Remote model and effort"):
                self.launch(host="remote", **{key: "high"})
        self.assertEqual(self.app.calls, [])

    def test_remote_launch_without_selectors_remains_supported(self):
        result = self.launch(host="remote", task="literal task")
        self.assertEqual(result["block_ids"], ["block:remote"])
        self.assertEqual(self.records(), [])

    def test_both_native_argv_arrays_keep_one_literal_task_and_permissions(self):
        task = "first\n'quotes' \"double\" $(literal); `literal` $HOME"
        for kind, expected in (("claude", ["claude", "--name", "worker", "--model", "opus", "--effort", "high", "--", task]),
                ("codex", ["codex", "--no-daemon", "-m", "opus", "-c", 'model_reasoning_effort="high"', "--", task])):
            with self.subTest(kind=kind):
                self.app.launch(kind, "worker-" + kind, self.tmp.name, task=task, model="opus", effort="high")
                payload = self.splits()[-1][-1]
                decoded = json.loads(base64.urlsafe_b64decode(payload))
                decoded["name"] = "worker"
                payload = base64.urlsafe_b64encode(json.dumps(decoded).encode()).decode()
                with patch("os.execvpe") as execute:
                    self.app.worker(payload)
                self.assertEqual(execute.call_args.args[1], expected)
                self.assertEqual(execute.call_args.args[1].count(task), 1)
                self.assertNotIn("CODEX_THREAD_ID", execute.call_args.args[2])
                self.assertEqual(execute.call_args.args[2]["REX_AGENTS_LAUNCH"], decoded["token"])

    def test_native_defaults_remain_unchanged(self):
        for kind, expected in (("claude", ["claude", "--name", "worker-claude"]),
                               ("codex", ["codex", "--no-daemon"])):
            self.app.launch(kind, "worker-" + kind, self.tmp.name)
            with patch("os.execvpe") as execute:
                self.app.worker(self.splits()[-1][-1])
            self.assertEqual(execute.call_args.args[1], expected)


if __name__ == "__main__":
    unittest.main()
