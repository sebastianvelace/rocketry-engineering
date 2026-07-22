# 02 · Flight Simulation — Airframe Design & Optimization

The airframe was designed and optimized by driving **OpenRocket's core headless
through JPype** (Python → Java), so hundreds of airframe variants could be
simulated programmatically with no hand-built XML.

Code: [`simulation/flight/`](../simulation/flight/)

## Architecture decision: the motor tube *is* the airframe

Two architectures were compared on the same motor:

| Architecture | Diameter | Mass | Apogee |
|---|---|---|---|
| Motor inside a separate fibreglass body | 27.4 mm | 340 g | 1324 m |
| **Aluminium motor tube = airframe** | **25.4 mm** | **284 g** | **1503 m** |

Using the aluminium motor tube directly as the airframe removes an entire tube:
**+179 m and −56 g.** (A modelling trap was avoided here — the motor's hardware
mass already includes the aluminium tube, so it must not be double-counted when
the tube is also modelled as structure.)

## The dominant result: aerodynamics beats motor choice

A one-factor-at-a-time study (motor E baseline, 856 m) ranked every lever:

| Change | Δ apogee |
|---|---|
| **Fin cross-section square → airfoil** | **+212 m** |
| Fin cross-section → rounded | +181 m |
| **Polished finish** | **+108 m** |
| Thinner fins (2.4 → 1.6 mm) | +70 m |
| Nose shape (any) | ±5 m — **irrelevant** |
| Longer nose (200 mm) | **−16 m** |
| 4 fins instead of 3 | −72 m |

**At Mach 0.77 the drag is dominated by fin-edge pressure drag and skin friction,
not the nose.** A full constrained grid search lifted motor E from **856 m to
1403 m (+64 %)** — entirely from fins and finish, with stability held in the
1.5–2.5 calibre window.

The airframe optimization (+547 m) **dwarfs** the choice of motor (A vs E =
140 m). Conclusion: the safe instrumentation motor on a good airframe beats the
risky high-impulse motor on a poor one.

## Fin flutter (OpenRocket does not model this)

Checked separately (NACA TN-4197). The optimum fin thickness of 1.6 mm gives a
flutter margin of ~5×; going to 1.2 mm drops it to ~3.3×. The build was kept at
2.4 mm G10 — costing only ~15 m of apogee but doubling the flutter margin and
being far more robust to handle. **Fifteen metres is not worth a fin torn off in
flight.**

## Stability & wind

- Launch margin **1.95 cal**, burnout **2.39 cal** — inside the safe window.
- Rail-exit velocity ~40 m/s (well above the ~15 m/s floor for fin authority).
- Wind study: apogee is nearly wind-insensitive (1539 m at 0 m/s → 1517 m at
  12 m/s). Wind costs **drift**, not altitude — a recovery problem, not a
  performance one.

## Cross-validation

OpenRocket's motor loader independently read the exported `.eng` files and
reproduced the openMotor impulse figures exactly (E = 72.7 N·s), cross-checking
the two independent simulators against each other.

## Final design (`FINAL_primer_cohete.ork`)

| | |
|---|---|
| Apogee | ~1522 m |
| Max speed | 267 m/s (Mach 0.78) |
| Length / diameter | 470 mm / 25.4 mm |
| Fins | 3 × G10, airfoil, polished |
| Mass | 299 g |

> Caveat carried in the model: hardware mass is an unmeasured placeholder. The
> absolute apogee is an estimate until the real hardware is weighed; the
> *relative* comparisons between designs are sound.
