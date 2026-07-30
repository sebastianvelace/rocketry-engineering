#!/usr/bin/env python3
"""Try every bundled trusted motor lighter than the zero-mass G125T optimum.

For a candidate to beat 886.2499 points it must carry at least 1372.5 g of
payload.  This lets the screen avoid expensive payload searches that cannot
possibly overtake the incumbent.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import optimize_practice_mission as search


ROOT = Path(__file__).resolve().parent
INCUMBENT_SCORE = 886.2499
PAYLOAD_FLOOR_G = 2.0 * (INCUMBENT_SCORE - 200.0)


def low_drag_geometry(optimizer, motor):
    rng = optimizer.random
    minimum_radius = max(0.0130, motor["diameter_m"] / 2.0 + 0.0008)
    radius = minimum_radius + (0.032 - minimum_radius) * rng.random() ** 4
    minimum_body = max(0.13, motor["length_m"] - 0.018)
    body_length = minimum_body + (0.55 - minimum_body) * rng.random() ** 4
    fin_root = rng.uniform(0.025, min(0.13, body_length * 0.55))
    return {
        "motor_digest": motor["digest"],
        "radius_m": radius,
        "body_length_m": body_length,
        "nose_length_m": rng.uniform(2.0, 8.0) * 2.0 * radius,
        "nose_shape": rng.choice(("haack", "parabolic", "ogive", "power")),
        "fin_count": rng.choice((3, 3, 4)),
        "fin_root_m": fin_root,
        "fin_tip_m": fin_root * rng.uniform(0.15, 0.85),
        "fin_sweep_m": fin_root * rng.uniform(0.0, 0.85),
        "fin_span_m": 2.0 * radius * rng.uniform(0.15, 1.10),
        "payload_offset_m": body_length * rng.uniform(0.0, 0.10),
        "parachute_offset_m": body_length * rng.uniform(0.0, 0.30),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials-per-motor", type=int, default=100)
    parser.add_argument("--seed", type=int, default=19075)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "light-motor-screen.json"
    )
    args = parser.parse_args()

    application = search.start_openrocket()
    motors = [
        motor
        for motor in search.motor_catalog(application)
        if motor["motor_mass_g"] < 127.0
    ]
    document = search.load_document(ROOT / "practice-01-v2.ork")
    optimizer = search.Optimizer(
        document, motors, seed=args.seed, zero_nonpayload_mass=True
    )

    summaries = []
    total_evaluations = 0
    for motor_index, motor in enumerate(motors, 1):
        upper_bound = 200.0 + (1499.5 - motor["motor_mass_g"]) / 2.0
        motor_results = []
        for _ in range(args.trials_per_motor):
            geometry = low_drag_geometry(optimizer, motor)
            optimizer.apply_geometry(geometry)
            capacity = optimizer.payload_capacity_g()
            if capacity < PAYLOAD_FLOOR_G:
                continue
            payloads = sorted(
                {
                    capacity,
                    PAYLOAD_FLOOR_G,
                    capacity * 0.75 + PAYLOAD_FLOOR_G * 0.25,
                    capacity * 0.50 + PAYLOAD_FLOOR_G * 0.50,
                    capacity * 0.25 + PAYLOAD_FLOOR_G * 0.75,
                }
            )
            for payload_g in payloads:
                motor_results.append(optimizer.evaluate(geometry, payload_g))
        total_evaluations += len(motor_results)
        feasible = [row for row in motor_results if row.get("feasible")]
        best = max(feasible, key=lambda row: row["score"]) if feasible else None
        summary = {
            "motor": {key: value for key, value in motor.items() if key != "object"},
            "theoretical_upper_bound": upper_bound,
            "evaluations": len(motor_results),
            "best": best,
        }
        summaries.append(summary)
        best_text = (
            f"{best['score']:.2f} P={best['payload_g']:.1f} "
            f"A={best['apogee_m']:.1f} AOA={best['max_aoa_deg']:.1f}"
            if best
            else "no qualifying candidate"
        )
        print(
            f"MOTOR {motor_index}/{len(motors)} {motor['manufacturer']} "
            f"{motor['designation']} mass={motor['motor_mass_g']:.1f} "
            f"upper={upper_bound:.2f} best={best_text}",
            flush=True,
        )

    summaries.sort(
        key=lambda row: (
            row["best"]["score"] if row["best"] is not None else -math.inf
        ),
        reverse=True,
    )
    output = {
        "incumbent_score": INCUMBENT_SCORE,
        "payload_floor_g": PAYLOAD_FLOOR_G,
        "motor_count": len(motors),
        "trials_per_motor": args.trials_per_motor,
        "total_evaluations": total_evaluations,
        "results": summaries,
    }
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(
        "RESULT_JSON="
        + json.dumps(
            {
                "motor_count": len(motors),
                "total_evaluations": total_evaluations,
                "best": summaries[0] if summaries else None,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
