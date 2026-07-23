"""
Subprocess adapter for OpenRocket. Runs console/runners/or_fly.py inside
~/openrocket/.venv (the one with jpype installed). Each call is a fresh
process: the JVM starts, flies one design, and the process exits. This
sidesteps the "JVM can only start once per process" constraint entirely --
there's no long-lived interpreter for Streamlit to accidentally re-enter.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

OPENROCKET_VENV_PYTHON = Path.home() / "openrocket" / ".venv" / "bin" / "python"
OPENROCKET_DIR = Path.home() / "openrocket"
RUNNER = Path(__file__).resolve().parent.parent.parent / "runners" / "or_fly.py"


class OpenRocketError(RuntimeError):
    pass


def fly(eng_path: str, architecture: str = "mindia", fin: dict | None = None,
        wind: float = 2.0, timeout_s: float = 60.0) -> dict:
    """Build and fly one rocket design, return the parsed JSON result."""
    if not OPENROCKET_VENV_PYTHON.exists():
        raise OpenRocketError(f"OpenRocket venv not found at {OPENROCKET_VENV_PYTHON}")

    resolved_eng_path = Path(eng_path).expanduser().resolve()
    if not resolved_eng_path.is_file():
        raise OpenRocketError(f"Motor curve not found at {resolved_eng_path}")

    params = {"eng_path": str(resolved_eng_path), "architecture": architecture, "wind": wind}
    if fin:
        params["fin"] = fin

    try:
        proc = subprocess.run(
            [str(OPENROCKET_VENV_PYTHON), str(RUNNER), json.dumps(params)],
            cwd=str(OPENROCKET_DIR),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise OpenRocketError(
            f"OpenRocket did not finish within {timeout_s:.0f}s. "
            "Check the JVM and reduce model complexity before retrying."
        ) from exc

    if proc.returncode != 0:
        raise OpenRocketError(f"or_fly.py exited {proc.returncode}: {proc.stderr[-2000:]}")

    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as e:
        raise OpenRocketError(f"Could not parse output: {e}\nstdout: {proc.stdout[:500]}\n"
                               f"stderr: {proc.stderr[-1000:]}") from e

    if not result.get("ok"):
        raise OpenRocketError(result.get("error", "unknown error"))

    return result
