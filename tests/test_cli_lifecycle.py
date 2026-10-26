import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rex_agents import cli
from rex_agents.core import Error


class CliLifecycleTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        integration = patch("rex_agents.cli.Integration")
        self.integration = integration.start()
        self.addCleanup(integration.stop)
        self.app = self.integration.return_value
        for boundary in ("rex_agents.core.run", "rex_agents.cli.run"):
            runner = patch(boundary, side_effect=AssertionError("Unexpected subprocess call"))
            runner.start()
            self.addCleanup(runner.stop)

    def invoke(self, argv, stdin=""):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors), patch("sys.stdin", io.StringIO(stdin)):
            status = cli.main(argv)
        return status, output.getvalue(), errors.getvalue()

    def test_launch_forwards_native_selectors_and_literal_task(self):
        task = "Review 'quotes', $HOME, `commands`, and spaces.\nSecond line.\n"
        self.app.launch.return_value = {"registration": "pending", "block_ids": ["block:worker"]}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "task with spaces.txt"
            path.write_text(task)
            status, output, errors = self.invoke([
                "--server", "local", "--session", "session:driver", "--block", "block:driver",
                "launch", "codex", "--name", "reviewer", "--cwd", "/project with spaces",
                "--model", "gpt-6.1-sol", "--effort", "high", "--task-file", str(path),
            ])
        self.assertEqual((status, errors), (0, ""))
        self.assertEqual(json.loads(output), self.app.launch.return_value)
        self.integration.assert_called_once_with(server="local", session="session:driver", block="block:driver", client=None)
        self.app.launch.assert_called_once_with("codex", "reviewer", "/project with spaces", task, None,
                                                model="gpt-6.1-sol", effort="high")

    def test_omitted_selectors_inherit_including_remote_launch(self):
        self.app.launch.return_value = {"registration": "pending"}
        for host in (None, "remote"):
            with self.subTest(host=host):
                self.app.launch.reset_mock()
                argv = ["launch", "claude", "--name", "reviewer", "--cwd", "/project"]
                if host:
                    argv += ["--host", host]
                status, output, errors = self.invoke(argv)
                self.assertEqual((status, errors), (0, ""))
                self.app.launch.assert_called_once_with("claude", "reviewer", "/project", None, host,
                                                        model=None, effort=None)

    def test_selectors_are_independently_optional(self):
        self.app.launch.return_value = {"registration": "pending"}
        for option, value in (("model", "claude-opus-5-5"), ("effort", "xhigh")):
            with self.subTest(option=option):
                self.app.launch.reset_mock()
                status, output, errors = self.invoke([
                    "launch", "claude", "--name", "reviewer", "--cwd", "/project", "--" + option, value,
                ])
                self.assertEqual((status, errors), (0, ""))
                selectors = dict(model=None, effort=None)
                selectors[option] = value
                self.app.launch.assert_called_once_with("claude", "reviewer", "/project", None, None, **selectors)

    def test_cleanup_emits_json_and_status_for_uncertainty(self):
        for uncertain in ([], [{"launch": "unknown", "reason": "Rex unavailable"}]):
            with self.subTest(uncertain=uncertain):
                self.app.cleanup.reset_mock()
                report = dict(closed=["block:worker"], gone=["block:old"], uncertain=uncertain)
                self.app.cleanup.return_value = report
                status, output, errors = self.invoke(["cleanup"])
                self.assertEqual(status, int(bool(uncertain)))
                self.assertEqual(errors, "")
                self.assertEqual(json.loads(output), report)
                self.app.cleanup.assert_called_once_with()
        self.app.launch.assert_not_called()

    def test_cleanup_with_no_owned_workers_succeeds(self):
        self.app.cleanup.return_value = dict(closed=[], gone=[], uncertain=[])
        status, output, errors = self.invoke(["cleanup"])
        self.assertEqual((status, errors), (0, ""))
        self.assertEqual(json.loads(output), self.app.cleanup.return_value)

    def test_identity_errors_are_reported_without_success_json(self):
        messages = (
            "No native agent identity. Use an agent shell or a human Rex action.",
            "Conflicting inherited agent identities; use a clean worker or resume the intended conversation",
        )
        for command in ("cleanup", "launch"):
            for message in messages:
                with self.subTest(command=command, message=message):
                    getattr(self.app, command).side_effect = Error(message)
                    argv = [command]
                    if command == "launch":
                        argv += ["codex", "--name", "reviewer", "--cwd", "/project"]
                    status, output, errors = self.invoke(argv)
                    self.assertEqual(status, 1)
                    self.assertEqual(output, "")
                    self.assertEqual(errors, f"rex-agents: {message}\n")

    def test_action_launch_forwards_supplied_selectors(self):
        self.app.launch.return_value = {"registration": "pending"}
        for selectors in ({}, {"model": "gpt-6.1-sol"}, {"effort": "high"},
                          {"model": "claude-opus-5-5", "effort": "xhigh"}):
            with self.subTest(selectors=selectors):
                self.app.launch.reset_mock()
                args = dict(kind="claude", name="reviewer", cwd="/project", task="Review", **selectors)
                status, output, errors = self.invoke(["_action"], json.dumps(dict(operation="launch", args=args)))
                self.assertEqual((status, errors), (0, ""))
                self.assertEqual(json.loads(output), self.app.launch.return_value)
                self.app.launch.assert_called_once_with("claude", "reviewer", "/project", "Review", None, **selectors)

    def test_action_remote_launch_keeps_existing_arguments(self):
        self.app.launch.return_value = {"registration": "pending"}
        args = dict(kind="codex", name="remote-reviewer", cwd="/remote", host="remote")
        status, output, errors = self.invoke(["_action"], json.dumps(dict(operation="launch", args=args)))
        self.assertEqual((status, errors), (0, ""))
        self.app.launch.assert_called_once_with("codex", "remote-reviewer", "/remote", None, "remote")

    def test_cleanup_is_not_a_palette_action(self):
        status, output, errors = self.invoke(["_action"], json.dumps(dict(operation="cleanup")))
        self.assertEqual((status, output, errors), (1, "", "rex-agents: Unknown action: cleanup\n"))
        self.app.cleanup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
