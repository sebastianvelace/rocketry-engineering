"""Provider-neutral implementations behind the Rocketry MCP tools."""
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

import artifacts
import services
from operation_locks import OperationLocks


class RocketryTools:
    def __init__(
        self,
        *,
        bench: services.BenchService | None = None,
        wiring: services.WiringService | None = None,
        motor: services.MotorService | None = None,
        flight: services.FlightService | None = None,
        history: services.HistoryService | None = None,
        artifact_store: artifacts.ArtifactStore | None = None,
        locks: OperationLocks | None = None,
        console_root: Path | None = None,
    ):
        self.bench = bench or services.BenchService()
        self.wiring = wiring or services.WiringService()
        self.motor = motor or services.MotorService()
        self.flight = flight or services.FlightService()
        self.history = history or services.HistoryService()
        self.artifacts = artifact_store or artifacts.ArtifactStore()
        self.locks = locks or OperationLocks()
        self.console_root = console_root or Path(__file__).resolve().parent.parent

    def system_status(self) -> dict[str, Any]:
        return {
            "ports": self.bench.list_ports(),
            "saved_runs": self.history.count(),
            "openmotor_ready": (Path.home() / "openMotor" / ".venv" / "bin" / "python").is_file(),
            "openrocket_ready": (Path.home() / "openrocket" / ".venv" / "bin" / "python").is_file(),
            "wiring_circuits": self.wiring.list_keys(),
        }

    def list_ports(self) -> dict[str, Any]:
        ports = self.bench.list_ports()
        return {"ports": ports, "count": len(ports)}

    def capture_bench(
        self,
        *,
        port: str,
        baud: int = 115200,
        timeout_s: float = 15.0,
        note: str = "",
    ) -> dict[str, Any]:
        with self.locks.acquire("serial"):
            capture = self.bench.capture(
                services.BenchCaptureRequest(port=port, baud=baud, timeout_s=timeout_s)
            )
            run_id = self.bench.save(capture, note=note)
        block = capture.block
        return {
            "run_id": run_id,
            "kind": capture.detected_kind,
            "meta": block.meta,
            "columns": block.columns,
            "row_count": len(block.rows),
            "rows_preview": block.rows[:20],
        }

    def get_wiring_guide(self, circuit: str, language: str = "en") -> dict[str, Any]:
        item = self.wiring.get(circuit)
        spanish = language.casefold() in {"es", "spanish", "español"}

        def localized(field: str):
            return item.guide.get(f"{field}_es", item.guide[field]) if spanish else item.guide[field]

        pins = [
            {
                "from": pin.get("from_es", pin["from"]) if spanish else pin["from"],
                "to": pin.get("to_es", pin["to"]) if spanish else pin["to"],
                "how": pin.get("how_es", pin["how"]) if spanish else pin["how"],
            }
            for pin in item.pins
        ]
        svg = item.svg.decode("utf-8") if isinstance(item.svg, bytes) else item.svg
        return {
            "artifact_id": f"wiring:{item.key}:{'es' if spanish else 'en'}",
            "circuit": item.key,
            "short": localized("short"),
            "purpose": localized("purpose"),
            "use_for": localized("use_for"),
            "parts": localized("parts"),
            "before": localized("before"),
            "verify": localized("verify"),
            "pins": pins,
            "svg": svg,
        }

    def run_motor_sweep(
        self,
        *,
        core_min_mm: int,
        core_max_mm: int,
        segment_counts: list[int],
        segment_length_min_mm: int,
        segment_length_max_mm: int,
        segment_length_step_mm: int = 5,
        maximum_stack_mm: int = 320,
        target_peak_kn: float = 280.0,
        note: str = "",
        timeout_s: float = 240.0,
    ) -> dict[str, Any]:
        params = {
            "core_range_mm": [core_min_mm, core_max_mm],
            "seg_counts": segment_counts,
            "seg_len_range_mm": [
                segment_length_min_mm,
                segment_length_max_mm,
                segment_length_step_mm,
            ],
            "max_total_mm": maximum_stack_mm,
            "target_peak_kn": target_peak_kn,
        }
        with self.locks.acquire("openmotor"):
            result = self.motor.run(params, timeout_s=timeout_s)
            run_id = self.motor.save(result, note=note)
        return {
            "run_id": run_id,
            **{key: value for key, value in result.items() if key != "rows"},
            "rows_preview": result.get("rows", [])[:10],
        }

    def run_flight(
        self,
        *,
        motor_curve_path: str,
        architecture: str = "mindia",
        fin: dict | None = None,
        wind_m_s: float = 2.0,
        note: str = "",
        timeout_s: float = 60.0,
    ) -> dict[str, Any]:
        with self.locks.acquire("openrocket"):
            result = self.flight.run(
                motor_curve_path,
                architecture=architecture,
                fin=fin,
                wind=wind_m_s,
                timeout_s=timeout_s,
            )
            run_id = self.flight.save(result, note=note)
        return {"run_id": run_id, **result}

    def get_run(self, run_id: int, *, offset: int = 0, limit: int = 500) -> dict[str, Any]:
        if offset < 0 or limit < 1 or limit > 2000:
            raise services.ServiceError(
                "invalid_request",
                "offset must be non-negative and limit must be between 1 and 2000.",
            )
        run = self.history.get(run_id)
        return {
            "id": run.id,
            "created_at": run.created_at,
            "kind": run.kind,
            "meta": run.meta,
            "columns": run.columns,
            "rows": run.rows[offset:offset + limit],
            "row_count": len(run.rows),
            "offset": offset,
            "note": run.note,
        }

    def compare_runs(
        self,
        run_ids: list[int],
        *,
        x_column: str | None = None,
        y_column: str | None = None,
        max_points: int = 500,
    ) -> dict[str, Any]:
        if len(run_ids) < 2 or len(run_ids) > 6:
            raise services.ServiceError("invalid_request", "Select between two and six runs.")
        if max_points < 10 or max_points > 2000:
            raise services.ServiceError("invalid_request", "max_points must be between 10 and 2000.")
        runs = [self.history.get(run_id) for run_id in run_ids]
        kinds = {run.kind for run in runs}
        if len(kinds) != 1:
            raise services.ServiceError("incompatible_runs", "All compared runs must have the same type.")

        numeric_by_run = [dict(self.history.numeric_columns(run)) for run in runs]
        common = set(numeric_by_run[0])
        for columns in numeric_by_run[1:]:
            common &= set(columns)
        if not common:
            raise services.ServiceError(
                "incompatible_runs",
                "The selected runs do not share a numeric column.",
            )
        ordered = [name for name, _ in self.history.numeric_columns(runs[0]) if name in common]
        chosen_y = y_column or ordered[min(1, len(ordered) - 1)]
        if chosen_y not in common:
            raise services.ServiceError("invalid_request", f"Unknown shared y column: {chosen_y}")
        if x_column is not None and x_column not in common:
            raise services.ServiceError("invalid_request", f"Unknown shared x column: {x_column}")

        series = []
        for run, columns in zip(runs, numeric_by_run):
            y_index = columns[chosen_y]
            x_index = columns[x_column] if x_column is not None else None
            points = [
                {
                    "x": row[x_index] if x_index is not None else sample,
                    "y": row[y_index],
                }
                for sample, row in enumerate(run.rows)
                if len(row) > y_index and (x_index is None or len(row) > x_index)
            ]
            stride = max(1, (len(points) + max_points - 1) // max_points)
            series.append({"run_id": run.id, "note": run.note, "points": points[::stride]})

        comparison = {
            "kind": runs[0].kind,
            "x_column": x_column or "sample_index",
            "y_column": chosen_y,
            "series": series,
        }
        artifact = self.artifacts.save(
            kind="run_comparison",
            content=json.dumps(comparison, ensure_ascii=False),
            suffix=".json",
            media_type="application/json",
            metadata={"run_ids": run_ids},
        )
        return {"artifact_id": artifact.id, "artifact_path": artifact.path, **comparison}

    def export_csv(self, run_id: int) -> dict[str, Any]:
        run = self.history.get(run_id)
        artifact = self.artifacts.save(
            kind="run_csv",
            content=self.history.to_csv(run),
            suffix=".csv",
            media_type="text/csv",
            metadata={"run_id": run_id, "run_kind": run.kind},
        )
        return asdict(artifact)

    def run_tests(self) -> dict[str, Any]:
        with self.locks.acquire("console_tests"):
            try:
                process = subprocess.run(
                    ["bash", "tools/ci_check.sh"],
                    cwd=self.console_root,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                output = process.stdout + process.stderr
                return_code = process.returncode
            except subprocess.TimeoutExpired as exc:
                output = (exc.stdout or "") + (exc.stderr or "")
                return_code = 124
        artifact = self.artifacts.save(
            kind="test_log",
            content=output,
            suffix=".log",
            media_type="text/plain",
            metadata={"return_code": return_code, "suite": "console"},
        )
        return {
            "artifact_id": artifact.id,
            "artifact_path": artifact.path,
            "passed": return_code == 0,
            "return_code": return_code,
            "output_tail": "\n".join(output.splitlines()[-80:]),
        }
