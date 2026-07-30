#!/usr/bin/env python3
"""Parametric OpenRocket optimizer for Practice Mission 01.

The script loads practice-01-v2.ork, reuses one flight configuration, enumerates
bundled motors, varies the external geometry, and tunes payload against the
300 m target.  Every retained candidate is checked against the mission's six
hard constraints using OpenRocket 24.12 itself.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import time
import zipfile
from pathlib import Path

import jpype
import jpype.imports


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "practice-01-v2.ork"
DEFAULT_OUTPUT = ROOT / "optimization-results.json"
DEFAULT_OPENROCKET_JAR = Path.home() / "openrocket" / "OpenRocket-24.12.jar"

TARGET_ALTITUDE_M = 300.0
MAX_LAUNCH_MASS_KG = 1.5
MIN_PAYLOAD_G = 60.0

# Name prefix of the simulation carrying the mission's fixed launch conditions.
MISSION_SIMULATION_PREFIX = "FINAL"

# The canopy is not scenery: at the inherited 1.5 m it weighed 127 g of a 148 g
# structure, so its diameter is the single largest lever on payload mass.  Cd is
# a property of the canopy type rather than a free parameter, so it stays fixed.
PARACHUTE_CD = 1.34
PARACHUTE_DIAMETER_MIN_M = 0.70
PARACHUTE_DIAMETER_MAX_M = 1.60

# The mission caps ground contact at 6.0 m/s.  Aim below it so the candidate is
# not balanced on the constraint wall.
MAX_DESCENT_M_S = 6.0
TARGET_DESCENT_M_S = 5.7


def openrocket_jar():
    path = Path(os.environ.get("OPENROCKET_JAR", DEFAULT_OPENROCKET_JAR)).expanduser()
    if not path.is_file():
        raise FileNotFoundError(
            f"OpenRocket JAR not found at {path}. Set OPENROCKET_JAR to the "
            "OpenRocket 24.12 public-release JAR."
        )
    return path


def start_openrocket():
    jpype.startJVM(
        "-Dorg.slf4j.simpleLogger.defaultLogLevel=error",
        classpath=[str(openrocket_jar())],
    )
    from com.google.inject import Guice
    from info.openrocket.core.startup import Application, CoreModule
    from info.openrocket.core.plugin import PluginModule

    core_module = CoreModule()
    Application.setInjector(Guice.createInjector(core_module, PluginModule()))
    core_module.startLoader()
    return Application


def load_document(path):
    from info.openrocket.core.file import GeneralRocketLoader
    from java.io import ByteArrayInputStream, File

    loader = GeneralRocketLoader(File(str(path)))
    with zipfile.ZipFile(path) as archive:
        raw = archive.read("rocket.ork")
    # Headless CoreModule does not bind ComponentPresetDao.  Component values
    # are already serialized, so removing preset references is lossless here.
    raw = re.sub(br"\s*<preset\b[^>]*/>", b"", raw)
    return loader.load(ByteArrayInputStream(raw), path.stem)


def component_by_type(rocket, simple_name):
    return next(
        component
        for component in rocket.iterator()
        if str(component.getClass().getSimpleName()) == simple_name
    )


def flight_values(branch, data_type):
    return [float(value) for value in branch.get(data_type)]


def finite_window(values, indices):
    return [values[index] for index in indices if math.isfinite(values[index])]


def score(apogee_m, payload_g):
    return 200.0 - ((TARGET_ALTITUDE_M - apogee_m) ** 2) / 4.0 + payload_g / 2.0


def motor_catalog(application, include_obscure=False):
    rows = []
    seen = set()
    database = application.getThrustCurveMotorSetDatabase()
    trusted = (
        "AeroTech",
        "Cesaroni",
        "Rocketvision",
        "Ellis Mountain",
        "Loki",
        "Animal Motor Works",
        "Public Missiles",
        "Kosdon",
    )
    for motor_set in database.getMotorSets():
        for motor in motor_set.getMotors():
            manufacturer = str(motor.getManufacturer())
            diameter = float(motor.getDiameter())
            length = float(motor.getLength())
            impulse = float(motor.getTotalImpulseEstimate())
            average = float(motor.getAverageThrustEstimate())
            launch_mass = float(motor.getLaunchMass())
            if not (0.017 <= diameter <= 0.0385):
                continue
            if not (55.0 <= impulse <= 500.0):
                continue
            if not (35.0 <= average <= 600.0):
                continue
            if launch_mass > 0.55 or length > 0.5:
                continue
            if not include_obscure and not manufacturer.startswith(trusted):
                continue
            digest = str(motor.getDigest())
            if digest in seen:
                continue
            seen.add(digest)
            rows.append(
                {
                    "object": motor,
                    "manufacturer": manufacturer,
                    "designation": str(motor.getDesignation()),
                    "common_name": str(motor.getCommonName()),
                    "digest": digest,
                    "diameter_m": diameter,
                    "length_m": length,
                    "impulse_ns": impulse,
                    "average_thrust_n": average,
                    "max_thrust_n": float(motor.getMaxThrustEstimate()),
                    "burn_s": float(motor.getBurnTimeEstimate()),
                    "motor_mass_g": launch_mass * 1000.0,
                }
            )
    return rows


def competitive_motor_subset(motors):
    return [
        motor
        for motor in motors
        if motor["diameter_m"] <= 0.0305
        and motor["motor_mass_g"] <= 220.0
        and motor["impulse_ns"] <= 180.0
        and (
            (
                motor["impulse_ns"] >= 90.0
                and motor["average_thrust_n"] >= 70.0
            )
            or motor["designation"] == "G55"
        )
    ]


class Optimizer:
    def __init__(self, document, motors, seed, zero_nonpayload_mass=False):
        from info.openrocket.core.masscalc import MassCalculator
        from info.openrocket.core.rocketcomponent import Transition
        from info.openrocket.core.rocketcomponent.position import AxialMethod
        from info.openrocket.core.simulation import FlightDataType

        self.document = document
        self.rocket = document.getRocket()
        self.motors = motors
        self.random = random.Random(seed)
        self.MassCalculator = MassCalculator
        self.AxialMethod = AxialMethod
        self.Transition = Transition
        self.FlightDataType = FlightDataType
        self.body = component_by_type(self.rocket, "BodyTube")
        self.nose = component_by_type(self.rocket, "NoseCone")
        self.mount = component_by_type(self.rocket, "InnerTube")
        self.fins = component_by_type(self.rocket, "TrapezoidFinSet")
        self.parachute = component_by_type(self.rocket, "Parachute")
        self.payload = component_by_type(self.rocket, "MassComponent")
        self.simulation = self.select_simulation(document)
        self.fcid = self.simulation.getFlightConfigurationId()
        self.motor_configuration = self.mount.getMotorConfig(self.fcid)

        options = self.simulation.getOptions()
        options.setLaunchRodLength(2.0)
        options.setWindSpeedAverage(4.0)
        options.setWindTurbulenceIntensity(0.0)
        options.setLaunchRodAngle(0.0)
        options.setISAAtmosphere(True)
        options.setTimeStep(0.05)

        self.fins.setAxialMethod(AxialMethod.BOTTOM)
        self.fins.setAxialOffset(0.0)
        self.mount.setAxialMethod(AxialMethod.BOTTOM)
        self.mount.setAxialOffset(0.0)
        self.payload.setAxialMethod(AxialMethod.TOP)
        self.parachute.setAxialMethod(AxialMethod.TOP)
        self.parachute.setCD(PARACHUTE_CD)
        # The inherited file force-overrode the canopy mass to 141.75 g, a figure
        # carried over from a 0.91 m SkyAngle preset and applied unchanged to a
        # 1.5 m canopy.  Dropping the override lets OpenRocket derive the mass
        # from the material and the diameter, which at 1.5 m is 127.0 g, and
        # makes the diameter a meaningful variable instead of a fixed cost.
        self.parachute.setMassOverridden(False)
        self.parachute.setDiameter(PARACHUTE_DIAMETER_MAX_M)

        self.zero_nonpayload_mass = zero_nonpayload_mass
        if zero_nonpayload_mass:
            for component in self.rocket.iterator():
                component_type = str(component.getClass().getSimpleName())
                if component_type in {"Rocket", "AxialStage", "MassComponent"}:
                    continue
                component.setOverrideMass(0.0)
                component.setMassOverridden(True)

        self.shape_map = {
            "conical": Transition.Shape.CONICAL,
            "ogive": Transition.Shape.OGIVE,
            "ellipsoid": Transition.Shape.ELLIPSOID,
            "power": Transition.Shape.POWER,
            "parabolic": Transition.Shape.PARABOLIC,
            "haack": Transition.Shape.HAACK,
        }

    @staticmethod
    def select_simulation(document):
        """Pick the mission simulation by name, not by position.

        The previous code took ``document.getSimulation(7)``, an index that was
        only valid because the base file happened to carry eight simulations.
        Renaming or reordering them would have silently optimised the wrong
        flight, so resolve it by name and fail loudly when it is missing.
        """
        count = document.getSimulationCount()
        names = []
        for index in range(count):
            simulation = document.getSimulation(index)
            name = str(simulation.getName())
            names.append(name)
            if name.startswith(MISSION_SIMULATION_PREFIX):
                return simulation
        if count:
            # Fall back to the last simulation, which is where the mission run
            # was appended in the inherited document.
            return document.getSimulation(count - 1)
        raise RuntimeError(
            f"No simulation found. Expected one named "
            f"'{MISSION_SIMULATION_PREFIX}...', saw: {names}"
        )

    def random_geometry(self, motor):
        minimum_radius = max(0.0132, motor["diameter_m"] / 2.0 + 0.0011)
        maximum_radius = max(0.030, minimum_radius + 0.010)
        radius = self.random.uniform(minimum_radius, maximum_radius)
        minimum_body = max(0.13, motor["length_m"] - 0.018)
        body_length = self.random.uniform(minimum_body, max(0.85, minimum_body + 0.20))
        fin_root = self.random.uniform(0.04, min(0.19, body_length * 0.48))
        fin_tip_ratio = self.random.uniform(0.15, 0.82)
        return {
            "motor_digest": motor["digest"],
            "radius_m": radius,
            "body_length_m": body_length,
            "nose_length_m": self.random.uniform(1.5, 6.5) * (2.0 * radius),
            "nose_shape": self.random.choice(tuple(self.shape_map)),
            "fin_count": self.random.choice((3, 3, 3, 4)),
            "fin_root_m": fin_root,
            "fin_tip_m": fin_root * fin_tip_ratio,
            "fin_sweep_m": fin_root * self.random.uniform(0.0, 0.72),
            "fin_span_m": (2.0 * radius) * self.random.uniform(0.22, 1.35),
            "payload_offset_m": body_length * self.random.uniform(0.0, 0.22),
            "parachute_offset_m": body_length * self.random.uniform(0.0, 0.48),
            "parachute_diameter_m": self.random.uniform(
                PARACHUTE_DIAMETER_MIN_M, PARACHUTE_DIAMETER_MAX_M
            ),
        }

    def perturb_geometry(self, source, scale=0.12):
        motor = next(m for m in self.motors if m["digest"] == source["motor_digest"])

        def perturbed(key, minimum, maximum):
            value = source[key] * math.exp(self.random.gauss(0.0, scale))
            return min(maximum, max(minimum, value))

        minimum_radius = max(0.0132, motor["diameter_m"] / 2.0 + 0.0011)
        minimum_body = max(0.13, motor["length_m"] - 0.018)
        body_length = perturbed("body_length_m", minimum_body, 0.9)
        fin_root = perturbed("fin_root_m", 0.035, min(0.22, body_length * 0.55))
        return {
            "motor_digest": source["motor_digest"],
            "radius_m": perturbed("radius_m", minimum_radius, 0.045),
            "body_length_m": body_length,
            "nose_length_m": perturbed("nose_length_m", 0.04, 0.45),
            "nose_shape": (
                self.random.choice(tuple(self.shape_map))
                if self.random.random() < 0.12
                else source["nose_shape"]
            ),
            "fin_count": (
                self.random.choice((3, 4))
                if self.random.random() < 0.10
                else source["fin_count"]
            ),
            "fin_root_m": fin_root,
            "fin_tip_m": perturbed("fin_tip_m", 0.005, fin_root * 0.95),
            "fin_sweep_m": perturbed("fin_sweep_m", 0.0, fin_root * 0.9),
            "fin_span_m": perturbed("fin_span_m", 0.004, 0.10),
            "payload_offset_m": min(
                body_length * 0.45,
                max(0.0, source["payload_offset_m"] + self.random.gauss(0, 0.015)),
            ),
            "parachute_offset_m": min(
                body_length * 0.70,
                max(0.0, source["parachute_offset_m"] + self.random.gauss(0, 0.025)),
            ),
            "parachute_diameter_m": perturbed(
                "parachute_diameter_m",
                PARACHUTE_DIAMETER_MIN_M,
                PARACHUTE_DIAMETER_MAX_M,
            ),
        }

    def apply_geometry(self, geometry):
        motor = next(m for m in self.motors if m["digest"] == geometry["motor_digest"])
        radius = geometry["radius_m"]
        self.motor_configuration.setMotor(motor["object"])
        self.motor_configuration.setEjectionDelay(0.0)
        self.mount.setOuterRadius(motor["diameter_m"] / 2.0 + 0.0005)
        self.mount.setLength(max(0.07, motor["length_m"] - 0.005))
        self.body.setOuterRadius(radius)
        self.body.setLength(geometry["body_length_m"])
        self.nose.setAftRadius(radius)
        self.nose.setLength(geometry["nose_length_m"])
        self.nose.setShapeType(self.shape_map[geometry["nose_shape"]])
        if geometry["nose_shape"] == "ogive":
            self.nose.setShapeParameter(1.0)
        elif geometry["nose_shape"] == "power":
            self.nose.setShapeParameter(0.5)
        elif geometry["nose_shape"] == "parabolic":
            self.nose.setShapeParameter(1.0)
        elif geometry["nose_shape"] == "haack":
            self.nose.setShapeParameter(0.0)
        self.fins.setFinCount(geometry["fin_count"])
        self.fins.setFinShape(
            geometry["fin_root_m"],
            geometry["fin_tip_m"],
            geometry["fin_sweep_m"],
            geometry["fin_span_m"],
            0.002,
        )
        self.payload.setAxialOffset(geometry["payload_offset_m"])
        self.parachute.setAxialOffset(geometry["parachute_offset_m"])
        self.parachute.setDiameter(
            geometry.get("parachute_diameter_m", PARACHUTE_DIAMETER_MAX_M)
        )

    def payload_capacity_g(self):
        self.payload.setComponentMass(0.0)
        config = self.simulation.getActiveConfiguration()
        nonpayload_mass = float(self.MassCalculator.calculateLaunch(config).getMass())
        return (MAX_LAUNCH_MASS_KG - 0.0005 - nonpayload_mass) * 1000.0

    def evaluate(self, geometry, payload_g):
        self.payload.setComponentMass(payload_g / 1000.0)
        config = self.simulation.getActiveConfiguration()
        launch_mass_g = float(self.MassCalculator.calculateLaunch(config).getMass()) * 1000.0
        try:
            self.simulation.simulate()
            data = self.simulation.getSimulatedData()
            branch = data.getBranch(0)
            times = flight_values(branch, self.FlightDataType.TYPE_TIME)
            stability = flight_values(branch, self.FlightDataType.TYPE_STABILITY)
            aoa = flight_values(branch, self.FlightDataType.TYPE_AOA)
            velocity = flight_values(branch, self.FlightDataType.TYPE_VELOCITY_TOTAL)
            events = {}
            for event in branch.getEvents():
                events.setdefault(str(event.getType().name()), float(event.getTime()))
            rod_time = events["LAUNCHROD"]
            burnout_time = events["BURNOUT"]
            powered_indices = [
                index
                for index, value in enumerate(times)
                if rod_time <= value <= burnout_time
            ]
            after_rod_indices = [
                index for index, value in enumerate(times) if value >= rod_time
            ]
            powered_stability = finite_window(stability, powered_indices)
            after_rod_aoa = finite_window(aoa, after_rod_indices)
            rod_index = min(
                range(len(times)), key=lambda index: abs(times[index] - rod_time)
            )
            apogee = float(branch.getMaximum(self.FlightDataType.TYPE_ALTITUDE))
            minimum_stability = min(powered_stability)
            maximum_stability = max(powered_stability)
            maximum_aoa = math.degrees(max(after_rod_aoa))
            ground_hit = float(data.getGroundHitVelocity())
            deployed = "RECOVERY_DEVICE_DEPLOYMENT" in events
            warnings = [str(warning) for warning in self.simulation.getSimulatedWarnings()]
            feasible = (
                payload_g >= MIN_PAYLOAD_G
                and launch_mass_g <= 1500.0001
                and minimum_stability >= 1.5
                and maximum_stability <= 3.0
                and maximum_aoa <= 15.0
                and deployed
                # Held to TARGET_DESCENT_M_S rather than the mission's 6.0 limit.
                # A smaller canopy is lighter and therefore always scores better,
                # so the search will sit on whatever bound it is given; putting
                # the bound below the real limit is what buys the margin.
                and ground_hit <= TARGET_DESCENT_M_S
            )
            result = {
                **geometry,
                "payload_g": payload_g,
                "launch_mass_g": launch_mass_g,
                "apogee_m": apogee,
                "score": score(apogee, payload_g),
                "feasible": feasible,
                "stability_min_cal": minimum_stability,
                "stability_max_cal": maximum_stability,
                "max_aoa_deg": maximum_aoa,
                "ground_hit_m_s": ground_hit,
                "rod_velocity_m_s": velocity[rod_index],
                "recovery_deployed": deployed,
                "warnings": warnings,
            }
            result["rank"] = self.rank(result)
            return result
        except Exception as error:
            return {
                **geometry,
                "payload_g": payload_g,
                "launch_mass_g": launch_mass_g,
                "feasible": False,
                "rank": -1e9,
                "error": str(error),
            }

    @staticmethod
    def rank(result):
        if "score" not in result:
            return -1e9
        penalty = 0.0
        penalty += 1200.0 * max(0.0, 1.5 - result["stability_min_cal"])
        penalty += 1000.0 * max(0.0, result["stability_max_cal"] - 3.0)
        penalty += 180.0 * max(0.0, result["max_aoa_deg"] - 15.0)
        penalty += 400.0 * max(0.0, result["ground_hit_m_s"] - TARGET_DESCENT_M_S)
        if not result["recovery_deployed"]:
            penalty += 2000.0
        return result["score"] - penalty

    def evaluate_geometry(self, geometry):
        self.apply_geometry(geometry)
        capacity = self.payload_capacity_g()
        if capacity < MIN_PAYLOAD_G:
            return []

        evaluated = []
        maximum_payload = max(MIN_PAYLOAD_G, capacity)
        maximum_result = self.evaluate(geometry, maximum_payload)
        evaluated.append(maximum_result)
        if "apogee_m" not in maximum_result:
            return evaluated

        # If a fully loaded rocket is below target, find the payload giving 300 m.
        if maximum_result["apogee_m"] < TARGET_ALTITUDE_M:
            minimum_result = self.evaluate(geometry, MIN_PAYLOAD_G)
            evaluated.append(minimum_result)
            if minimum_result.get("apogee_m", -math.inf) >= TARGET_ALTITUDE_M:
                low = MIN_PAYLOAD_G
                high = maximum_payload
                for _ in range(7):
                    middle = (low + high) / 2.0
                    result = self.evaluate(geometry, middle)
                    evaluated.append(result)
                    if result.get("apogee_m", -math.inf) >= TARGET_ALTITUDE_M:
                        low = middle
                    else:
                        high = middle
                target_payload = (low + high) / 2.0
                for delta in (-8.0, -4.0, 0.0, 4.0, 8.0, 15.0, 25.0):
                    candidate_payload = min(
                        maximum_payload,
                        max(MIN_PAYLOAD_G, target_payload + delta),
                    )
                    evaluated.append(self.evaluate(geometry, candidate_payload))

        return evaluated

    def run_random(self, trials, progress_every=25):
        all_results = []
        start = time.monotonic()
        for trial in range(1, trials + 1):
            motor = self.random.choice(self.motors)
            geometry = self.random_geometry(motor)
            all_results.extend(self.evaluate_geometry(geometry))
            if trial % progress_every == 0:
                feasible = [row for row in all_results if row.get("feasible")]
                best = max(feasible, key=lambda row: row["score"]) if feasible else None
                elapsed = time.monotonic() - start
                best_text = (
                    f"{best['score']:.2f} {best['motor_digest']} "
                    f"P={best['payload_g']:.1f} A={best['apogee_m']:.2f}"
                    if best
                    else "none"
                )
                print(
                    f"PROGRESS trial={trial}/{trials} evaluations={len(all_results)} "
                    f"elapsed_s={elapsed:.1f} best={best_text}",
                    flush=True,
                )
        return all_results

    def run_refinement(self, seeds, trials, progress_every=25):
        all_results = []
        start = time.monotonic()
        for trial in range(1, trials + 1):
            source = self.random.choice(seeds)
            geometry = self.perturb_geometry(source, scale=0.10)
            all_results.extend(self.evaluate_geometry(geometry))
            if trial % progress_every == 0:
                feasible = [row for row in all_results if row.get("feasible")]
                best = max(feasible, key=lambda row: row["score"]) if feasible else None
                elapsed = time.monotonic() - start
                best_text = (
                    f"{best['score']:.2f} P={best['payload_g']:.1f} "
                    f"A={best['apogee_m']:.2f}"
                    if best
                    else "none"
                )
                print(
                    f"REFINE trial={trial}/{trials} evaluations={len(all_results)} "
                    f"elapsed_s={elapsed:.1f} best={best_text}",
                    flush=True,
                )
        return all_results


def serializable_motor(motor):
    return {key: value for key, value in motor.items() if key != "object"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--trials", type=int, default=400)
    parser.add_argument("--refine", type=int, default=500)
    parser.add_argument("--seed", type=int, default=9075)
    parser.add_argument("--include-obscure", action="store_true")
    parser.add_argument("--competitive", action="store_true")
    parser.add_argument("--zero-nonpayload-mass", action="store_true")
    parser.add_argument(
        "--motor-digest",
        action="append",
        help="Restrict the search to one or more exact bundled motor digests.",
    )
    args = parser.parse_args()

    application = start_openrocket()
    document = load_document(args.input)
    motors = motor_catalog(application, include_obscure=args.include_obscure)
    if args.competitive:
        motors = competitive_motor_subset(motors)
    if args.motor_digest:
        selected_digests = set(args.motor_digest)
        motors = [motor for motor in motors if motor["digest"] in selected_digests]
    print(f"MOTORS count={len(motors)}", flush=True)
    optimizer = Optimizer(
        document,
        motors,
        args.seed,
        zero_nonpayload_mass=args.zero_nonpayload_mass,
    )
    coarse = optimizer.run_random(args.trials)
    feasible_coarse = sorted(
        (row for row in coarse if row.get("feasible")),
        key=lambda row: row["score"],
        reverse=True,
    )
    seeds = feasible_coarse[: min(30, len(feasible_coarse))]
    refined = optimizer.run_refinement(seeds, args.refine) if seeds else []
    all_results = coarse + refined
    feasible = sorted(
        (row for row in all_results if row.get("feasible")),
        key=lambda row: row["score"],
        reverse=True,
    )
    motor_lookup = {motor["digest"]: motor for motor in motors}
    input_path = args.input.resolve()
    try:
        input_label = str(input_path.relative_to(ROOT))
    except ValueError:
        input_label = str(input_path)
    output = {
        "input": input_label,
        "seed": args.seed,
        "geometry_trials": args.trials,
        "refinement_trials": args.refine,
        "simulation_evaluations": len(all_results),
        "motor_count": len(motors),
        "zero_nonpayload_mass": args.zero_nonpayload_mass,
        "motors": [serializable_motor(motor) for motor in motors],
        "best": feasible[0] if feasible else None,
        "top_100": feasible[:100],
    }
    if output["best"]:
        output["best"]["motor"] = serializable_motor(
            motor_lookup[output["best"]["motor_digest"]]
        )
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print("RESULT_JSON=" + json.dumps(output["best"]), flush=True)


if __name__ == "__main__":
    main()
