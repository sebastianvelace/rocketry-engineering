# 03 · Propellant Characterization & Static-Test Post-Mortem

> **Scope note.** This section documents *methodology and failure analysis at an
> engineering level*. It intentionally contains **no synthesis procedure,
> quantities, or recipe.** The value here is the physics and the debugging, not
> the chemistry.

## Why a static test exists at all

The whole motor design rests on the propellant's burn-rate coefficient `a`. The
library value is for uncatalysed KNSB; the real mix uses a burn-rate catalyst
that shifts `a` by an unknown amount, and mixing/dispersion quality changes it
further. **No simulation can supply this number — it must be measured.**

The measurement is elegant and needs almost no instrumentation. In a BATES grain
the burn rate is simply the web thickness over the burn time:

```
r = web / t_burn
```

A 240 fps phone video of a confined static burn yields the burn time to ~1 %,
and since the burn-rate exponent `n ≈ 0` in this pressure band,
`a_real / a_library ≈ t_predicted / t_measured`. The first motor's job is to
*measure*, not to fly.

## The first test: what happened

A test article was burned. It produced copious smoke but **no thrust** — it did
not fly, which was expected for this article.

## Root-cause analysis

Three findings, in order of importance:

1. **No pressure vessel → no thrust.** The test article's motor was a
   3D-printed plastic (PLA) body. PLA softens at ~60 °C; combustion gas is
   ~1500 °C. The plastic cannot contain pressure — it vents, so no chamber
   pressure builds, the nozzle never chokes, and there is no thrust. The
   propellant burned as an unconfined flare, not a rocket motor. **This is
   exactly why the design specifies an aluminium casing and graphite nozzle.**

2. **Burn rate is pressure-dependent — open-air tests mislead.** From
   `r = a·Pⁿ`, a sugar propellant burns *much* faster confined at ~3 MPa than in
   open air at ~0.1 MPa. The "slow" burn observed unconfined says almost nothing
   about behaviour inside a real motor. Judging burn rate from an unconfined
   test is a category error.

3. **Preparation method mattered.** The propellant was made by an aqueous
   dissolve-and-dry route rather than the melt-cast method the design specifies.
   The aqueous route's weakness is water removal; incomplete drying leaves
   residual water that absorbs combustion heat and slows the burn — consistent
   with both the slow burn and the observed humidity sensitivity. Melt-casting
   never introduces water, which is the point.

## What actually worked (and matters)

- The propellant **ignited and sustained combustion** — the chemistry is sound.
- Flame temperature was clearly real (it melted a damp wooden board).
- The oxidizer, purified by **fractional recrystallization** (exploiting the
  steep KNO₃ solubility curve vs. a flat contaminant curve), was verified
  qualitatively by **flame test** (progressive reduction of sodium's yellow).

## Engineering lessons

- **The failing link was hardware, not chemistry.** A correct diagnosis points
  at the pressure vessel, not the propellant.
- **You cannot characterize a propellant unconfined.** The next test uses the
  aluminium motor so the burn happens under pressure.
- **Method discipline:** one variable at a time. The next motor changes the
  casing (aluminium) and the prep (melt-cast, dry) — and *then* measures `a`.

## Next step

Build the aluminium motor with the graphite nozzle, load a dry melt-cast grain,
and fire it confined on an instrumented stand (see
[04 · Avionics DAQ](04-avionics-daq.md)) to obtain the real thrust curve and
the measured burn-rate coefficient.
