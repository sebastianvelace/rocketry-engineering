"""UI-independent application services for the Rocketry Console.

Streamlit, the future desktop client, and agent tools must all call these
services instead of talking directly to serial ports, simulators, diagrams,
or SQLite.  The service boundary keeps stored data compatible while exposing
stable progress, cancellation, and error contracts.
"""
from __future__ import annotations

import csv
import dataclasses
import io
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import blocks
import diagrams
import store
import wiring_guides
from adapters import openmotor, openrocket


class ServiceError(RuntimeError):
    """A user-facing failure with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        cause: Exception | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.__cause__ = cause


class OperationCancelled(ServiceError):
    def __init__(self):
        super().__init__("operation_cancelled", "The operation was cancelled.")


@dataclass(frozen=True)
class ProgressEvent:
    stage: str
    message: str
    completed: int | None = None
    total: int | None = None


class CancellationToken:
    """Thread-safe cooperative cancellation shared by every service."""

    def __init__(self):
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise OperationCancelled()


ProgressCallback = Callable[[ProgressEvent], None]


@dataclass
class OperationContext:
    progress: ProgressCallback | None = None
    cancellation: CancellationToken = field(default_factory=CancellationToken)

    def emit(
        self,
        stage: str,
        message: str,
        *,
        completed: int | None = None,
        total: int | None = None,
    ) -> None:
        self.cancellation.raise_if_cancelled()
        if self.progress is not None:
            self.progress(ProgressEvent(stage, message, completed, total))

    def checkpoint(self) -> None:
        self.cancellation.raise_if_cancelled()


@dataclass(frozen=True)
class BenchCaptureRequest:
    port: str
    baud: int = blocks.DEFAULT_BAUD
    timeout_s: float = 15.0


@dataclass(frozen=True)
class BenchCapture:
    block: blocks.Block
    detected_kind: str


@dataclass(frozen=True)
class WiringCircuit:
    key: str
    guide: dict[str, Any]
    svg: str
    pins: list


def _context(context: OperationContext | None) -> OperationContext:
    return context if context is not None else OperationContext()


class BenchService:
    def __init__(
        self,
        *,
        ports_fn: Callable[[], list[str]] | None = None,
        capture_fn: Callable[..., tuple[blocks.Block | None, blocks.BlockReadDiagnostics]] | None = None,
        detect_fn: Callable[[blocks.Block], str] | None = None,
        save_fn: Callable[..., int] | None = None,
    ):
        if detect_fn is None:
            import plots

            detect_fn = plots.detect_kind
        self._ports = ports_fn or blocks.find_ports
        self._capture = capture_fn or blocks.open_and_read
        self._detect = detect_fn
        self._save = save_fn or store.save_run

    def list_ports(self) -> list[str]:
        try:
            return self._ports()
        except (OSError, ValueError) as exc:
            raise ServiceError("serial_discovery_failed", f"Could not list serial ports: {exc}", cause=exc)

    def capture(
        self,
        request: BenchCaptureRequest,
        context: OperationContext | None = None,
    ) -> BenchCapture:
        ctx = _context(context)
        if not request.port.strip():
            raise ServiceError("invalid_request", "A serial port is required.")
        if request.baud <= 0 or request.timeout_s <= 0:
            raise ServiceError("invalid_request", "Baud rate and timeout must be positive.")
        ctx.emit("connecting", f"Opening {request.port}.")
        try:
            block, diagnostics = self._capture(
                request.port,
                baud=request.baud,
                timeout_s=request.timeout_s,
            )
        except (OSError, ValueError) as exc:
            raise ServiceError(
                "serial_capture_failed",
                f"Could not read {request.port}: {exc}",
                cause=exc,
            )
        ctx.checkpoint()
        if block is None:
            raise ServiceError(
                "capture_timeout",
                "No complete block was received before the timeout.",
                details={"diagnostics": dataclasses.asdict(diagnostics)},
            )
        kind = self._detect(block)
        ctx.emit("complete", f"Captured {len(block.rows)} rows as {kind}.", completed=1, total=1)
        return BenchCapture(block=block, detected_kind=kind)

    def save(self, capture: BenchCapture, note: str = "") -> int:
        block = capture.block
        return self._save(
            capture.detected_kind,
            block.meta,
            block.columns,
            block.rows,
            note=note.strip(),
        )


class WiringService:
    def __init__(
        self,
        *,
        guides: dict[str, dict[str, Any]] | None = None,
        circuits: dict[str, Callable[[], tuple[str, list]]] | None = None,
    ):
        self._guides = guides if guides is not None else wiring_guides.GUIDES
        self._circuits = circuits if circuits is not None else diagrams.CIRCUITS

    def list_keys(self) -> list[str]:
        return list(self._guides)

    def get(self, key: str) -> WiringCircuit:
        if key not in self._guides or key not in self._circuits:
            raise ServiceError("wiring_not_found", f"Unknown wiring circuit: {key}")
        svg, pins = self._circuits[key]()
        if not svg.strip():
            raise ServiceError("invalid_wiring_diagram", f"Circuit {key} produced an empty diagram.")
        return WiringCircuit(key=key, guide=self._guides[key], svg=svg, pins=pins)


class MotorService:
    def __init__(
        self,
        *,
        run_fn: Callable[..., dict] | None = None,
        save_fn: Callable[..., int] | None = None,
    ):
        self._run = run_fn or openmotor.run_sweep
        self._save = save_fn or store.save_run

    @staticmethod
    def estimate_combinations(params: dict) -> int:
        try:
            core_lo, core_hi = params["core_range_mm"]
            len_lo, len_hi, len_step = params["seg_len_range_mm"]
            segments = params["seg_counts"]
            if core_hi < core_lo or len_hi < len_lo or int(len_step) <= 0 or not segments:
                raise ValueError
            return (int(core_hi) - int(core_lo) + 1) * len(segments) * (
                (int(len_hi) - int(len_lo)) // int(len_step) + 1
            )
        except (KeyError, TypeError, ValueError):
            raise ServiceError("invalid_request", "The motor search envelope is invalid.")

    def run(
        self,
        params: dict,
        context: OperationContext | None = None,
        *,
        timeout_s: float = 240.0,
    ) -> dict:
        ctx = _context(context)
        total = self.estimate_combinations(params)
        ctx.emit("running", f"Evaluating {total} motor geometries.", completed=0, total=total)
        try:
            result = self._run(params, timeout_s=timeout_s)
        except openmotor.OpenMotorError as exc:
            raise ServiceError("motor_simulation_failed", str(exc), cause=exc)
        ctx.checkpoint()
        ctx.emit("complete", "Motor sweep complete.", completed=total, total=total)
        return result

    def save(self, result: dict, note: str = "") -> int:
        rows = result.get("rows", [])
        columns = list(rows[0]) if rows else []
        return self._save(
            "MOTOR_SWEEP",
            {key: value for key, value in result.items() if key != "rows"},
            columns,
            [[row.get(column) for column in columns] for row in rows],
            note=note.strip(),
        )


class FlightService:
    def __init__(
        self,
        *,
        run_fn: Callable[..., dict] | None = None,
        save_fn: Callable[..., int] | None = None,
    ):
        self._run = run_fn or openrocket.fly
        self._save = save_fn or store.save_run

    def run(
        self,
        eng_path: str,
        *,
        architecture: str = "mindia",
        fin: dict | None = None,
        wind: float = 2.0,
        timeout_s: float = 60.0,
        context: OperationContext | None = None,
    ) -> dict:
        ctx = _context(context)
        if architecture not in {"mindia", "separate"}:
            raise ServiceError("invalid_request", f"Unknown airframe architecture: {architecture}")
        if wind < 0:
            raise ServiceError("invalid_request", "Wind speed cannot be negative.")
        ctx.emit("running", f"Simulating flight with {Path(eng_path).name}.", completed=0, total=1)
        try:
            result = self._run(
                eng_path,
                architecture=architecture,
                fin=fin,
                wind=wind,
                timeout_s=timeout_s,
            )
        except openrocket.OpenRocketError as exc:
            raise ServiceError("flight_simulation_failed", str(exc), cause=exc)
        ctx.checkpoint()
        ctx.emit("complete", "Flight simulation complete.", completed=1, total=1)
        return result

    def save(self, result: dict, note: str = "") -> int:
        return self._save(
            "FLIGHT",
            {key: value for key, value in result.items() if key != "warn"},
            ["metric", "value"],
            [[key, value] for key, value in result.items() if isinstance(value, (int, float))],
            note=note.strip(),
        )


class HistoryService:
    def __init__(
        self,
        *,
        list_fn: Callable[..., list[store.RunRecord]] | None = None,
        get_fn: Callable[[int], store.RunRecord | None] | None = None,
        delete_fn: Callable[[int], None] | None = None,
        count_fn: Callable[[], int] | None = None,
        latest_fn: Callable[[], store.RunRecord | None] | None = None,
    ):
        self._list = list_fn or store.list_runs
        self._get = get_fn or store.get_run
        self._delete = delete_fn or store.delete_run
        self._count = count_fn or store.count_runs
        self._latest = latest_fn or store.latest_run

    def list(self, kind: str | None = None) -> list[store.RunRecord]:
        return self._list(kind)

    def get(self, run_id: int) -> store.RunRecord:
        record = self._get(run_id)
        if record is None:
            raise ServiceError("run_not_found", f"Run #{run_id} does not exist.")
        return record

    def delete(self, run_id: int) -> None:
        self.get(run_id)
        self._delete(run_id)

    def count(self) -> int:
        return self._count()

    def latest(self) -> store.RunRecord | None:
        return self._latest()

    @staticmethod
    def numeric_columns(run: store.RunRecord) -> list[tuple[str, int]]:
        if not run.rows:
            return []
        width = max(len(row) for row in run.rows)
        names = run.columns or [f"column_{idx + 1}" for idx in range(width)]
        numeric = []
        for idx in range(width):
            values = [row[idx] for row in run.rows if len(row) > idx and row[idx] is not None]
            if values and all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                for value in values
            ):
                name = names[idx] if idx < len(names) else f"column_{idx + 1}"
                numeric.append((name, idx))
        return numeric

    @staticmethod
    def to_csv(run: store.RunRecord) -> str:
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        if run.columns:
            writer.writerow(run.columns)
        writer.writerows(run.rows)
        return output.getvalue()
