#!/usr/bin/env python3
"""
Runs INSIDE ~/openMotor/.venv, with cwd=~/openMotor (motorlib only imports
that way -- see console/core/adapters/openmotor.py for why). Imports the
existing sweep_bates.py from the project's own simulation folder (no physics
is duplicated here), runs a bounded grid, and prints one JSON object to
stdout. The console adapter calls this as a subprocess and parses the output.

Usage (only meant to be invoked by the adapter, but works standalone):
    python om_sweep.py '{"core_range": [9, 17], "seg_counts": [2,3,4,5,6],
                         "seg_len_range_mm": [25, 60, 5], "max_total_mm": 320}'
"""
import json
import sys
import itertools
from pathlib import Path

# motorlib is an unpackaged source tree that only imports with
# ~/openMotor on sys.path (normally satisfied by cwd when run interactively
# from that directory -- not the case when this script is invoked as a
# subprocess from elsewhere, so it's added explicitly here).
sys.path.insert(0, str(Path.home() / "openMotor"))
sys.path.insert(0, str(Path.home() / "rocketry-portfolio" / "simulation" / "internal-ballistics"))

import sweep_bates as S  # noqa: E402


def run_sweep(params: dict) -> dict:
    core_lo, core_hi = params.get("core_range_mm", [9, 17])
    seg_counts = params.get("seg_counts", [2, 3, 4, 5, 6])
    len_lo, len_hi, len_step = params.get("seg_len_range_mm", [25, 60, 5])
    max_total_mm = params.get("max_total_mm", 320)
    target_kn = params.get("target_peak_kn", 280.0)

    S.TARGET_PEAK_KN = float(target_kn)

    core_diameters = [d / 1000 for d in range(core_lo, core_hi)]
    segment_lengths = [l / 1000 for l in range(len_lo, len_hi + 1, len_step)]

    rejected = {"kn": 0, "port": 0, "flux": 0, "mach": 0, "pressure": 0}
    rows = []
    for core_d, n_seg, seg_len in itertools.product(core_diameters, seg_counts, segment_lengths):
        total_len = n_seg * seg_len
        if total_len > max_total_mm / 1000:
            continue
        if seg_len > 3 * S.GRAIN_OD:
            continue

        res, throat, exit_d = S.simulate(core_d, n_seg, seg_len)
        if res is None:
            continue

        kn_avg = S.kn_average(res)
        if kn_avg < S.KN_MIN:
            rejected["kn"] += 1
            continue
        if res.getPortRatio() < S.MIN_PORT_THROAT:
            rejected["port"] += 1
            continue
        if res.getPeakMassFlux() > S.MAX_MASS_FLUX:
            rejected["flux"] += 1
            continue
        if res.getPeakMachNumber() > S.MAX_MACH:
            rejected["mach"] += 1
            continue
        if res.getMaxPressure() > S.MAX_PRESSURE:
            rejected["pressure"] += 1
            continue

        rows.append({
            "core_mm": round(core_d * 1000, 2),
            "n_segments": n_seg,
            "segment_len_mm": round(seg_len * 1000, 2),
            "total_len_mm": round(total_len * 1000, 1),
            "throat_mm": round(throat * 1000, 3),
            "exit_mm": round(exit_d * 1000, 3),
            "kn_peak": round(res.getPeakKN(), 1),
            "kn_avg": round(kn_avg, 1),
            "kn_initial": round(res.getInitialKN(), 1),
            "peak_pressure_mpa": round(res.getMaxPressure() / 1e6, 3),
            "peak_thrust_n": round(res.getAverageForce() and res.channels["force"].getMax(), 1),
            "avg_force_n": round(res.getAverageForce(), 1),
            "impulse_ns": round(res.getImpulse(), 2),
            "burn_time_s": round(res.getBurnTime(), 3),
            "designation": res.getFullDesignation(),
            "propellant_mass_g": round(res.getPropellantMass() * 1000, 2),
            "port_throat_ratio": round(res.getPortRatio(), 2),
            "peak_mass_flux": round(res.getPeakMassFlux(), 1),
            "mass_flux_pct_limit": round(100 * res.getPeakMassFlux() / S.MAX_MASS_FLUX, 1),
        })

    rows.sort(key=lambda r: r["impulse_ns"], reverse=True)

    return {
        "ok": True,
        "tube_id_mm": round(S.TUBE_ID * 1000, 2),
        "grain_od_mm": round(S.GRAIN_OD * 1000, 2),
        "target_peak_kn": S.TARGET_PEAK_KN,
        "n_viable": len(rows),
        "rejected": rejected,
        "rows": rows,
    }


def main():
    try:
        params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
        result = run_sweep(params)
    except Exception as e:
        result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
