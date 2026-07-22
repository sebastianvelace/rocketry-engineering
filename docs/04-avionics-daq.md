# 04 · Avionics — Data-Acquisition System (Phase 1)

The static test needs an instrument: a data-acquisition (DAQ) system to record
the thrust and pressure curves. This is Phase 1 — building and *understanding*
the sampling chain on an ESP32 before any sensor is attached.

Code: [`avionics/daq-fase1/`](../avionics/daq-fase1/)

## The fundamental question of any DAQ

The world is analog and continuous; a microcontroller samples it in discrete
snapshots. **How often must you sample to not lose information?**

**Nyquist–Shannon theorem:** to faithfully capture a signal you must sample at
**more than twice** its highest frequency. Half the sampling rate is the
*Nyquist frequency*.

**Aliasing:** violate Nyquist and a fast signal masquerades as a slow one that
was never there. In a thrust/pressure DAQ, a real high-frequency oscillation
(e.g. an acoustic resonance) could appear as a gentle slow ripple — or vanish
entirely — leading you to design the next motor on a false reading.

## The demonstration

The ESP32 generates a known sine on its DAC (GPIO25), a single jumper feeds it
to the ADC (GPIO34), and it samples itself back. By choosing the signal and
sampling frequencies, the theorem is shown directly.

**Clean case — 50 Hz signal, 1000 Hz sampling (well under Nyquist = 500 Hz):**

![clean sampling](../images/daq/capture.png)

Ten clean cycles, ~20 samples each — a faithful capture.

**Aliasing case — 950 Hz signal, 1000 Hz sampling (above Nyquist):**

![aliasing](../images/daq/capture_alias.png)

The plot shows a ~50 Hz sine — a **ghost**. A 950 Hz signal sampled at 1000 Hz
aliases to |1000 − 950| = 50 Hz. **The two plots are nearly identical: from the
samples alone you cannot tell a real 50 Hz sine from an aliased 950 Hz one.**

## What was measured along the way

- **ADC nonlinearity:** a DAC value of 2.59 V read back as 2.44 V (~0.15 V
  error) — the ESP32 ADC is nonlinear near the rails. This is the concrete
  motivation for the external ADC planned in Phase 2.
- **A real hardware bug:** early captures read all-zero. Root cause was an
  intermittent jumper on the header pins — not code. A constant-DAC continuity
  test isolated it. *When bench hardware misbehaves, suspect the connection
  before the software.*

## Design notes

- Timing is deliberately "soft" (scheduled with `micros()`) for Phase 1, to keep
  the concept clear. Phase 2 replaces it with a **hardware-timer ISR + external
  ADC** for jitter-free multi-kHz sampling, and adds an **analog anti-aliasing
  low-pass filter before the ADC** — aliasing cannot be fixed in software; it
  must be removed before sampling.
- Only the classic ESP32 (WROOM/WROVER) has a DAC on GPIO25/26.

## Roadmap

```
Phase 1  sampling & aliasing (this)          ✅
Phase 2  timer ISR + external ADC + anti-aliasing filter
Phase 3  load cell (Wheatstone) → instrumentation amp → thrust curve
Phase 4  flight computer: IMU + barometer sensor fusion (Kalman)
```

## Files

| File | Purpose |
|---|---|
| `main.cpp` | ESP32 firmware: DAC sine generation + ADC sampling |
| `plot.py` | Reads one CSV block over serial, plots the capture |
| `platformio.ini` | Build config (board `esp32dev`, Arduino framework) |
