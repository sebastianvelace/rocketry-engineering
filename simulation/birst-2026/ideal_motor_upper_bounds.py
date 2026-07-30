#!/usr/bin/env python3
"""No-drag upper bounds for motors lighter than the G125T incumbent.

The calculation deliberately gives each challenger an impossible advantage:
zero aerodynamic drag and zero mass for every non-motor, non-payload component.
If its best score still remains below the incumbent, no OpenRocket geometry can
make that motor win under the same mass model.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import optimize_practice_mission as search


ROOT = Path(__file__).resolve().parent
INCUMBENT_SCORE = 886.499999
MIN_PAYLOAD_G = 2.0 * (INCUMBENT_SCORE - 200.0)
GRAVITY = 9.80665
WIND_M_S = 4.0
MAX_AOA_RAD = math.radians(15.0)
MIN_RAIL_VELOCITY_M_S = WIND_M_S / math.tan(MAX_AOA_RAD)
DT = 0.001


def interpolate(x, xs, ys):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    low = 0
    high = len(xs) - 1
    while high - low > 1:
        middle = (low + high) // 2
        if xs[middle] <= x:
            low = middle
        else:
            high = middle
    fraction = (x - xs[low]) / (xs[high] - xs[low])
    return ys[low] + fraction * (ys[high] - ys[low])


def ideal_flight(payload_kg, source_time, source_thrust, source_mass):
    height = 0.0
    velocity = 0.0
    rail_velocity = math.nan
    launched = False
    time = 0.0
    final_time = source_time[-1]
    while time < final_time:
        thrust = interpolate(time, source_time, source_thrust)
        motor_mass = interpolate(time, source_time, source_mass)
        total_mass = payload_kg + motor_mass
        if thrust > total_mass * GRAVITY:
            launched = True
        if launched:
            acceleration = thrust / total_mass - GRAVITY
            previous_height = height
            previous_velocity = velocity
            velocity += acceleration * DT
            height += previous_velocity * DT + 0.5 * acceleration * DT * DT
            if math.isnan(rail_velocity) and height >= 2.0:
                fraction = min(
                    1.0,
                    max(
                        0.0,
                        (2.0 - previous_height)
                        / max(height - previous_height, 1e-12),
                    ),
                )
                rail_velocity = previous_velocity + fraction * (
                    velocity - previous_velocity
                )
        time += DT
    ideal_apogee = height + max(velocity, 0.0) ** 2 / (2.0 * GRAVITY)
    return ideal_apogee, rail_velocity


def upper_bound(motor_row):
    motor = motor_row["object"]
    capacity_g = 1499.5 - motor_row["motor_mass_g"]
    payloads_g = [
        MIN_PAYLOAD_G + (capacity_g - MIN_PAYLOAD_G) * index / 200.0
        for index in range(201)
    ]
    source_time = [float(value) for value in motor.getTimePoints()]
    source_thrust = [float(value) for value in motor.getThrustPoints()]
    source_mass = [float(point.weight) for point in motor.getCGPoints()]
    candidates = []
    for payload_g in payloads_g:
        ideal_apogee, rail_velocity = ideal_flight(
            payload_g / 1000.0,
            source_time,
            source_thrust,
            source_mass,
        )
        # Do not reject slow rail departures here.  Ignoring the AOA constraint
        # makes this a looser, safer upper bound: a motor eliminated by altitude
        # and payload alone remains eliminated even if the rail integration has
        # small numerical error.
        closest_possible_apogee = min(ideal_apogee, 300.0)
        score_upper = (
            200.0
            - (300.0 - closest_possible_apogee) ** 2 / 4.0
            + payload_g / 2.0
        )
        candidates.append((score_upper, payload_g, ideal_apogee, rail_velocity))
    score_upper, payload_g, ideal_apogee, rail_velocity = max(
        candidates, key=lambda row: row[0]
    )
    return {
        "manufacturer": motor_row["manufacturer"],
        "designation": motor_row["designation"],
        "digest": motor_row["digest"],
        "motor_mass_g": motor_row["motor_mass_g"],
        "payload_g": payload_g,
        "ideal_no_drag_apogee_m": ideal_apogee,
        "ideal_rail_velocity_m_s": rail_velocity,
        "minimum_rail_velocity_for_15deg_m_s": MIN_RAIL_VELOCITY_M_S,
        "ideal_rail_meets_15deg_requirement": (
            math.isfinite(rail_velocity)
            and rail_velocity >= MIN_RAIL_VELOCITY_M_S
        ),
        "score_upper_bound": score_upper,
        "can_beat_incumbent": score_upper > INCUMBENT_SCORE,
    }


def every_bundled_light_motor(application):
    rows = []
    seen = set()
    database = application.getThrustCurveMotorSetDatabase()
    for motor_set in database.getMotorSets():
        for motor in motor_set.getMotors():
            digest = str(motor.getDigest())
            launch_mass_g = float(motor.getLaunchMass()) * 1000.0
            if digest in seen or not math.isfinite(launch_mass_g):
                continue
            if launch_mass_g >= 127.0:
                continue
            seen.add(digest)
            rows.append(
                {
                    "object": motor,
                    "manufacturer": str(motor.getManufacturer()),
                    "designation": str(motor.getDesignation()),
                    "digest": digest,
                    "motor_mass_g": launch_mass_g,
                }
            )
    return rows


def main():
    application = search.start_openrocket()
    motors = every_bundled_light_motor(application)
    motors = [
        motor
        for motor in motors
        if float(motor["object"].getMaxThrustEstimate())
        > (MIN_PAYLOAD_G + motor["motor_mass_g"]) / 1000.0 * GRAVITY
    ]
    rows = [upper_bound(motor) for motor in motors]
    rows.sort(key=lambda row: row["score_upper_bound"], reverse=True)
    output = {
        "method": "vertical point mass, zero drag, zero auxiliary mass",
        "time_step_s": DT,
        "incumbent_score": INCUMBENT_SCORE,
        "minimum_payload_to_beat_incumbent_g": MIN_PAYLOAD_G,
        "motor_count": len(rows),
        "challengers_remaining": [
            row for row in rows if row["can_beat_incumbent"]
        ],
        "results": rows,
    }
    (ROOT / "ideal-motor-upper-bounds.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )
    print("RESULT_JSON=" + json.dumps(output))


if __name__ == "__main__":
    main()
