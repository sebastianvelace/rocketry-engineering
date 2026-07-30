#!/usr/bin/env python3
"""Build the competition deliverable from a chosen candidate.

Takes an existing candidate document, applies the canopy and payload decided by
the isolated parachute study, strips every leftover flight configuration and
simulation, names the file from TEAM_NAME.txt, and saves it.

The canopy is the point of this script.  The original search pinned the
parachute at 1.5 m with its mass force-overridden to 141.75 g, a figure carried
over from a 0.91 m preset.  Dropping the override and sizing the canopy against
the mission's own 6 m/s descent limit is worth about 25 points, all of it
converted into payload.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import optimize_practice_mission as O  # noqa: E402


def team_name() -> str:
    return (ROOT / "TEAM_NAME.txt").read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "Tars Crew 9075 - score optimum.ork",
        help="candidate whose airframe geometry is kept",
    )
    parser.add_argument("--parachute-diameter", type=float, default=1.05)
    parser.add_argument("--payload-g", type=float, default=1275.48)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    name = team_name()
    output = args.output or (ROOT / f"{name}.ork")

    O.start_openrocket()
    document = O.load_document(args.source)
    rocket = document.getRocket()

    from info.openrocket.core.simulation import FlightDataType

    chute = O.component_by_type(rocket, "Parachute")
    payload = O.component_by_type(rocket, "MassComponent")

    # Let OpenRocket derive the canopy mass from its material and diameter
    # instead of carrying an override inherited from a different parachute.
    chute.setMassOverridden(False)
    chute.setDiameter(args.parachute_diameter)
    chute.setName(
        f"Parachute {args.parachute_diameter * 100:.0f} cm, "
        f"Cd {float(chute.getCD()):.2f}"
    )
    payload.setComponentMass(args.payload_g / 1000.0)
    payload.setName("Payload")

    simulation = O.Optimizer.select_simulation(document)
    simulation.setName("FINAL — Practice Mission 01")
    options = simulation.getOptions()
    options.setLaunchRodLength(2.0)
    options.setWindSpeedAverage(4.0)
    options.setWindTurbulenceIntensity(0.0)
    options.setLaunchRodAngle(0.0)
    options.setISAAtmosphere(True)
    options.setTimeStep(0.05)

    for other in list(document.getSimulations()):
        if other != simulation:
            document.removeSimulation(other)

    fcid = simulation.getFlightConfigurationId()
    for configuration_id in list(rocket.getIds()):
        if configuration_id != fcid:
            rocket.removeFlightConfiguration(configuration_id)
    rocket.setSelectedConfiguration(fcid)
    rocket.setName(name)
    rocket.setComment(
        "Practice Mission 01 deliverable. Fixed conditions: 2 m guide, 4 m/s "
        "wind, 0% turbulence, ISA, 0.05 s step. Canopy sized against the 6 m/s "
        "descent limit rather than inherited; mass derived from material."
    )

    simulation.simulate()
    data = simulation.getSimulatedData()
    branch = data.getBranch(0)
    apogee = float(branch.getMaximum(FlightDataType.TYPE_ALTITUDE))
    liftoff_g = float(branch.get(FlightDataType.TYPE_MASS)[0]) * 1000.0

    storage = document.getDefaultStorageOptions()
    storage.setSaveSimulationData(True)

    from info.openrocket.core.file import GeneralRocketSaver
    from java.io import File

    GeneralRocketSaver().save(File(str(output)), document, storage)

    print("RESULT_JSON=" + json.dumps({
        "output": str(output),
        "team_name": name,
        "parachute_diameter_m": args.parachute_diameter,
        "parachute_mass_g": float(chute.getMass()) * 1000.0,
        "payload_g": args.payload_g,
        "liftoff_mass_g": liftoff_g,
        "apogee_m": apogee,
        "ground_hit_m_s": float(data.getGroundHitVelocity()),
        "launch_rod_velocity_m_s": float(data.getLaunchRodVelocity()),
        "score": O.score(apogee, args.payload_g),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
