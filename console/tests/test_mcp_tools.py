import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

import artifacts  # noqa: E402
import blocks  # noqa: E402
import operation_locks  # noqa: E402
import services  # noqa: E402
import store  # noqa: E402
from mcp_tools import RocketryTools  # noqa: E402


class ArtifactAndLockTests(unittest.TestCase):
    def test_artifact_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_store = artifacts.ArtifactStore(Path(tmp))
            saved = artifact_store.save(
                kind="test",
                content="evidence",
                suffix=".txt",
                media_type="text/plain",
                metadata={"run_id": 4},
            )
            loaded = artifact_store.get(saved.id)
            listed = artifact_store.list()

            self.assertEqual(loaded, saved)
            self.assertEqual(listed, [saved])
            self.assertEqual(Path(saved.path).read_text(encoding="utf-8"), "evidence")
            self.assertIsNone(artifact_store.get("../escape"))

    def test_second_process_style_lock_fails_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = operation_locks.OperationLocks(Path(tmp))
            second = operation_locks.OperationLocks(Path(tmp))
            with first.acquire("serial"):
                with self.assertRaises(services.ServiceError) as raised:
                    with second.acquire("serial"):
                        pass
            self.assertEqual(raised.exception.code, "operation_busy")


class RocketryToolTests(unittest.TestCase):
    def test_wiring_is_localized_and_json_serializable(self):
        guide = RocketryTools().get_wiring_guide(
            "Direct jumper (Phase 1/2/4)",
            language="es",
        )
        encoded = json.dumps(guide)
        self.assertIn("<svg", encoded)
        self.assertEqual(guide["pins"][0]["how"], "un cable jumper")

    def test_capture_is_saved_and_returns_bounded_preview(self):
        captured = blocks.Block(
            kind="SINE",
            meta={"F_SAMPLE": 1000},
            columns=["i", "adc"],
            rows=[[index, index * 2] for index in range(30)],
        )
        saved = []
        bench = services.BenchService(
            capture_fn=lambda port, baud, timeout_s: captured,
            detect_fn=lambda block: block.kind,
            save_fn=lambda kind, meta, columns, rows, note="": saved.append(note) or 9,
        )
        with tempfile.TemporaryDirectory() as tmp:
            tools = RocketryTools(
                bench=bench,
                locks=operation_locks.OperationLocks(Path(tmp) / "locks"),
                artifact_store=artifacts.ArtifactStore(Path(tmp) / "artifacts"),
            )
            result = tools.capture_bench(port="/dev/ttyUSB0", note="agent capture")

        self.assertEqual(result["run_id"], 9)
        self.assertEqual(result["row_count"], 30)
        self.assertEqual(len(result["rows_preview"]), 20)
        self.assertEqual(saved, ["agent capture"])

    def test_compare_runs_persists_decimated_artifact(self):
        runs = {
            run_id: store.RunRecord(
                id=run_id,
                created_at="2026-07-23T00:00:00+00:00",
                kind="SINE",
                meta={},
                columns=["x", "y"],
                rows=[[index, index * run_id] for index in range(100)],
                note=f"run {run_id}",
            )
            for run_id in (1, 2)
        }
        history = services.HistoryService(
            get_fn=lambda run_id: runs.get(run_id),
            list_fn=lambda kind=None: list(runs.values()),
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifact_store = artifacts.ArtifactStore(Path(tmp) / "artifacts")
            tools = RocketryTools(history=history, artifact_store=artifact_store)
            result = tools.compare_runs([1, 2], x_column="x", y_column="y", max_points=25)
            loaded = artifact_store.get(result["artifact_id"])

            self.assertIsNotNone(loaded)
            payload = json.loads(Path(loaded.path).read_text(encoding="utf-8"))

        self.assertEqual(payload["x_column"], "x")
        self.assertEqual(len(payload["series"]), 2)
        self.assertLessEqual(len(payload["series"][0]["points"]), 25)


class MCPTransportTests(unittest.TestCase):
    def test_stdio_server_initializes_and_exposes_expected_tools(self):
        async def exercise():
            params = StdioServerParameters(
                command=str(ROOT / ".venv" / "bin" / "python"),
                args=[str(ROOT / "rocketry_mcp.py")],
                cwd=str(ROOT),
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    status = await session.call_tool("system_status", {})
                    return {tool.name for tool in listed.tools}, status

        names, status = asyncio.run(exercise())

        self.assertEqual(
            names,
            {
                "system_status",
                "list_ports",
                "capture_bench",
                "get_wiring_guide",
                "run_motor_sweep",
                "run_flight",
                "get_run",
                "compare_runs",
                "export_csv",
                "run_tests",
            },
        )
        self.assertFalse(status.isError)
        self.assertTrue(status.structuredContent["ok"])


if __name__ == "__main__":
    unittest.main()
