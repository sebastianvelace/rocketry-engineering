import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import provider_probe


ROOT = Path(__file__).resolve().parents[1]


def completed(command, stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


class ProviderProbeTests(unittest.TestCase):
    @mock.patch.object(provider_probe.shutil, "which", return_value="/usr/bin/claude")
    def test_claude_probe_redacts_account_identity(self, _which):
        help_text = " ".join(
            (
                "--input-format",
                "--output-format",
                "--include-partial-messages",
                "--include-hook-events",
                "--resume",
                "--session-id",
                "--fork-session",
                "--remote-control",
                "--background",
                "--worktree",
                "--permission-mode",
            )
        )

        def runner(command, **_kwargs):
            if command[-1] == "--version":
                return completed(command, "2.1.218 (Claude Code)")
            if command[1:3] == ["auth", "status"]:
                return completed(
                    command,
                    json.dumps(
                        {
                            "loggedIn": True,
                            "authMethod": "claude.ai",
                            "apiProvider": "firstParty",
                            "subscriptionType": "pro",
                            "email": "private@example.com",
                            "orgId": "secret-org",
                        }
                    ),
                )
            return completed(command, help_text)

        report = provider_probe.probe_claude(ROOT, runner=runner)
        serialized = json.dumps(report.to_dict())

        self.assertTrue(report.ready)
        self.assertNotIn("private@example.com", serialized)
        self.assertNotIn("secret-org", serialized)
        self.assertIn("subscriptionType", serialized)

    @mock.patch.object(provider_probe.shutil, "which", return_value="/usr/bin/codex")
    @mock.patch.object(
        provider_probe,
        "probe_codex_app_server",
        return_value=provider_probe.Check(
            "app_server_handshake",
            "pass",
            "JSON-RPC initialized",
            {"type": "chatgpt"},
        ),
    )
    def test_codex_probe_requires_chatgpt_auth(self, _protocol, _which):
        def runner(command, **_kwargs):
            if command[-1] == "--version":
                return completed(command, "codex-cli 0.145.0")
            if command[1:3] == ["login", "status"]:
                return completed(command, "Logged in using ChatGPT")
            return completed(
                command,
                "Run the app server stdio:// unix:// ws:// generate-json-schema",
            )

        report = provider_probe.probe_codex(ROOT, runner=runner)

        self.assertTrue(report.ready)
        auth = next(check for check in report.checks if check.name == "authentication")
        self.assertEqual(auth.data["authMethod"], "chatgpt")

    def test_report_fails_when_executable_is_missing(self):
        with mock.patch.object(provider_probe.shutil, "which", return_value=None):
            report = provider_probe.probe_claude(ROOT)

        self.assertFalse(report.ready)
        self.assertEqual(report.checks[0].status, "fail")

    def test_warning_does_not_make_provider_unready(self):
        report = provider_probe.ProviderReport(
            "claude",
            "/usr/bin/claude",
            [provider_probe.Check("compatibility", "warn", "Needs live proof")],
        )
        self.assertTrue(report.ready)


if __name__ == "__main__":
    unittest.main()
