# Project guide — Solid-Propellant Rocket Engineering

Guidance for anyone (human or AI assistant) continuing this project. Read the
**Working principles** first — they were learned the hard way.

---

## Working principles (read this first)

This project runs on one rule: **measure before you trust, and verify before you
conclude.** These are not slogans; every one was paid for with a mistake.

1. **Never build a conclusion on a single, unverified measurement.**
   In this project a subtle firmware bug (undersampling a sine while measuring
   its amplitude) produced a *confident, elaborate, and completely wrong*
   conclusion — a phantom "weak DAC with 3 kΩ output impedance." It took a
   second, independent measurement method (RC step-response) plus the vendor
   documentation to expose it. One measurement is a hypothesis, not a fact.

2. **Cross-check with an independent method.** A frequency-sweep and a
   time-domain step-response measure the same physical quantity (a time
   constant) by different means. When they disagree by 10×, *one of them is
   wrong* — find out which before proceeding. Agreement across methods is what
   turns a number into a fact.

3. **Verify against external documentation / datasheets.** The ESP32 DAC's real
   output resistance (~20 Ω, sources ~12 mA) is documented. Our measurement
   implied ~3 kΩ. The contradiction was the tell. Always sanity-check a
   surprising result against the authoritative source.

4. **Distinguish a measurement artifact from a real phenomenon.** Most
   "surprising physics" at the bench is a flaw in the measurement (a loose
   jumper, an undersampled signal, a source impedance the instrument can't
   handle, an ADC out of its valid range). Suspect the setup before the universe.

5. **When bench hardware misbehaves, suspect the connection first.** Intermittent
   jumpers on header pins caused all-zero reads more than once. A constant-signal
   continuity check isolates it in seconds.

6. **One variable at a time.** This governs the propellant, the motor, and the
   electronics equally. Change the casing OR the propellant prep, never both, or
   you cannot attribute the result.

7. **Static-test / measure first; maximize performance later.** The first motor
   is an instrument to measure the real burn-rate coefficient, not a flight
   article. The DAQ is validated against a known thrust curve before it ever sees
   a real motor.

If a result seems important, the correct next action is almost always **another
measurement**, not a conclusion.

---

## What this project is

A ground-up experimental rocketry project spanning internal-ballistics
simulation, airframe optimization, propellant characterization, a custom
data-acquisition system, and an upstream contribution to OpenRocket. See
[README.md](README.md) for the full overview and results.

Current stage of the engineering arc **measure → estimate → control**: the
**measure** stage (the ESP32 DAQ) is essentially complete.

---

## Repository structure

```
simulation/internal-ballistics/   Python sweeps over openMotor's motorlib
simulation/flight/                OpenRocket driven headless via JPype
avionics/daq-fase1/               ESP32 firmware + Python capture/analysis
images/                           result figures
docs/                             engineering write-ups (01–05)
```

---

## Avionics development environment

PlatformIO Core lives in a venv (not global):
`~/rocketry-avionics/.pio-venv/`. The working project is
`~/rocketry-avionics/daq-fase1/`.

- **Board:** ESP32-WROOM-32 (`esp32dev`), Arduino-ESP32 core 2.0.17. It shows up
  as `/dev/ttyUSB0` (CP210x). The user is in the `dialout` group — no sudo.
- **Build:** `~/rocketry-avionics/.pio-venv/bin/pio run`
- **Flash:** `pio run -t upload --upload-port /dev/ttyUSB0`
- **Python analysis** (headless): `MPLBACKEND=Agg <venv>/bin/python <script>.py /dev/ttyUSB0`
- Firmware that does a one-shot capture should **repeat in a loop with a delay**,
  otherwise the PC misses the block (the ESP32 does not reliably reset on port
  open).
- **Shell gotcha:** `ls /dev/ttyUSB*` errors with "no matches" in zsh when the
  glob is empty — use `lsusb` or `ls /sys/class/tty` to check for the board.

---

## Hard-won technical facts

- **ESP32 DAC** (GPIO25/26, classic ESP32 only): output resistance ~20 Ω, sources
  up to ~12 mA but best kept under 1–2 mA; use an op-amp voltage-follower buffer
  for real loads. It is *not* a weak 3 kΩ source (an early wrong conclusion here).
- **ESP32 ADC** is nonlinear near the rails (~0.15 V error) and needs a source
  impedance below ~40 kΩ to read accurately; above that its readings are
  meaningless. Use `analogReadMilliVolts()` for the factory calibration.
- **Measuring amplitude vs. frequency by min/max requires enough samples per
  cycle**; undersampling silently underestimates high-frequency amplitude and
  fakes a low-pass rolloff. Prefer a **step-response / time-constant** method to
  measure RC, which is immune to this.
- **Electrolytic caps** are polarized (stripe = negative → ground) and leak (~µA),
  which matters when the series resistance is large (MΩ).

---

## Simulation environment

- **openMotor** (internal ballistics) and **OpenRocket** (flight, via JPype) are
  external tools the scripts drive. OpenRocket needs **JDK 17**; the headless
  core runs fine, only its GUI rejects newer JDKs.
- Motor `.eng` files are exported with an unmeasured hardware-mass placeholder —
  absolute apogee is an estimate until the real hardware is weighed; relative
  comparisons between designs are sound.
