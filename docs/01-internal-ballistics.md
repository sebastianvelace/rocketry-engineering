# 01 · Internal Ballistics — Motor Design

Motor design was driven by a **headless sweep** over openMotor's `motorlib`
(no GUI), so that thousands of grain geometries could be evaluated against the
real internal-ballistics model and its safety limits.

Code: [`simulation/internal-ballistics/`](../simulation/internal-ballistics/)

## The vehicle

- **Casing:** 1" (25.4 mm OD) 6061-T6 aluminium tube, 2.1 mm wall — a pressure
  vessel at chamber pressure.
- **Liner:** kraft/epoxy thermal barrier (sacrificial, non-structural).
- **Grain:** KNSB (65/35 KNO₃/sorbitol), BATES geometry (hollow cylinder).
- **Nozzle:** converging–diverging (graphite), designed for the chamber pressure.
- **Goal:** maximum total impulse in a minimum-diameter vehicle.

## Key finding: Kn alone is a false sense of safety

A first sweep produced **120 grain geometries all inside the "safe" Kn window
(200–280)**. When the four real limits from openMotor's own defaults were
applied simultaneously, **all 120 were unsafe**:

| Limit | Value | What the 120 configs did |
|---|---|---|
| Chamber pressure | ≤ 10.34 MPa | OK |
| Mass flux | ≤ 1406 kg/(m²·s) | **1800–3600** — violated |
| Core Mach | ≤ 0.7 | OK |
| Port/throat | ≥ 2.0 | **0.8–1.7** — violated |

Below port/throat = 2, the gas accelerates through the core fast enough to strip
propellant off the walls (**erosive burning**), spiking pressure beyond what Kn
predicts. **Kn, port/throat and mass flux must all hold at once.**

## The four viable configurations

After enforcing all limits (throat solved for peak Kn = 280):

| Config | Core | Segments | Impulse | Peak thrust | Burn | P/T | Class |
|--------|------|----------|---------|-------------|------|-----|-------|
| A | 12 mm | 5×50 mm | 92.2 N·s | 196 N | 0.50 s | 2.4 | G184 |
| B | 13 mm | 6×45 mm | 89.6 N·s | 213 N | 0.43 s | 2.6 | G206 |
| C | 11 mm | 4×55 mm | 88.6 N·s | 171 N | 0.56 s | 2.3 | G157 |
| D | 14 mm | 6×50 mm | 87.1 N·s | 246 N | 0.37 s | 2.6 | G235 |

## Burn-rate sensitivity — why the "best" motor isn't the one to build

The library burn-rate coefficient `a` is for uncatalysed KNSB. The real
propellant uses a 1 % Fe₂O₃ catalyst that raises `a` by an unknown amount.
A sensitivity sweep on config A (throat fixed) shows how close the margin is:

| `a` × library | Peak pressure | Mass flux (% of limit) |
|---|---|---|
| 1.00 | 3.32 MPa | 94 % |
| 1.07 | — | **100 % — limit crossed** |
| 1.50 | 6.73 MPa | 161 % |

**Config A tolerates only +7 % in burn rate before erosive burning.** A catalyst
plausibly exceeds that. So a lower-impulse **instrumentation motor (config E:
13 mm core, 4×55 mm)** was selected instead — it tolerates **+37 %** — with the
explicit purpose of *measuring* the real `a` before committing to a high-impulse
design. (Also corrected a common misconception: pressure scales *worse* than
linearly with `a`, because rising pressure crosses into a different burn-rate
regime.)

## Nozzle retention (not modelled by openMotor)

Axial blow-out force = chamber pressure × **tube-bore** area (21.2 mm, 353 mm²) —
*not* the grain OD; the liner carries no load.

| Case | Pressure | Axial force |
|---|---|---|
| Nominal | 3.32 MPa | 1172 N |
| `a`×1.5 | 6.73 MPa | 2376 N |
| Chamber rating | 10.34 MPa | 3650 N |

With FS 4 against the chamber rating: **5× M4 or 4× M5 grade-8.8 bolts.** The
failure mode flips from bolt shear (small bolts) to aluminium bearing (large
bolts) — past a point, more bolts help but thicker bolts don't, because the
2.1 mm wall governs.

## Scripts

| File | Purpose |
|---|---|
| `sweep_bates.py` | Grid sweep over core/segments/length with all four safety gates |
| `sensitivity_a.py` | Burn-rate `a` sensitivity with a fixed (machined) throat |
| `retention.py` | Nozzle/closure bolt sizing |
| `export_eng.py` | RASP `.eng` thrust-curve export |
| `save_motors.py` | Serialise configs as openMotor `.ric` files |
