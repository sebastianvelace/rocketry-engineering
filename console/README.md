# Rocketry Console

Local engineering workstation for ESP32 bench captures, wiring guidance,
openMotor grain sweeps, OpenRocket flight simulations and persistent run
comparison.

The application is intentionally local-first. Serial devices, the openMotor
environment and the OpenRocket JVM all run on the workstation.

## Product map

| Module | Job |
| --- | --- |
| Home | Shows hardware, simulation and archive readiness. Routes the operator to the next action. |
| Bench | Reads one complete ESP32 block, detects the measurement type, plots it and saves it. |
| Wiring | Guides preparation, pin-by-pin assembly and a pre-power inspection. |
| Motor | Runs a bounded BATES geometry sweep and exposes viable openMotor candidates. |
| Flight | Builds and flies a vehicle in OpenRocket from a motor curve and fin geometry. |
| History | Reopens, compares, exports and manages saved runs. |

## Setup

From `console/`:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

External simulation environments are expected at:

```text
~/openMotor/.venv/bin/python
~/openrocket/.venv/bin/python
```

The simulation source folders and `.eng` curves are resolved relative to the
repository, so the repository itself can be moved or cloned elsewhere.

## Run

```bash
.venv/bin/streamlit run app.py
```

Open `http://localhost:8501`.

Serial access on Linux may require membership in the group that owns
`/dev/ttyUSB*` or `/dev/ttyACM*` (commonly `dialout`).

## Verify

Run the complete local check:

```bash
bash tools/ci_check.sh
```

It compiles the Python sources, runs unit and Streamlit page smoke tests, then
checks the Git diff for whitespace errors.

Optional browser capture:

```bash
google-chrome --headless --no-sandbox --remote-debugging-port=9223 about:blank
.venv/bin/python tools/capture_ui.py http://127.0.0.1:8501 /tmp/console.png
```

## Data

Runs are stored in `runs.db`, which is intentionally ignored by Git. Each
record includes UTC creation time, type, metadata, column names, row data and
an operator note.

CSV export is available from History. Deletion is permanent and requires an
explicit confirmation in the interface.

## Engineering constraints

- Bench captures complete blocks, not a continuous kHz stream.
- Motor and Flight execute in isolated subprocesses to protect Streamlit from
  openMotor import assumptions and JVM lifecycle constraints.
- A viable simulated configuration is not a manufacturing, firing or launch
  authorization.
- Wiring diagrams are generated from `core/diagrams.py`; the numbered
  connection sequence is the physical assembly source of truth.

## Documentation

- [Technical audit](docs/technical-audit-2026-07-23.md)
- [Frontend and UX system](docs/frontend-redesign.md)
