"""
Subprocess adapter for openMotor. Runs console/runners/om_sweep.py inside
~/openMotor/.venv with cwd=~/openMotor, because motorlib is an unpackaged
source tree that only imports that way (see plan doc for the full reasoning).
This process starts and exits per call -- no long-lived interpreter, no
state to manage between runs.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

OPENMOTOR_VENV_PYTHON = Path.home() / "openMotor" / ".venv" / "bin" / "python"
OPENMOTOR_DIR = Path.home() / "openMotor"
RUNNER = Path(__file__).resolve().parent.parent.parent / "runners" / "om_sweep.py"


class OpenMotorError(RuntimeError):
    pass


def run_sweep(params: dict, timeout_s: float = 120.0) -> dict:
    """Run a BATES grain sweep in openMotor and return the parsed JSON result."""
    if not OPENMOTOR_VENV_PYTHON.exists():
        raise OpenMotorError(f"openMotor venv not found at {OPENMOTOR_VENV_PYTHON}")

    proc = subprocess.run(
        [str(OPENMOTOR_VENV_PYTHON), str(RUNNER), json.dumps(params)],
        cwd=str(OPENMOTOR_DIR),
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )

    if proc.returncode != 0:
        raise OpenMotorError(f"om_sweep.py exited {proc.returncode}: {proc.stderr[-2000:]}")

    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as e:
        raise OpenMotorError(f"Could not parse output: {e}\nstdout: {proc.stdout[:500]}\n"
                              f"stderr: {proc.stderr[-1000:]}") from e

    if not result.get("ok"):
        raise OpenMotorError(result.get("error", "unknown error"))

    return result
