import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import store  # noqa: E402


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_path = store.DB_PATH
        store.DB_PATH = Path(self.tmp.name) / "runs.db"

    def tearDown(self):
        store.DB_PATH = self.original_path
        self.tmp.cleanup()

    def test_run_round_trip_and_delete(self):
        run_id = store.save_run("SINE", {"F_SAMPLE": 1000}, ["i", "adc"], [[0, 42]], "baseline")
        self.assertEqual(store.count_runs(), 1)
        record = store.get_run(run_id)
        self.assertEqual(record.kind, "SINE")
        self.assertEqual(record.rows, [[0, 42]])
        self.assertEqual(record.note, "baseline")

        summary = store.list_runs()[0]
        self.assertEqual(summary.id, run_id)
        self.assertEqual(summary.rows, [])

        store.delete_run(run_id)
        self.assertEqual(store.count_runs(), 0)
        self.assertIsNone(store.get_run(run_id))


if __name__ == "__main__":
    unittest.main()
