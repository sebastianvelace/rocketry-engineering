#!/usr/bin/env python3
"""
Runs INSIDE ~/openrocket/.venv (the one with jpype). Imports the existing
simulation/flight/architecture.py and reuses design_mindia()/design_separate()
+ fly() unmodified -- this script only wires parameters to those functions and
serializes the result. One JVM start per process, then the process exits, so
the console (which reruns its script on every interaction) never has to deal
with "JVM already started" across calls.

Usage:
    python or_fly.py '{"eng_path": ".../E.eng", "architecture": "mindia",
                        "fin": {"root":0.055,"tip":0.025,"height":0.030,
                                "sweep":0.030,"thickness":0.0016},
                        "wind": 2.0}'
"""
import json
import sys
from pathlib import Path

FLIGHT_DIR = str(Path.home() / "rocketry-portfolio" / "simulation" / "flight")
sys.path.insert(0, FLIGHT_DIR)

import architecture as A  # noqa: E402


def run(params: dict) -> dict:
    eng_path = params["eng_path"]
    fin = params.get("fin", {"root": 0.055, "tip": 0.025, "height": 0.030,
                              "sweep": 0.030, "thickness": 0.0016})
    wind = float(params.get("wind", 2.0))
    arch = params.get("architecture", "mindia")

    # The "mindia" architecture models the aluminium motor tube as airframe
    # structure. If the .eng file ALSO carries the tube's mass in its hardware
    # weight (the default export), the tube gets counted twice and apogee
    # comes out badly wrong (undetected in an earlier manual run of this
    # runner: E.eng with mindia silently gave 1173 m instead of the correct
    # 1503 m). Filenames ending in _sintubo carry hardware-only mass and are
    # the ones meant for this architecture; anything else triggers a warning
    # rather than a silent wrong answer.
    if arch == "mindia" and "sintubo" not in Path(eng_path).stem:
        raise ValueError(
            f"'{Path(eng_path).name}' likely double-counts the aluminium tube mass "
            "under the 'mindia' architecture (which models the tube as airframe "
            "structure). Use the '*_sintubo.eng' variant, which carries only "
            "nozzle+closures mass. See simulation/flight/architecture.py header."
        )

    if arch == "mindia":
        built, od = A.design_mindia(fin, eng_path)
    elif arch == "separate":
        built, od = A.design_separate(fin, eng_path)
    else:
        raise ValueError(f"Unknown architecture '{arch}', expected 'mindia' or 'separate'")

    result = A.fly(built, od, wind=wind)
    result["ok"] = True
    result["architecture"] = arch
    result["eng_path"] = eng_path
    result["fin"] = fin
    result["wind"] = wind
    return result


def main():
    try:
        params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
        result = run(params)
    except Exception as e:
        result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
