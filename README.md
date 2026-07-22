# Solid-Propellant Rocket Engineering Project

A ground-up experimental rocketry project: from internal-ballistics simulation
and airframe optimization, through propellant characterization and a static
test, to a custom data-acquisition system — plus a merged-track contribution to
the OpenRocket open-source flight simulator.

**Author:** Sebastián Velandia · Electronic Engineering
**Status:** ongoing · **Focus:** instrumentation, simulation, flight dynamics

---

## Why this project

Amateur experimental rocketry is one of the few disciplines where a single
person touches the whole engineering chain — thermochemistry, internal
ballistics, compressible flow, aerodynamics, structures, and avionics. This
repository documents that chain end to end, including the parts that **failed**
and what they taught, because honest failure analysis is where the engineering
actually happens.

Everything here was driven by one discipline: **measure before you trust, and
change one variable at a time.**

---

## Highlights

| | |
|---|---|
| **Motor** | 25.4 mm minimum-diameter KNSB (potassium nitrate / sorbitol) BATES-grain motor, F-class, designed from a headless internal-ballistics sweep |
| **Key safety finding** | A Kn in the "safe" 200–280 range is **not** sufficient — 120 Kn-valid configurations all violated port/throat or mass-flux limits. All four limits must hold simultaneously |
| **Airframe** | The aluminium motor tube *is* the airframe (true minimum diameter). Optimized in OpenRocket: **+64 % apogee** from fin-profile and finish alone — the nose shape was irrelevant at Mach 0.77 |
| **Avionics** | Custom ESP32 data-acquisition system; live demonstration of the Nyquist–Shannon theorem and aliasing |
| **Open source** | Diagnosed, fixed, validated and submitted a bug fix to [OpenRocket](https://github.com/openrocket/openrocket) ([issue #3183](https://github.com/openrocket/openrocket/issues/3183), PR #3186) |

---

## Documentation

| Section | What's inside |
|---|---|
| [01 · Internal Ballistics](docs/01-internal-ballistics.md) | Motor design, the Kn-isn't-enough finding, burn-rate sensitivity, nozzle retention |
| [02 · Flight Simulation](docs/02-flight-simulation.md) | OpenRocket airframe study, the +64 % optimization, stability, wind |
| [03 · Propellant & Static Test](docs/03-propellant-and-test.md) | Characterization methodology and the static-test post-mortem (engineering-level) |
| [04 · Avionics DAQ](docs/04-avionics-daq.md) | ESP32 sampling system, Nyquist/aliasing demonstration, results |
| [05 · Open-Source Contribution](docs/05-open-source.md) | The OpenRocket tumble-abort bug: diagnosis → fix → statistical validation |

## Repository layout

```
simulation/internal-ballistics/   # Python sweeps over openMotor's motorlib
simulation/flight/                # OpenRocket driven headless via JPype
avionics/daq-fase1/               # ESP32 firmware + Python capture/plot
images/                           # result figures
docs/                             # engineering write-ups
```

## The engineering arc

```
   MEASURE            ESTIMATE            CONTROL
  (DAQ, done)   →   (sensor fusion)  →   (active TVC)
```

This project is at the **measure** stage. The data-acquisition system is the
instrument that turns the next static test into real numbers (the measured
burn-rate coefficient), which in turn unlocks a data-grounded flight design.

## Safety & scope

This is a documentation and engineering-analysis repository. It deliberately
**does not** include propellant synthesis procedures or quantities. All physical
testing described followed a static-test-first methodology and standard amateur
safety practice (remote ignition, stand-off distance, physical barrier). Nothing
here should be treated as instructions to manufacture energetic materials.

## Tools

Python · [openMotor](https://github.com/reilleya/openMotor) (internal ballistics) ·
[OpenRocket](https://github.com/openrocket/openrocket) (flight, driven via JPype) ·
PlatformIO / ESP32 (Arduino framework) · matplotlib

## License

MIT — see [LICENSE](LICENSE).
