# 05 · Open-Source Contribution — OpenRocket

While using OpenRocket to design the airframe, a reproducible bug surfaced: a
**stable rocket would randomly abort** its simulation at launch-rod clearance in
wind, reporting a ~1 m apogee. This became a full diagnosis → fix → validation →
upstream contribution.

- **Issue:** [openrocket/openrocket#3183](https://github.com/openrocket/openrocket/issues/3183)
- **Pull request:** #3186
- Reproduction file: [`simulation/flight/tumble_abort_repro.ork`](../simulation/flight/tumble_abort_repro.ork)

## The bug

A stable rocket (1.9 cal margin) in the default 10 % turbulence **randomly**
aborted with `TUMBLE_UNDER_THRUST` on the first time step after leaving the rod.
Identical settings gave a full ~590 m flight on one run and ~1 m on the next —
non-reproducible results driven only by the turbulence seed.

## Root cause (found in the source)

At rod clearance the angle of attack is geometrically forced to
`atan(wind / rail_exit_velocity)`. During that transient the body-lift CP
correction can momentarily move CP ahead of CG; a single turbulence gust pushing
the instantaneous AOA past the fixed 17.5° stall angle emits a `TUMBLE` event,
and under thrust that becomes an unrecoverable abort. The sibling low-AOA warning
was already gated on a 0.25 s post-rod window (`recordWarnings()`) — **the tumble
emission was not.**

## The fix

Gate the tumble emission on the same `recordWarnings()` check, so the
geometrically unavoidable rod-exit transient no longer aborts the flight —
consistent with how the neighbouring warning is already handled.

## Statistical validation (before vs after)

Reproduction rocket, 24 random seeds per wind speed, 10 % turbulence, built from
source and measured:

| wind | spurious aborts (before) | spurious aborts (after) |
|---|---|---|
| 8 m/s | 8 % | **0 %** |
| 9 m/s | 38 % | **0 %** |
| 10 m/s | 75 % | **0 %** |
| 11 m/s | 88 % | **0 %** |

Regression guard: a genuinely unstable (finless) rocket is still detected as
tumbling in **100 %** of runs both before and after — the fix removes only the
spurious aborts, not real tumble detection. Apogee of already-successful flights
is numerically unchanged, and the existing 63-test core suite passes.

## Engineering practice demonstrated

- Root-cause diagnosis down to specific source lines, not just symptom reporting.
- A two-click reproduction case attached to the issue.
- A **quantified before/after** validation built from source — the evidence that
  makes a fix mergeable.
- An honest **scope note** in the PR: reusing `recordWarnings()` also suppresses
  tumble detection during descent for no-parachute tumble-recovery rockets;
  the tradeoff and a surgical alternative were laid out for the maintainers to
  choose. Contributing means surfacing the side effects, not hiding them.
