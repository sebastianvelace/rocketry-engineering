#!/usr/bin/env python3
"""Create a clean .ork from one result produced by optimize_practice_mission.py."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import optimize_practice_mission as search


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=ROOT / "optimization-results.json")
    parser.add_argument("--input", type=Path, default=ROOT / "practice-01-v2.ork")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--candidate",
        type=int,
        default=-1,
        help="-1 selects best; non-negative values index top_100",
    )
    parser.add_argument("--rocket-name", default="Tars Crew 9075 — optimized practice")
    parser.add_argument("--payload-g", type=float)
    parser.add_argument("--zero-nonpayload-mass", action="store_true")
    args = parser.parse_args()

    application = search.start_openrocket()
    document = search.load_document(args.input)
    motors = search.competitive_motor_subset(search.motor_catalog(application))
    optimizer = search.Optimizer(
        document,
        motors,
        seed=9075,
        zero_nonpayload_mass=args.zero_nonpayload_mass,
    )
    results = json.loads(args.results.read_text())
    candidate = (
        results["best"] if args.candidate < 0 else results["top_100"][args.candidate]
    )
    geometry_keys = (
        "motor_digest",
        "radius_m",
        "body_length_m",
        "nose_length_m",
        "nose_shape",
        "fin_count",
        "fin_root_m",
        "fin_tip_m",
        "fin_sweep_m",
        "fin_span_m",
        "payload_offset_m",
        "parachute_offset_m",
        "parachute_diameter_m",
    )
    geometry = {key: candidate[key] for key in geometry_keys if key in candidate}
    optimizer.apply_geometry(geometry)

    rocket = document.getRocket()
    rocket.setName(args.rocket_name)
    rocket.setComment(
        "Automated Practice Mission 01 candidate. Generated from practice-01-v2 "
        "with fixed 2 m guide, 4 m/s wind, 0% turbulence, ISA, and 0.05 s step. "
        "This is a simulation optimum; component packaging and structural realism "
        "must be audited separately."
    )
    optimizer.payload.setName("Payload")
    optimizer.parachute.setName(
        f"Parachute {optimizer.parachute.getDiameter() * 100:.0f} cm, "
        f"Cd {float(optimizer.parachute.getCD()):.2f}"
    )
    optimizer.mount.setName("29 mm motor mount")
    optimizer.fins.setName("Optimized trapezoidal fin set")
    configuration = rocket.getFlightConfiguration(optimizer.fcid)
    motor = next(m for m in motors if m["digest"] == geometry["motor_digest"])
    configuration.setName(f"OPT — {motor['designation']}")
    rocket.setSelectedConfiguration(optimizer.fcid)
    optimizer.simulation.setName("FINAL — Practice Mission 01")

    for simulation in list(document.getSimulations()):
        if simulation != optimizer.simulation:
            document.removeSimulation(simulation)
    for configuration_id in list(rocket.getIds()):
        if configuration_id != optimizer.fcid:
            rocket.removeFlightConfiguration(configuration_id)
    rocket.setSelectedConfiguration(optimizer.fcid)

    payload_g = candidate["payload_g"] if args.payload_g is None else args.payload_g
    verified = optimizer.evaluate(geometry, payload_g)
    options = document.getDefaultStorageOptions()
    options.setSaveSimulationData(True)

    from info.openrocket.core.file import GeneralRocketSaver
    from java.io import File

    GeneralRocketSaver().save(File(str(args.output)), document, options)
    print(
        "RESULT_JSON="
        + json.dumps(
            {
                "output": str(args.output),
                "motor": {key: value for key, value in motor.items() if key != "object"},
                "metrics": verified,
            }
        )
    )


if __name__ == "__main__":
    main()
