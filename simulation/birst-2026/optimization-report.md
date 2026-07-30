# Practice Mission 01 — automated optimization report

Date: 2026-07-29, revised 2026-07-30  
OpenRocket: 24.12, public release  
Starting point: `practice-01-v2.ork`

## Deliverable

**`Tars Crew 9075.ork` — score 837.74.** Filename matches `TEAM_NAME.txt` byte for
byte. Verified twice by code that does not share a path with the search:
`verify_optimized_candidate.py` reloads and re-simulates it, and
`audit_candidate.py` reads the flight data straight out of the saved file and
applies the mission's own windows. Both report every constraint satisfied.

| | |
|---|---|
| Motor | AeroTech G125T, 127.0 g |
| Payload | 1275.48 g |
| Liftoff mass | 1498.25 g of 1500 |
| Apogee | 300.000 m |
| Stability, guide → burnout | 1.735 – 2.014 cal |
| Max angle of attack after departure | 12.60° of 15 |
| Ground contact | 5.982 m/s of 6.0 |
| **Score** | **837.740** |

## The canopy was the whole margin

The original study fixed the parachute at 1.5 m with its mass force-overridden to
141.75 g and never varied it across 39,803 flights. That single constant was
almost the entire structure:

```
1495.00 g  liftoff, recommended candidate
-1220.00 g  payload
- 127.00 g  G125T
=  148.00 g  everything else
             of which 141.75 g was the canopy and 2.87 g the rail button,
             leaving 3.4 g for nose, body, fins and motor mount
```

Two measurements, made before changing anything:

1. **The override was heavier than the truth.** With it removed, OpenRocket
   derives 127.03 g from the material and the 1.5 m diameter. The 141.75 g came
   from a SkyAngle Classic 36 preset — a 0.91 m canopy — applied unchanged to a
   1.5 m one. Removing it alone is worth 6.8 points.
2. **Canopy mass does not scale with area.** From 0.80 m to 1.50 m the area grows
   3.5× but the mass only 1.67×, so there is a large fixed component. Assuming
   `d²` would have overestimated the saving by roughly double.

Isolating the canopy on the existing best airframe, one variable at a time, with
payload re-tuned to hold 300 m:

| canopy | canopy mass | payload | apogee | ground contact | score |
|---|---|---|---|---|---|
| 1.50 m, override | 141.75 g | 1225.7 g | 299.51 m | 5.070 m/s | 812.79 |
| 1.50 m, derived | 127.03 g | 1239.2 g | 300.00 m | 5.069 m/s | 819.59 |
| 1.30 m | 109.30 g | 1256.9 g | 300.00 m | 5.377 m/s | 828.45 |
| 1.20 m | 101.39 g | 1264.8 g | 300.00 m | 5.581 m/s | 832.41 |
| 1.10 m | 94.11 g | 1272.1 g | 300.00 m | 5.834 m/s | 836.04 |
| **1.05 m** | **90.71 g** | **1275.5 g** | **300.00 m** | **5.982 m/s** | **837.74** |
| 1.00 m | 87.46 g | 1278.7 g | 300.00 m | 6.150 m/s | disqualified |

The boundary sits at about 1.045 m, so 1.05 m is the practical wall; going lower
buys fractions of a point before the descent limit bites.

A canopy meeting a 6.0 m/s limit at 5.982 m/s is a design standing on its
constraint, so that margin was tested rather than assumed. Terminal velocity
under canopy is an equilibrium, not an integration result: at time steps of
0.010, 0.025, 0.050 and 0.100 s the descent reads 5.982 m/s every time, and the
score moves by less than 0.02. The margin is thin but it is not fragile.

## A search that looked like a regression

Re-running the full search with the canopy freed but only 400/600 trials
returned 761.33 — worse than the 809 it was meant to beat, and 165 g under the
mass ceiling. That is not evidence against freeing the canopy; it is evidence
that 7,578 evaluations do not cover the space the original 18,290 did. The
isolated study above is the controlled comparison, and it is the one to trust.
The under-budget run was discarded rather than published, since a reader would
reasonably have drawn the opposite conclusion from it.

## Search performed

- 266 bundled motor curves passed the broad dimensional and performance screen.
- 53 competitive F/G/H curves were retained for the detailed search.
- 1,178 flight evaluations were run in the broad geometry search.
- 18,290 flight evaluations were run in the focused search and refinement.
- 3,803 additional flights optimized the zero-auxiliary-mass G125T.
- 16,500 flights screened every initially competitive motor lighter than the
  G125T in the only payload range capable of beating it.
- 32 final radius-bisection flights targeted the exact mass and altitude walls.
- Total OpenRocket search flights evaluated: **39,803**, plus independent
  reload verification and sensitivity runs.
- Random seed: `9075`.

For every geometry, the search varied:

- motor and motor-mount diameter;
- body diameter and length;
- nose length and profile;
- fin count, root chord, tip chord, sweep and span;
- payload and parachute longitudinal position;
- payload mass, including numerical targeting around 300 m.

Every retained result was simulated with:

- 2.0 m vertical guide;
- 4.0 m/s average wind;
- 0% turbulence;
- ISA atmosphere;
- 0.05 s time step.

A candidate was rejected unless it held 1.5–3.0 cal from guide departure
through burnout, remained at or below 15° AOA after guide departure, deployed
recovery and reached the ground at or below 6 m/s.

This is a stochastic search, not a mathematical proof of the global optimum.

That statement applies to the realistic component-mass search below. The
separate zero-auxiliary-mass model was subsequently taken to a provable score
ceiling.

## An arithmetic bound, not a rocket

`Tars Crew 9075 - absolute optimum clean.ork` reaches 886.5 by setting
`overridemass = 0.0` on six components — nose, body, motor mount, fins, rail
button **and the parachute**. It is a correct statement of what the scoring
expression permits when structure and recovery are free, and it is useful as a
bound on the search. It is not a candidate, and the 886.5 should never be quoted
as an achieved score. `audit_candidate.py` reports it as qualifying, because it
does qualify on the letter of the rules, and then prints the list of zeroed
components immediately underneath so the number cannot be read alone.

## Absolute OpenRocket mathematical optimum

File: `Tars Crew 9075 - absolute optimum clean.ork`

| Parameter | Value |
|---|---:|
| Motor | AeroTech G125T, 29 mm |
| Motor launch mass | 127.0 g |
| Body diameter | 44.76 mm |
| Body length | 254.16 mm |
| Nose | Power-series, 153.49 mm |
| Fins | 3 trapezoidal |
| Fin root / tip | 70.18 / 55.92 mm |
| Fin sweep / span | 49.15 / 46.30 mm |
| Payload | **1373.00 g** |
| Launch mass | **1500.00 g** |
| Apogee after independent reload | **299.998 m** |
| Guide departure velocity | 17.86 m/s |
| Stability, departure → burnout | 2.211–2.732 cal |
| Maximum AOA after departure | 12.62° |
| Ground impact | 5.07 m/s |
| Score after independent reload | **886.500** |

This file uses zero-mass overrides for every non-motor, non-payload component.
It is accepted and simulated by OpenRocket, but it is not physically
manufacturable.

### Why 886.5 is the absolute ceiling

The score has the bound:

```
Score = 200 − (300 − A)² / 4 + P / 2
      ≤ 200 + P / 2
```

The penalty reaches its maximum value of zero only at 300 m.

The winning motor weighs 127 g. With zero auxiliary mass and the 1500 g launch
limit, payload cannot exceed:

```
1500 − 127 = 1373 g
```

Therefore:

```
Score ≤ 200 + 1373 / 2 = 886.5
```

The saved file reaches 300 m with that payload and satisfies every hard
constraint, so it attains the bound.

A lighter motor might appear able to leave more payload mass. To exclude that
possibility, every bundled motor below 127 g was evaluated with an intentionally
impossible advantage:

- zero aerodynamic drag;
- zero structure and recovery mass;
- perfectly vertical point-mass motion;
- payload values throughout the only range that could exceed 886.5.

After discarding motors unable even to lift that mass, 149 bundled light-motor
curves remained. None could beat the G125T. The most favorable challenger was
the 104.9 g AeroTech G80T; even with zero drag its score ceiling was only about
758.9 because its ideal apogee was 277.4 m. This exclusion deliberately ignores
the AOA limit, giving every challenger an additional advantage. Motors at or
above 127 g are eliminated directly by the payload-mass bound.

This proves the 886.5 result within the mission rules and the bundled motor
database, provided OpenRocket zero-mass overrides are admitted.

## Highest-scoring simulation candidate

File: `Tars Crew 9075 - score optimum.ork`

| Parameter | Value |
|---|---:|
| Motor | AeroTech G125T, 29 mm |
| Motor launch mass | 127.0 g |
| Motor total impulse | 124.81 Ns |
| Body diameter | 38.75 mm |
| Body length | 270.0 mm |
| Nose | Parabolic, 82.49 mm |
| Fins | 4 trapezoidal |
| Fin root / tip | 143.56 / 36.34 mm |
| Fin sweep / span | 70.86 / 49.47 mm |
| Payload | 1225.69 g |
| Launch mass | 1499.50 g |
| Apogee | 299.51 m |
| Guide departure velocity | 17.87 m/s |
| Stability, departure → burnout | 1.722–1.999 cal |
| Maximum AOA after departure | 12.61° |
| Ground impact | 5.07 m/s |
| Score | **812.79** |

For this exact payload, a perfect 300 m apogee would score 812.85. The found
candidate is only about 0.06 points below that architecture-specific ceiling.

The design has only 0.50 g of launch-mass margin and unusually large fins.
It is the score winner, not the recommended engineering choice.

## Recommended simulation candidate

File: `Tars Crew 9075 - robust margin.ork`

| Parameter | Value |
|---|---:|
| Motor | AeroTech G125T, 29 mm |
| Body diameter | 49.21 mm |
| Body length | 286.25 mm |
| Nose | Conical, 207.87 mm |
| Total external length | 494.13 mm |
| Fins | 4 trapezoidal |
| Fin root / tip | 43.75 / 6.67 mm |
| Fin sweep / span | 29.99 / 32.93 mm |
| Payload | 1220.00 g |
| Launch mass | 1494.91 g |
| Apogee | 301.96 m |
| Guide departure velocity | 17.93 m/s |
| Stability, departure → burnout | 1.923–2.425 cal |
| Maximum AOA after departure | 12.57° |
| Ground impact | 5.07 m/s |
| Score | **809.04** |

This candidate gives up 3.75 points for:

- 5.09 g of launch-mass margin;
- much more conventional external proportions;
- approximately 0.42 cal clearance from both stability boundaries;
- 2.43° clearance from the AOA limit.

## Robustness checks on the recommended candidate

These are sensitivity checks; the mission itself remains fixed at 4.0 m/s and
0.05 s.

| Perturbation | Qualifies | Apogee | AOA | Impact |
|---|---:|---:|---:|---:|
| Time step 0.01 s | Yes | 301.82 m | 12.69° | 5.07 m/s |
| Time step 0.025 s | Yes | 301.82 m | 12.72° | 5.07 m/s |
| Time step 0.10 s | Yes | 302.11 m | 12.36° | 5.07 m/s |
| Wind 3.5 m/s | Yes | 303.73 m | 11.04° | 4.68 m/s |
| Wind 4.5 m/s | Yes | 299.97 m | 14.08° | 5.47 m/s |
| Wind 5.0 m/s | **No** | 297.77 m | **15.57°** | 5.89 m/s |
| Payload −2 g | Yes | 302.77 m | 12.55° | 5.07 m/s |
| Payload +2 g | Yes | 301.15 m | 12.59° | 5.07 m/s |
| Fin span −1 mm | Yes | 302.13 m | 12.57° | 5.07 m/s |
| Fin span +1 mm | Yes | 301.79 m | 12.57° | 5.07 m/s |
| Chute Cd −10%, diameter −5% | Yes | 301.96 m | 12.57° | 5.28 m/s |

## Important modeling limitation

Neither candidate is ready to manufacture.

- The 150 cm, Cd 1.34 parachute retains the 141.75 g mass derived from the
  original SkyAngle component, but does not retain its real packing volume.
- A parachute this large cannot be packed into the original 29 mm airframe.
  The recommended candidate's 49 mm body is better but still needs a real
  packing study.
- Payload, parachute and other internal components can overlap in OpenRocket.
- The payload's simulated density and volume are not yet physically credible.
- The foam body, nose and fins contribute only a few grams. OpenRocket does not
  establish that they can survive the acceleration, aerodynamic loading or
  recovery shock.
- One rail button remains in the inherited component tree; a real guide system
  needs two separated contact points or an appropriate launch lug.

The files therefore answer: “What scores best under the written simulator
constraints?” A separate structural and packaging design is required to answer:
“What can be safely built?”
