import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import provider_live_probe


class ProviderLiveProbeTests(unittest.TestCase):
    def test_json_lines_ignores_terminal_noise(self):
        events = provider_live_probe.json_lines(
            'warning\n{"type":"system","session_id":"abc"}\n{"type":"result","result":"ok"}'
        )
        self.assertEqual([event["type"] for event in events], ["system", "result"])

    def test_codex_summary_prefers_completed_message(self):
        events = [
            {
                "method": "item/agentMessage/delta",
                "params": {"delta": "partial"},
            },
            {
                "method": "item/completed",
                "params": {
                    "item": {"type": "agentMessage", "text": "complete"},
                },
            },
        ]
        summary = provider_live_probe.summarize_codex(
            events,
            {"id": "turn-1", "status": "completed"},
        )
        self.assertEqual(summary["result"], "complete")
        self.assertEqual(summary["turnId"], "turn-1")


if __name__ == "__main__":
    unittest.main()
