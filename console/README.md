# Rocketry Console

Local Streamlit dashboard that centralizes the ESP32 bench captures and (as
more pages are built) the openMotor and OpenRocket simulations, with a
persistent SQLite history so runs can be compared across sessions.

Design rationale, architecture, and the rebanada-by-rebanada plan are in
[`/home/sebasvelace/.claude/plans/solo-yo-busca-la-robust-bentley.md`](../CLAUDE.md).

## Setup (one time)

```
cd console
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run

```
console/.venv/bin/streamlit run console/app.py
```

Opens at `http://localhost:8501`. This only runs locally — it reads the ESP32's
serial port directly, which is not possible from a hosted web app.

## Pages

- **Bench** — capture a block from the ESP32, auto-detect its kind (sine,
  FFT, jitter, RC step, ADC calibration, Bode sweep, thrust replay), plot it,
  save it.
- **Wiring** — reproducible schematics (schemdraw) + explicit pin-to-pin
  tables for the bench circuits.
- **Motor** — BATES grain sweep in openMotor, run as a subprocess in its own
  venv (`motorlib` is an unpackaged source tree that only imports with
  `cwd=~/openMotor`).
- **Flight** — fly a design in OpenRocket, also a subprocess (its own venv,
  isolates the JVM to one process per simulation).
- **History** — every saved run, filterable by kind; reopen one to re-plot
  it, overlay several of the same kind to compare, export CSV, delete.

## Status

All 5 rebanadas of the original plan are complete and verified against real
hardware/data (not just synthetic tests) — see
[`~/.claude/plans/solo-yo-busca-la-robust-bentley.md`](../../.claude/plans/solo-yo-busca-la-robust-bentley.md)
for the full verification log, including two real bugs caught and fixed along
the way (a `sys.path` issue in the openMotor subprocess, and a motor-mass
double-count in the OpenRocket 'mindia' architecture).

## Notes

- `console/.venv/` and `console/runs.db` are gitignored (local environment and
  local data, not portfolio artifacts).
- The plot math mirrors the standalone scripts in `avionics/daq-fase1/`
  exactly — this app does not reimplement the analysis, it re-renders it.
  Same principle for Motor/Flight: the subprocess runners import and call the
  existing `sweep_bates.py` / `architecture.py` functions unmodified.
- Known limits: local-only (serial + JVM access require it), no live streaming
  at kHz rates (Streamlit's rerun model doesn't fit that; the DAQ's block-based
  capture does), no embedded OpenRocket GUI, no 3D rocket view.
