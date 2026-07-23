import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import blocks  # noqa: E402
import plots  # noqa: E402


class PlotDispatchTests(unittest.TestCase):
    def test_fft_kind_uses_frequency_domain_plot(self):
        block = blocks.Block(
            kind="FFT",
            meta={"F_SIGNAL": 50, "F_SAMPLE": 1000},
            columns=["i", "adc"],
            rows=[[index, 2048 + ((index % 10) - 5) * 30] for index in range(100)],
        )
        figure, stats = plots.plot_block(block)
        self.assertIn("ADC sees (Hz)", stats)
        self.assertEqual(figure.layout.xaxis.title.text, "frequency (Hz)")

    def test_empty_block_has_actionable_error(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            plots.plot_block(blocks.Block(kind="SINE"))

    def test_mixed_width_block_is_rejected(self):
        block = blocks.Block(kind="SINE", rows=[[0, 1], [1]])
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            plots.plot_block(block)


if __name__ == "__main__":
    unittest.main()
