import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import blocks  # noqa: E402
import services  # noqa: E402
import store  # noqa: E402


class ServiceContractTests(unittest.TestCase):
    def test_bench_capture_reports_progress_and_preserves_block(self):
        block = blocks.Block(
            kind="SINE",
            meta={"F_SAMPLE": 1000},
            columns=["i", "adc"],
            rows=[[0.0, 42.0]],
        )
        events = []
        service = services.BenchService(
            ports_fn=lambda: ["/dev/ttyUSB0"],
            capture_fn=lambda port, baud, timeout_s: (block, blocks.BlockReadDiagnostics()),
            detect_fn=lambda captured: captured.kind,
        )

        capture = service.capture(
            services.BenchCaptureRequest("/dev/ttyUSB0"),
            services.OperationContext(progress=events.append),
        )

        self.assertIs(capture.block, block)
        self.assertEqual(capture.detected_kind, "SINE")
        self.assertEqual([event.stage for event in events], ["connecting", "complete"])

    def test_bench_timeout_has_stable_error_code(self):
        service = services.BenchService(
            capture_fn=lambda port, baud, timeout_s: (None, blocks.BlockReadDiagnostics()),
            detect_fn=lambda captured: captured.kind,
        )
        with self.assertRaises(services.ServiceError) as raised:
            service.capture(services.BenchCaptureRequest("/dev/ttyUSB0"))
        self.assertEqual(raised.exception.code, "capture_timeout")

    def test_bench_timeout_reports_what_was_actually_seen_on_the_wire(self):
        diagnostics = blocks.BlockReadDiagnostics(
            bytes_received=48,
            lines_received=3,
            last_line="# BLOCK STEP",
            saw_block_start=True,
            rows_captured=0,
            elapsed_s=15.02,
        )
        service = services.BenchService(
            capture_fn=lambda port, baud, timeout_s: (None, diagnostics),
            detect_fn=lambda captured: captured.kind,
        )
        with self.assertRaises(services.ServiceError) as raised:
            service.capture(services.BenchCaptureRequest("/dev/ttyUSB0"))
        reported = raised.exception.details["diagnostics"]
        self.assertEqual(reported["bytes_received"], 48)
        self.assertEqual(reported["last_line"], "# BLOCK STEP")
        self.assertTrue(reported["saw_block_start"])

    def test_cancelled_operation_never_reaches_provider(self):
        called = False

        def run_motor(params, timeout_s):
            nonlocal called
            called = True
            return {}

        token = services.CancellationToken()
        token.cancel()
        context = services.OperationContext(cancellation=token)
        service = services.MotorService(run_fn=run_motor)
        params = {
            "core_range_mm": [12, 12],
            "seg_counts": [4],
            "seg_len_range_mm": [45, 45, 5],
        }

        with self.assertRaises(services.OperationCancelled):
            service.run(params, context)
        self.assertFalse(called)

    def test_motor_result_uses_existing_history_shape(self):
        saved = {}

        def save(kind, meta, columns, rows, note=""):
            saved.update(kind=kind, meta=meta, columns=columns, rows=rows, note=note)
            return 17

        result = {
            "n_viable": 1,
            "rows": [{"designation": "E20", "impulse_ns": 40.5}],
        }
        service = services.MotorService(run_fn=lambda params, timeout_s: result, save_fn=save)

        self.assertEqual(service.save(result, note=" baseline "), 17)
        self.assertEqual(saved["kind"], "MOTOR_SWEEP")
        self.assertEqual(saved["meta"], {"n_viable": 1})
        self.assertEqual(saved["columns"], ["designation", "impulse_ns"])
        self.assertEqual(saved["rows"], [["E20", 40.5]])
        self.assertEqual(saved["note"], "baseline")

    def test_flight_result_uses_existing_history_shape(self):
        saved = {}

        def save(kind, meta, columns, rows, note=""):
            saved.update(kind=kind, meta=meta, columns=columns, rows=rows, note=note)
            return 23

        result = {"apogee": 500.0, "architecture": "mindia", "warn": ""}
        service = services.FlightService(save_fn=save)

        self.assertEqual(service.save(result), 23)
        self.assertEqual(saved["kind"], "FLIGHT")
        self.assertEqual(saved["meta"], {"apogee": 500.0, "architecture": "mindia"})
        self.assertEqual(saved["columns"], ["metric", "value"])
        self.assertEqual(saved["rows"], [["apogee", 500.0]])

    def test_wiring_contract_rejects_missing_and_empty_diagrams(self):
        good = services.WiringService(
            guides={"loop": {"short": "Loop"}},
            circuits={"loop": lambda: ("<svg/>", [("a", "b")])},
        )
        self.assertEqual(good.get("loop").pins, [("a", "b")])

        with self.assertRaises(services.ServiceError) as missing:
            good.get("other")
        self.assertEqual(missing.exception.code, "wiring_not_found")

        empty = services.WiringService(
            guides={"loop": {"short": "Loop"}},
            circuits={"loop": lambda: ("", [])},
        )
        with self.assertRaises(services.ServiceError) as invalid:
            empty.get("loop")
        self.assertEqual(invalid.exception.code, "invalid_wiring_diagram")

    def test_history_numeric_columns_and_csv_are_ui_independent(self):
        run = store.RunRecord(
            id=1,
            created_at="2026-07-23T00:00:00+00:00",
            kind="SINE",
            meta={},
            columns=["sample", "value", "label"],
            rows=[[0, 1.5, "a"], [1, 2.5, "b"]],
            note="",
        )

        self.assertEqual(
            services.HistoryService.numeric_columns(run),
            [("sample", 0), ("value", 1)],
        )
        self.assertEqual(
            services.HistoryService.to_csv(run),
            "sample,value,label\n0,1.5,a\n1,2.5,b\n",
        )


if __name__ == "__main__":
    unittest.main()
