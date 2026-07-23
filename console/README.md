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

## Status

- ✅ **Rebanada 1 — core + Bench page.** `core/blocks.py` (generic serial block
  reader, replaces the 7 duplicated parsers in `avionics/daq-fase1/`),
  `core/store.py` (SQLite run history), `core/plots.py` (Plotly renderer for
  each of the 6 block kinds: sine/aliasing, FFT, timing jitter, RC step
  response, ADC calibration, Bode sweep, thrust replay), `pages/1_Bench.py`
  (capture, auto-detect, plot, save).
- ⬜ Rebanada 2 — wiring diagrams (schemdraw).
- ⬜ Rebanada 3 — motor sweep panel (openMotor, subprocess adapter).
- ⬜ Rebanada 4 — flight sim panel (OpenRocket, subprocess adapter).
- ⬜ Rebanada 5 — cross-run history and comparison view.

## Notes

- `console/.venv/` and `console/runs.db` are gitignored (local environment and
  local data, not portfolio artifacts).
- The plot math mirrors the standalone scripts in `avionics/daq-fase1/`
  exactly — this app does not reimplement the analysis, it re-renders it.
