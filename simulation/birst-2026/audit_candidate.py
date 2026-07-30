#!/usr/bin/env python3
"""Independent constraint audit, read straight from a saved .ork.

Deliberately does not import the optimizer or re-simulate: it reads the flight
data OpenRocket itself wrote into the file, and applies the mission's own
windows.  A bug in the search that made a candidate look feasible cannot hide
from this, because nothing here shares code with the search.

Usage:  audit_candidate.py "Tars Crew 9075.ork" [...]
"""

from __future__ import annotations

import math
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

TARGET_ALTITUDE_M = 300.0
MIN_PAYLOAD_G = 60.0
MAX_LAUNCH_MASS_G = 1500.0
STABILITY_MIN_CAL = 1.5
STABILITY_MAX_CAL = 3.0
MAX_AOA_DEG = 15.0
MAX_DESCENT_M_S = 6.0

MISSION_CONDITIONS = {
    "launchrodlength": 2.0,
    "windaverage": 4.0,
    "windturbulence": 0.0,
    "launchrodangle": 0.0,
    "timestep": 0.05,
}


def score(apogee_m: float, payload_g: float) -> float:
    return 200.0 - ((TARGET_ALTITUDE_M - apogee_m) ** 2) / 4.0 + payload_g / 2.0


def series(branch, types, name):
    if name not in types:
        return None
    index = types.index(name)
    out = []
    for point in branch.iter("datapoint"):
        try:
            out.append(float(point.text.split(",")[index]))
        except (ValueError, IndexError):
            out.append(float("nan"))
    return out


def window(times, values, low, high):
    return [
        value
        for time, value in zip(times, values)
        if math.isfinite(value) and low <= time <= high
    ]


def audit(path: Path) -> bool:
    root = ET.fromstring(zipfile.ZipFile(path).read("rocket.ork"))
    print("=" * 72)
    print(path.name)

    checks: list[tuple[str, bool, str]] = []

    stages = [s for s in root.iter("stage") if s.get("number") is None]
    checks.append(("single stage", len(stages) == 1, f"{len(stages)} stage(s)"))

    # The rule is about the flight that gets scored, which is the default
    # configuration.  Extra configurations left over in the file are a hazard
    # worth reporting, but they are not themselves a rule violation.
    configs = list(root.iter("motorconfiguration"))
    default_id = next(
        (c.get("configid") for c in configs if c.get("default") == "true"), None
    )
    scored_motors = [
        m.findtext("designation")
        for m in root.iter("motor")
        if m.get("configid") == default_id and m.findtext("designation")
    ]
    checks.append((
        "single motor in scored config",
        len(scored_motors) == 1,
        f"{scored_motors or 'none'}",
    ))

    warnings: list[str] = []
    if len(configs) > 1:
        names = [c.findtext("name") for c in configs]
        warnings.append(
            f"{len(configs)} flight configurations present; only the default is "
            f"scored. Leftovers: {[n for n in names if n]}"
        )
    if any(
        component.findtext("overridemass") == "0.0" for component in root.iter()
    ):
        zeroed = [
            component.findtext("name")
            for component in root.iter()
            if component.findtext("overridemass") == "0.0"
        ]
        warnings.append(f"zero mass overrides on: {zeroed}")

    simulation = next(iter(root.iter("simulation")), None)
    if simulation is None:
        print("  no simulation stored")
        return False

    conditions = simulation.find("conditions")
    for key, expected in MISSION_CONDITIONS.items():
        actual = conditions.findtext(key)
        ok = actual is not None and abs(float(actual) - expected) < 1e-9
        checks.append((f"condition {key}={expected}", ok, str(actual)))

    branch = next(iter(simulation.iter("databranch")), None)
    if branch is None:
        print("  no flight data stored — re-run and save simulation data")
        return False

    types = (branch.get("types") or "").split(",")
    events = {e.get("type"): float(e.get("time")) for e in branch.iter("event")}
    rod = events.get("launchrod")
    burnout = events.get("burnout")
    if rod is None or burnout is None:
        print(f"  missing launchrod/burnout events: {sorted(events)}")
        return False

    time = series(branch, types, "Time")
    aoa = series(branch, types, "Angle of attack")
    stability = series(branch, types, "Stability margin calibers")
    altitude = series(branch, types, "Altitude")
    mass = series(branch, types, "Mass")
    velocity = series(branch, types, "Total velocity")

    liftoff_g = next(m for m in mass if math.isfinite(m)) * 1000.0
    apogee_m = max(a for a in altitude if math.isfinite(a))

    payload_g = 0.0
    for component in root.iter("masscomponent"):
        text = component.findtext("mass")
        if text:
            payload_g += float(text) * 1000.0

    # The mission measures AOA after guide departure and stability between guide
    # departure and burnout.  Descent is excluded from AOA by the deployment
    # event: a rocket under canopy hangs sideways and would read ~90 degrees.
    deploy = events.get("recoverydevicedeployment", float("inf"))
    aoa_deg = [math.degrees(v) for v in window(time, aoa, rod, deploy)]
    stab = window(time, stability, rod, burnout)
    descent = next(
        (v for t, v in reversed(list(zip(time, velocity))) if math.isfinite(v)), float("nan")
    )

    checks.append(("payload >= 60 g", payload_g >= MIN_PAYLOAD_G, f"{payload_g:.2f} g"))
    checks.append((
        "liftoff <= 1500 g",
        liftoff_g <= MAX_LAUNCH_MASS_G + 1e-6,
        f"{liftoff_g:.2f} g",
    ))
    checks.append((
        "stability 1.5-3.0 cal",
        bool(stab) and min(stab) >= STABILITY_MIN_CAL and max(stab) <= STABILITY_MAX_CAL,
        f"{min(stab):.3f}..{max(stab):.3f} cal" if stab else "no data",
    ))
    checks.append((
        "max AOA <= 15 deg",
        bool(aoa_deg) and max(aoa_deg) <= MAX_AOA_DEG,
        f"{max(aoa_deg):.2f} deg" if aoa_deg else "no data",
    ))
    checks.append((
        "recovery deployed",
        "recoverydevicedeployment" in events,
        f"t={events.get('recoverydevicedeployment', float('nan')):.2f} s",
    ))
    checks.append((
        "descent <= 6 m/s",
        math.isfinite(descent) and descent <= MAX_DESCENT_M_S,
        f"{descent:.3f} m/s",
    ))

    for label, ok, detail in checks:
        print(f"  [{'OK ' if ok else 'FAIL'}] {label:30s} {detail}")
    for warning in warnings:
        print(f"  [WARN] {warning}")

    value = score(apogee_m, payload_g)
    print(f"  apogee {apogee_m:.3f} m   payload {payload_g:.2f} g   SCORE {value:.3f}")

    qualifies = all(ok for _, ok, _ in checks)
    print(f"  QUALIFIES: {qualifies}")
    return qualifies


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    results = [audit(Path(arg)) for arg in sys.argv[1:]]
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
