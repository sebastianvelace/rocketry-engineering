import tempfile
import unittest
from pathlib import Path

from gateway.store import GatewayStore
from gateway.usage import UsageService, parse_claude_usage


class ClaudeUsageParsingTests(unittest.TestCase):
    def test_parses_real_subscription_windows_and_activity(self):
        parsed = parse_claude_usage(
            "You are currently using your subscription to power Claude Code\n\n"
            "Current session: 3% used · resets Jul 23, 11:30pm (America/Bogota)\n"
            "Current week (all models): 54% used · resets Jul 25, 5:59pm (America/Bogota)\n\n"
            "Last 24h · 282 requests · 9 sessions\n"
            "Last 7d · 1105 requests · 19 sessions"
        )

        self.assertTrue(parsed["subscription"])
        self.assertEqual(parsed["windows"][0]["used_percent"], 3)
        self.assertEqual(parsed["windows"][1]["used_percent"], 54)
        self.assertEqual(parsed["activity"]["day"]["requests"], 282)
        self.assertEqual(parsed["activity"]["week"]["sessions"], 19)


class LocalUsageTests(unittest.TestCase):
    def test_aggregates_claude_turns_and_latest_codex_thread_total(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = GatewayStore(Path(temporary) / "gateway.db")
            claude = store.create_session(provider="claude", workspace=temporary)
            codex = store.create_session(provider="codex", workspace=temporary)
            store.append_event(
                claude.id,
                type="usage",
                text="Turn usage",
                data={
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 4,
                        "cache_read_input_tokens": 20,
                    },
                    "cost_usd": 0.05,
                },
            )
            for total in (100, 140):
                store.append_event(
                    codex.id,
                    type="usage",
                    text="thread/tokenUsage/updated",
                    data={
                        "tokenUsage": {
                            "total": {
                                "inputTokens": total - 10,
                                "outputTokens": 10,
                                "cachedInputTokens": 3,
                                "reasoningOutputTokens": 2,
                                "totalTokens": total,
                            }
                        }
                    },
                )

            service = UsageService(store, object(), workspace=Path(temporary))
            local = service._local_usage()

        self.assertEqual(local["claude"]["turns"], 1)
        self.assertEqual(local["claude"]["cached_input_tokens"], 20)
        self.assertEqual(local["codex"]["total_tokens"], 140)
        self.assertEqual(local["codex"]["threads"], 1)


if __name__ == "__main__":
    unittest.main()
