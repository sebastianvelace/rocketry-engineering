#!/usr/bin/env python3
"""Reload and independently verify saved Practice Mission 01 .ork files."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import optimize_practice_mission as search


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ork", nargs="+")
    args = parser.parse_args()
    application = search.start_openrocket()

    from info.openrocket.core.masscalc import MassCalculator
    from info.openrocket.core.simulation import FlightDataType

    reports = []
    for path in args.ork:
        path = Path(path)
        document = search.load_document(path)
        rocket = document.getRocket()
        simulation = document.getSimulation(0)
        options = simulation.getOptions()
        configuration = simulation.getActiveConfiguration()
        payload = search.component_by_type(rocket, "MassComponent")
        parachute = search.component_by_type(rocket, "Parachute")
        motor_configuration = list(configuration.getActiveMotors())[0]
        motor = motor_configuration.getMotor()
        simulation.simulate()
        data = simulation.getSimulatedData()
        branch = data.getBranch(0)
        times = search.flight_values(branch, FlightDataType.TYPE_TIME)
        stability = search.flight_values(branch, FlightDataType.TYPE_STABILITY)
        aoa = search.flight_values(branch, FlightDataType.TYPE_AOA)
        velocity = search.flight_values(branch, FlightDataType.TYPE_VELOCITY_TOTAL)
        events = {}
        for event in branch.getEvents():
            events.setdefault(str(event.getType().name()), float(event.getTime()))
        powered = [
            index
            for index, value in enumerate(times)
            if events["LAUNCHROD"] <= value <= events["BURNOUT"]
        ]
        after_rod = [
            index for index, value in enumerate(times) if value >= events["LAUNCHROD"]
        ]
        rod_index = min(
            range(len(times)),
            key=lambda index: abs(times[index] - events["LAUNCHROD"]),
        )
        payload_g = float(payload.getComponentMass()) * 1000.0
        apogee = float(branch.getMaximum(FlightDataType.TYPE_ALTITUDE))
        report = {
            "file": str(path),
            "rocket_name": str(rocket.getName()),
            "simulation_name": str(simulation.getName()),
            "configuration": str(configuration.getName()),
            "motor": f"{motor.getManufacturer()} {motor.getDesignation()}",
            "single_stage": int(configuration.getActiveStageCount()) == 1,
            "single_motor": len(list(configuration.getActiveMotors())) == 1,
            "payload_g": payload_g,
            "launch_mass_g": float(MassCalculator.calculateLaunch(configuration).getMass())
            * 1000.0,
            "apogee_m": apogee,
            "score": search.score(apogee, payload_g),
            "rod_velocity_m_s": velocity[rod_index],
            "stability_min_cal": min(stability[index] for index in powered),
            "stability_max_cal": max(stability[index] for index in powered),
            "max_aoa_deg": math.degrees(max(aoa[index] for index in after_rod)),
            "ground_hit_m_s": float(data.getGroundHitVelocity()),
            "recovery_deployed": "RECOVERY_DEVICE_DEPLOYMENT" in events,
            "parachute_diameter_m": float(parachute.getDiameter()),
            "parachute_cd": float(parachute.getCD()),
            "guide_length_m": float(options.getLaunchRodLength()),
            "wind_m_s": float(options.getWindSpeedAverage()),
            "turbulence": float(options.getWindTurbulenceIntensity()),
            "guide_angle_deg": math.degrees(float(options.getLaunchRodAngle())),
            "time_step_s": float(options.getTimeStep()),
            "warnings": [str(warning) for warning in simulation.getSimulatedWarnings()],
        }
        report["qualifies"] = (
            report["single_stage"]
            and report["single_motor"]
            and report["payload_g"] >= 60.0
            and report["launch_mass_g"] <= 1500.0001
            and report["stability_min_cal"] >= 1.5
            and report["stability_max_cal"] <= 3.0
            and report["max_aoa_deg"] <= 15.0
            and report["recovery_deployed"]
            and report["ground_hit_m_s"] <= 6.0
        )
        reports.append(report)
    print("RESULT_JSON=" + json.dumps(reports))


if __name__ == "__main__":
    main()
