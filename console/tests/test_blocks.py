import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import blocks  # noqa: E402


class FakeSerial:
    def __init__(self, lines):
        self.lines = iter(lines)

    def readline(self):
        return next(self.lines, b"")


class BlockProtocolTests(unittest.TestCase):
    def test_meta_parser_supports_kind_and_numeric_values(self):
        kind, meta = blocks._parse_meta_line("# BLOCK BODE R=220 C=10.0 LABEL=test")
        self.assertEqual(kind, "BODE")
        self.assertEqual(meta, {"R": 220, "C": 10.0, "LABEL": "test"})

    def test_reader_ignores_noise_and_inconsistent_rows(self):
        serial = FakeSerial(
            [
                b"booting\n",
                b"# BLOCK STEP R=220\n",
                b"t_us,adc\n",
                b"0,10\n",
                b"100,20,unexpected\n",
                b"200,30\n",
                b"# END\n",
            ]
        )
        block, diagnostics = blocks.read_one_block(serial, timeout_s=0.05)
        self.assertIsNotNone(block)
        self.assertEqual(block.kind, "STEP")
        self.assertEqual(block.columns, ["t_us", "adc"])
        self.assertEqual(block.rows, [[0.0, 10.0], [200.0, 30.0]])
        self.assertTrue(diagnostics.saw_block_start)
        self.assertEqual(diagnostics.rows_captured, 2)

    def test_reader_returns_none_for_incomplete_block(self):
        serial = FakeSerial([b"# BLOCK SINE\n", b"0,1\n"])
        block, diagnostics = blocks.read_one_block(serial, timeout_s=0.001)
        self.assertIsNone(block)
        self.assertTrue(diagnostics.saw_block_start)
        self.assertEqual(diagnostics.last_line, "0,1")

    def test_reader_diagnostics_report_silence_before_any_block(self):
        serial = FakeSerial([b"booting\n", b"noise\n"])
        block, diagnostics = blocks.read_one_block(serial, timeout_s=0.001)
        self.assertIsNone(block)
        self.assertFalse(diagnostics.saw_block_start)
        self.assertEqual(diagnostics.last_line, "noise")
        self.assertGreater(diagnostics.bytes_received, 0)

    def test_port_discovery_excludes_motherboard_uart(self):
        ports = [
            SimpleNamespace(
                device="/dev/ttyS0", vid=None, description="n/a",
                manufacturer=None, product=None,
            ),
            SimpleNamespace(
                device="/dev/ttyUSB0", vid=0x10C4, description="CP210x USB UART",
                manufacturer="Silicon Labs", product="CP2102",
            ),
        ]
        with (
            mock.patch.object(blocks.list_ports, "comports", return_value=ports),
            mock.patch.object(blocks.glob, "glob", return_value=[]),
        ):
            self.assertEqual(blocks.find_ports(), ["/dev/ttyUSB0"])


if __name__ == "__main__":
    unittest.main()
