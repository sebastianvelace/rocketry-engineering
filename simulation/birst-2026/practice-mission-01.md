# Practice Mission 01 — "Calibration Band"

A self-imposed rehearsal for BIRST 2026. Written to the same shape as a real
Secret Mission: a contextualised scenario, hard constraints that disqualify, and
a scoring expression combining a squared penalty with a linear reward.

**This is not an official BIRST document.** It is a training exercise.

---

## Scenario

An atmospheric research group needs to characterise a thin layer of particulate
that forms over a valley at a specific altitude. Their sensor package integrates
its reading over a **narrow calibration band**, and returns useless data if the
apogee falls outside it — too low and it never enters the layer, too high and the
sensor saturates on the way through.

They also want to fly **as much instrumentation as the airframe will carry**: every
extra gram of payload is another channel of data.

You are asked to design the vehicle.

---

## Launch conditions — fixed, do not change

| Parameter | Value |
|---|---|
| Launch guide length | **2.0 m** |
| Wind speed | **4.0 m/s** |
| Wind turbulence intensity | **0 %** |
| Launch rod angle | 0° (vertical) |
| Atmosphere | ISA |
| Time step | 0.05 s |

---

## Hard constraints — violating any of these is a disqualification

These are the **critical elements**. Check every one before submitting.

1. **Single stage, single motor**, taken from OpenRocket's bundled motor database.
2. **Payload mass ≥ 60 g**, modelled as a distinct mass component.
3. **Total liftoff mass ≤ 1500 g.**
4. **Stability margin between 1.5 and 3.0 calibers**, held from launch-guide
   departure through to burnout — not merely at rest on the pad.
5. **Maximum angle of attack ≤ 15°** at any point after guide departure.
6. **A recovery device must deploy**, and the descent rate at ground contact must
   be **≤ 6 m/s**.

Constraint 5 is not arbitrary. OpenRocket's aerodynamic model has a stall angle of
17.5°; above it the coefficients it reports are outside their validity envelope.
A design that spends time past that angle is being optimised against numbers the
simulator does not stand behind.

---

## Scoring

Let **A** = apogee in metres, **P** = payload mass in grams.

```
Score = 200 − (300 − A)² / 4 + P / 2
```

Qualification requires every hard constraint above to hold. Any violation scores
nothing at all.

### Reading the formula before designing

Do this before opening OpenRocket — it is the habit the real exam rewards.

- **The target is 300 m and it dominates.** Missing by 10 m costs 25 points;
  missing by 20 m costs 100. The penalty is quadratic, so error grows faster than
  it feels.
- **Payload is the reward, at 0.5 points per gram.** 100 g of payload is worth
  50 points — equivalent to being 14 m off target.
- **They fight each other.** Every gram of payload lowers the apogee. The whole
  exercise is finding how much instrumentation the airframe can carry *while still
  landing on 300 m*, recovering the lost altitude through drag and efficiency
  rather than by shedding payload.

The naive strategy — minimum payload, easy target — scores about 230. The good
strategy carries several times that payload and still hits the band.

---

## Deliverable

A single `.ork`, named exactly:

```
Tars Crew 9075.ork
```

Copy the name from [`TEAM_NAME.txt`](TEAM_NAME.txt). Do not type it.

Alongside it, record:

| Field | Value |
|---|---|
| Apogee (m) | |
| Payload mass (g) | |
| Total liftoff mass (g) | |
| Min / max stability margin, guide departure → burnout (cal) | |
| Max angle of attack after departure (°) | |
| Descent rate at ground contact (m/s) | |
| **Computed score** | |

---

## Run it against the clock

Compress the seven days into one working day, keeping the same order. The point of
the rehearsal is the *sequence*, not the design.

| Phase | Budget | What happens |
|---|---|---|
| **1 · Read** | 30 min | Extract the critical elements into a checklist. Do not design. |
| **2 · Analyse the formula** | 30 min | Where is the penalty, where is the reward, where is the hard wall? Decide what to optimise and what merely to satisfy. |
| **3 · First feasible design** | 90 min | Something that qualifies, however badly. A qualifying design beats an elegant disqualified one. |
| **4 · Optimise** | 3 h | Trade payload against apogee. Sweep, do not guess. |
| **5 · Verify** | 60 min | Every critical element against the checklist, one at a time. |
| **6 · Submit** | 15 min | Filename check, character by character. |

**Log where the time actually goes.** The purpose of this rehearsal is to find out
what will eat exam week — almost certainly phases 1 and 5, which feel like
overhead right up until they are the reason you place.

---

## Traps deliberately planted

1. **Stability is a curve, not a number.** Constraint 4 asks for a range held
   across a window. The margin shown in the design view is the value at rest;
   propellant burns off and the CG moves forward, so the in-flight margin differs.
   Plot it against time.

2. **4 m/s of crosswind on a 2 m guide is not free.** The angle of attack at
   departure is roughly `atan(wind / rail_exit_velocity)`. A sluggish design leaves
   the guide slowly, and that angle can breach constraint 5 on its own — or, in
   OpenRocket 24.12, trigger a spurious `TUMBLE_UNDER_THRUST` abort. Check the
   rail exit velocity early; it is a ten-second calculation that governs the design.

3. **The recovery constraint is easy to forget** until it costs the qualification.

---

## Calibration note

The 300 m target and the payload weighting are set by hand and have not been
solved for. If first contact shows the band is unreachable with any sensible motor
from the bundled database, that is information: record the reachable range and
adjust the target, exactly as an organiser would when setting a mission.

Do not adjust it merely because it is hard.
