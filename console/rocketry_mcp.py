"""Shared local MCP server for Codex and Claude Code."""
from __future__ import annotations

import sys
from functools import partial
from pathlib import Path
from typing import Any, Callable

import anyio
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

CORE = Path(__file__).resolve().parent / "core"
sys.path.insert(0, str(CORE))

import services  # noqa: E402
from mcp_tools import RocketryTools  # noqa: E402


mcp = FastMCP(
    "rocketry",
    instructions=(
        "Local Rocketry engineering tools. Measurements and simulations are "
        "evidence, not authorization to manufacture, ignite, or launch. "
        "No ignition or hazardous actuation tool is available."
    ),
)
tools = RocketryTools()

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
LOCAL_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)


async def execute(
    ctx: Context,
    operation: Callable[[], dict[str, Any]],
    *,
    message: str,
) -> dict[str, Any]:
    await ctx.report_progress(0, 1, message)
    try:
        result = await anyio.to_thread.run_sync(operation)
    except services.ServiceError as exc:
        await ctx.warning(f"{exc.code}: {exc.message}")
        return {"ok": False, "error": {"code": exc.code, "message": exc.message}}
    except Exception as exc:  # MCP must not leak a server traceback to either provider.
        await ctx.error(f"internal_error: {type(exc).__name__}: {exc}")
        return {
            "ok": False,
            "error": {
                "code": "internal_error",
                "message": "The local Rocketry tool failed unexpectedly.",
            },
        }
    await ctx.report_progress(1, 1, "Complete")
    return {"ok": True, **result}


@mcp.tool(annotations=READ_ONLY)
async def system_status(ctx: Context) -> dict[str, Any]:
    """Check ESP32 ports, saved runs, openMotor and OpenRocket readiness."""
    return await execute(ctx, tools.system_status, message="Checking local engineering services")


@mcp.tool(annotations=READ_ONLY)
async def list_ports(ctx: Context) -> dict[str, Any]:
    """List likely ESP32 USB serial ports on this Linux workstation."""
    return await execute(ctx, tools.list_ports, message="Discovering serial ports")


@mcp.tool(annotations=LOCAL_WRITE)
async def capture_bench(
    port: str,
    ctx: Context,
    baud: int = 115200,
    timeout_s: float = 15.0,
    note: str = "",
) -> dict[str, Any]:
    """Capture one complete ESP32 block and save it to History.

    The serial device is locked across Codex and Claude sessions. The result
    includes a run_id plus a bounded preview; call get_run for more rows.
    """
    return await execute(
        ctx,
        partial(
            tools.capture_bench,
            port=port,
            baud=baud,
            timeout_s=timeout_s,
            note=note,
        ),
        message=f"Capturing one block from {port}",
    )


@mcp.tool(annotations=READ_ONLY)
async def get_wiring_guide(
    circuit: str,
    ctx: Context,
    language: str = "en",
) -> dict[str, Any]:
    """Return a bilingual guide, pin sequence and SVG for a supported circuit.

    Call system_status to discover the exact supported circuit keys.
    """
    return await execute(
        ctx,
        partial(tools.get_wiring_guide, circuit, language),
        message=f"Loading {circuit} wiring",
    )


@mcp.tool(annotations=LOCAL_WRITE)
async def run_motor_sweep(
    core_min_mm: int,
    core_max_mm: int,
    segment_counts: list[int],
    segment_length_min_mm: int,
    segment_length_max_mm: int,
    ctx: Context,
    segment_length_step_mm: int = 5,
    maximum_stack_mm: int = 320,
    target_peak_kn: float = 280.0,
    note: str = "",
    timeout_s: float = 240.0,
) -> dict[str, Any]:
    """Run a bounded openMotor BATES sweep and save the result to History."""
    return await execute(
        ctx,
        partial(
            tools.run_motor_sweep,
            core_min_mm=core_min_mm,
            core_max_mm=core_max_mm,
            segment_counts=segment_counts,
            segment_length_min_mm=segment_length_min_mm,
            segment_length_max_mm=segment_length_max_mm,
            segment_length_step_mm=segment_length_step_mm,
            maximum_stack_mm=maximum_stack_mm,
            target_peak_kn=target_peak_kn,
            note=note,
            timeout_s=timeout_s,
        ),
        message="Running the openMotor geometry sweep",
    )


@mcp.tool(annotations=LOCAL_WRITE)
async def run_flight(
    motor_curve_path: str,
    ctx: Context,
    architecture: str = "mindia",
    fin: dict | None = None,
    wind_m_s: float = 2.0,
    note: str = "",
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    """Run one OpenRocket flight and save its metrics to History."""
    return await execute(
        ctx,
        partial(
            tools.run_flight,
            motor_curve_path=motor_curve_path,
            architecture=architecture,
            fin=fin,
            wind_m_s=wind_m_s,
            note=note,
            timeout_s=timeout_s,
        ),
        message="Running the OpenRocket flight simulation",
    )


@mcp.tool(annotations=READ_ONLY)
async def get_run(
    run_id: int,
    ctx: Context,
    offset: int = 0,
    limit: int = 500,
) -> dict[str, Any]:
    """Read one saved run with bounded row pagination."""
    return await execute(
        ctx,
        partial(tools.get_run, run_id, offset=offset, limit=limit),
        message=f"Loading run {run_id}",
    )


@mcp.tool(annotations=LOCAL_WRITE)
async def compare_runs(
    run_ids: list[int],
    ctx: Context,
    x_column: str | None = None,
    y_column: str | None = None,
    max_points: int = 500,
) -> dict[str, Any]:
    """Overlay two to six compatible runs and persist a JSON plot artifact."""
    return await execute(
        ctx,
        partial(
            tools.compare_runs,
            run_ids,
            x_column=x_column,
            y_column=y_column,
            max_points=max_points,
        ),
        message="Comparing saved runs",
    )


@mcp.tool(annotations=LOCAL_WRITE)
async def export_csv(run_id: int, ctx: Context) -> dict[str, Any]:
    """Export one saved run to a persistent local CSV artifact."""
    return await execute(
        ctx,
        partial(tools.export_csv, run_id),
        message=f"Exporting run {run_id} as CSV",
    )


@mcp.tool(annotations=LOCAL_WRITE)
async def run_tests(ctx: Context) -> dict[str, Any]:
    """Run the fixed Rocketry Console CI suite and persist the complete log."""
    return await execute(ctx, tools.run_tests, message="Running Console verification")


if __name__ == "__main__":
    mcp.run(transport="stdio")
