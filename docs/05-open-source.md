# 05 · Open-Source Contribution — OpenRocket

While using OpenRocket to design the airframe, a reproducible bug surfaced: a
**stable rocket would randomly abort** its simulation at launch-rod clearance in
wind, reporting a ~1 m apogee. Chasing it to the bottom took three iterations of
diagnosis, produced a second and unrelated bug along the way, and ended in two
independent upstream contributions.

| | Upstream | Status |
|---|---|---|
| Random seed never reached the wind models | [issue #3188](https://github.com/openrocket/openrocket/issues/3188) → [PR #3189](https://github.com/openrocket/openrocket/pull/3189) | **merged** 29 Jul 2026 (`9d59e430`) |
| Spurious tumble abort | [issue #3183](https://github.com/openrocket/openrocket/issues/3183) → [PR #3190](https://github.com/openrocket/openrocket/pull/3190) | open, under review |
| First attempt at #3183 | [PR #3186](https://github.com/openrocket/openrocket/pull/3186) | superseded — see below |

The seed fix is now in OpenRocket's `unstable` branch. It also produced a
maintainer-opened follow-up, [#3191](https://github.com/openrocket/openrocket/issues/3191)
— exposing the seed in the UI so users can fix it for parameter sweeps, which the
fix makes meaningful for the first time.

Reproduction file: [`simulation/flight/tumble_abort_repro.ork`](../simulation/flight/tumble_abort_repro.ork)

---

## The bug

A stable rocket (1.9 cal margin) in the default 10 % turbulence **randomly**
aborted with `TUMBLE_UNDER_THRUST` on the first time steps after leaving the rod.
Identical settings gave a full flight on one run and ~1 m on the next.

## Root cause

The reported symptom pointed at gusts. **It was not about gusts** — that was only
what made the failure intermittent enough to look like one. A *steady* 6 m/s
crosswind, with no gust and no turbulence anywhere in the scenario, aborted every
single run.

The tumble test combined two things, and both are unsound:

1. An **instantaneous** angle of attack above the stall angle. The angle is
   measured against the apparent airflow, so a single integration step can carry
   it across the threshold without the rocket's state having changed.
2. A `cg > cp` stability comparison — and this is the half that mattered. Above
   the stall angle the aerodynamic model is **outside its validity envelope**,
   which is exactly the regime where the comparison was evaluated. The test drew
   its conclusion from a quantity it had itself declared unreliable.

At rod clearance the angle of attack is geometrically forced to
`atan(wind / rail_exit_velocity)`. A short rod and a crosswind put that past the
stall angle on their own — no gust required — and the CP comparison did the rest.

## The first attempt, and why it was abandoned

[PR #3186](https://github.com/openrocket/openrocket/pull/3186) gated the tumble
emission on the same `recordWarnings()` window that already suppressed the
sibling warning. It removed the spurious aborts, but it was the *smallest* fix,
not the *right* one — and it carried a side effect that was flagged in the PR
rather than hidden: `recordWarnings()` also returns false during descent, which
would suppress tumble detection for no-parachute tumble-recovery rockets exactly
when they need it.

The maintainer agreed, and proposed waiting for real kinematic evidence of a
tumble instead of gating on a time window. That became the current design.

## The fix that shipped

[PR #3190](https://github.com/openrocket/openrocket/pull/3190) decides tumbling
from **how long a high angle of attack has persisted**, measured against the
rocket's own pitch natural frequency, rather than from its value at one instant.

A stable rocket recovers within about a pitch period; a tumbling one never does.
Because the time constant is taken from the airframe's own dynamics, the wait
scales with the rocket instead of being a constant tuned to one design. No
aerodynamic coefficient enters the decision, and no flight-phase gating is needed
in either direction: the guide-departure transient does not survive the filter,
and descent tumbling does.

### An idea that was measured and rejected

The maintainer's first suggestion was to compare the rocket's orientation to its
trajectory. Building it showed it cannot work: **a stable rocket aligns itself
with the air, not with the ground.** In a crosswind those are different
directions, so a perfectly healthy rocket is already "crooked" relative to its
ground track — worst at low speed right after departure, which is precisely where
the detector must not fire. Instrumented on an Alpha III at 6 m/s there were
moments of sub-stall angle of attack while the ground-track angle read nearly 90°,
and moments of 84° angle of attack while the ground-track angle read under 30°.

The control that made this credible rather than merely asserted: **with the wind
switched off, the two angles agree exactly.** All of the disagreement was wind.

---

## Validation

Estes Alpha III, 1 m guide, wind supplied by a listener rather than the pink
noise model and the integrator's seed pinned — nothing random anywhere, so every
row is reproducible exactly.

**Steady crosswind, no gust:**

| wind | before | after |
|---|---|---|
| 0 m/s | 133.1 m | 133.1 m |
| 2 m/s | 132.2 m | 132.2 m |
| 4 m/s | 130.7 m | 130.7 m |
| 6 m/s | **abort, 1.1 m** | **132.0 m** |
| 8 m/s | abort, 1.1 m | abort, 5.5 m |

The first three rows are numerically identical before and after: flights that
already worked are untouched.

**A 0.1 s, +6 m/s gust swept across the whole departure window, 12 positions:**

| steady wind | aborts before | aborts after |
|---|---|---|
| 0 m/s | 2/12 | **0/12** |
| 2 m/s | 3/12 | **0/12** |
| 4 m/s | 3/12 | 3/12 |
| 6 m/s | **12/12** | 4/12 |

**The rows where aborts remain are correct detections.** A 1 m guide is short:
this airframe leaves it at about 10 m/s, so a 6 m/s crosswind gives roughly 32°
of angle of attack at departure, past stall, with the fins unable to generate a
restoring moment. Tracing one, the angle climbs monotonically from 27° to 94°
without recovering while vertical velocity falls under thrust, and OpenRocket's
own `TYPE_NATURAL_FREQUENCY` reads `NaN` throughout — the simulator stating that
the rocket has no static stability. Those rockets really do flip over.

Regression guard: a finless airframe is genuinely unstable and is still detected.
Core suite green at 1231 tests.

> **Superseded numbers.** An earlier version of this page reported 8 / 38 / 75 /
> 88 % spurious aborts falling to 0 %, measured on the repro rocket over 24 random
> seeds. Those numbers were taken on the abandoned #3186 design *and* before the
> seed bug below was known — which means they were not reproducible run to run and
> should not be cited. They are replaced by the deterministic tables above.

---

## The second bug, found by accident

Building deterministic experiments for the above exposed something else: identical
sweeps returned different numbers on consecutive runs.

`SimulationOptions.randomSeed` exists so a simulation can be repeated exactly. It
reached the integrator — both Runge-Kutta steppers build their `Random` from it —
but **never reached the wind models**. Two distinct failures:

- `PinkNoiseWindModel` received the seed once, in the `SimulationOptions`
  constructor, and its seed field was `final`. `setRandomSeed` could not change it.
- Every level of `MultiLevelPinkNoiseWindModel` was built with the no-argument
  constructor, so it was **never connected to the seed at all** — not in the
  constructor, not anywhere.

Measured on `unstable`, same seed, 24 runs: apogee ranged from **1.05 m to 131.3 m**,
and the count of runs finishing below 100 m came out as 18, 14, 17 and 17 across
four repetitions of the sweep. Not only was a flight not reproducible from its
seed — the measured failure rate was not reproducible either.

[PR #3189](https://github.com/openrocket/openrocket/pull/3189) seeds the throwaway
wind-model clone that is already built once per run, rather than the configured
models. That leaves `equals()`/`hashCode()` and the "simulation is outdated" logic
untouched, so no stored result is invalidated.

### Why this matters beyond OpenRocket

Any measurement taken from a single turbulent run was unreliable, and any sweep
repeated on the same seed disagreed with itself. **That invalidates numbers, not
just convenience** — including the earlier validation table on this page. It is the
reason the tables above use a written-down wind field instead of the built-in model.

---

## Engineering practice demonstrated

- Root-cause diagnosis to specific source lines, then **past** the first plausible
  cause to the real one: the reported gust sensitivity was a symptom, and a steady
  wind reproduced the fault deterministically.
- **A null control on every claim.** Zero wind proved the ground-track discrepancy
  was physical rather than an instrumentation bug; zero turbulence proved a
  residual test flakiness came from the integrator, not the wind.
- **Repeating every measurement.** A rate measured once is not a rate — the same
  24-run sweep gave four different answers, and that instability was itself the
  finding.
- **Mutation-testing new assertions.** A test asserting "different seeds give
  different flights" still passed when the wind model was mutated to ignore its
  seed, because the integrator also draws on that seed. The test was measuring the
  wrong thing; it was replaced with one that samples the models directly.
- **Surfacing side effects rather than hiding them**, twice: the descent tradeoff
  in #3186, and the deliberate scope boundary in #3188 (the seed is still not
  persisted to `.ork`, which is a feature, not this bug fix).
- **Correcting the public record.** A reviewer showed the wording of #3188
  overstated the fault; the issue was edited and the correction posted rather than
  left standing.
