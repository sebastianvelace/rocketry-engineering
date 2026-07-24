# Rocketry Console

Local engineering workstation for ESP32 bench captures, wiring guidance,
openMotor grain sweeps, OpenRocket flight simulations and persistent run
comparison.

The application is intentionally local-first. Serial devices, the openMotor
environment and the OpenRocket JVM all run on the workstation.

UI-independent engineering operations live in `core/services.py`. Streamlit,
the desktop application, the local gateway and both agent providers call the
same contracts.

## Product map

| Module | Job |
| --- | --- |
| Home | Shows hardware, simulation and archive readiness. Routes the operator to the next action. |
| Bench | Reads one complete ESP32 block, detects the measurement type, plots it and saves it. |
| Wiring | Guides preparation, pin-by-pin assembly and a pre-power inspection. |
| Motor | Runs a bounded BATES geometry sweep and exposes viable openMotor candidates. |
| Flight | Builds and flies a vehicle in OpenRocket from a motor curve and fin geometry. |
| History | Reopens, compares, exports and manages saved runs. |
| Agent | Runs durable Codex or Claude Code sessions, streams their work and exposes approvals without a browser shell. |

Use the compact `ES / EN` switch in the global rail to change the complete
console between English and Spanish. The preference persists across views and
application restarts.

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

### Desktop workstation

Install the web dependencies once:

```bash
cd desktop
pnpm install
```

Start the Linux desktop client:

```bash
pnpm tauri dev
```

The application starts its own authenticated gateway on a random localhost
port. It does not require an API key. Codex uses the existing ChatGPT login and
Claude Agent SDK uses the existing Claude Code subscription login.

The desktop client provides:

- a provider selector for independent Codex and Claude sessions;
- native Bench, Wiring, Motor, Flight and History work surfaces;
- durable conversation and activity history in `.rocketry/gateway.db`;
- explicit conversation deletion with confirmation, provider shutdown and
  cascading cleanup of its events and approvals;
- WebSocket streaming without periodic page polling;
- inline permission approval and interruption;
- the same saved runs whether an operation starts manually or through an agent;
- provider-aware command discovery by typing `/` in the composer;
- a native `/model` selector backed by the current Claude Code or Codex
  catalog, with the choice remembered per session;
- native session commands for status, usage, rename, clear and the provider
  operations that its installed protocol actually exposes;
- a Usage surface with real Claude subscription windows, real Codex account
  rate limits and clearly separated workstation-local token totals;
- GitHub-flavored Markdown rendering for agent messages;
- an explicitly visible full-repository workspace boundary;
- a resizable global navigation rail and consistently dark native controls;
- provider prewarming without consuming a model turn;
- startup recovery that waits for a real gateway health response and retries
  transient initial loads before declaring the session store unavailable;
- lower-noise Claude permissions: Rocketry's bounded local MCP is preapproved,
  edits use `acceptEdits`, and a narrow set of read/verification Bash commands
  is allowed while installs, publishing and arbitrary shell remain gated;
- live engineering plots, run comparison, CSV export and persistent artifacts;
- a bilingual English/Spanish interface saved in local preferences;
- a single chronological conversation timeline — thinking, tool calls,
  subagent activity and plan updates render inline next to the reply that
  produced them, the same narrative a terminal session shows, instead of a
  separate activity tab; and
- a secondary raw event log for troubleshooting, once activity moved into
  the conversation itself.

Claude is intentionally started with the Rocketry MCP only. Built-in Claude
Code tools and project commands remain available, while unrelated account
connectors are excluded from this process. This keeps initial connection
latency bounded and avoids waiting on remote MCP servers that are irrelevant
to the workstation.

Build the Linux executable without packaging:

```bash
pnpm tauri build --debug --no-bundle
```

The development executable is written to
`desktop/src-tauri/target/debug/rocketry-workstation`.

### Streamlit console

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
cd desktop && pnpm test && pnpm build && pnpm test:e2e
cd desktop/src-tauri && cargo check
```

The browser E2E suite uses the installed Google Chrome build and a deterministic
mock gateway. It does not consume Claude or Codex quota. Live provider probes
remain explicit opt-in checks.

It compiles the Python sources, runs unit and Streamlit page smoke tests, then
checks the Git diff for whitespace errors.

Optional browser capture:

```bash
google-chrome --headless --no-sandbox --remote-debugging-port=9223 about:blank
.venv/bin/python tools/capture_ui.py http://127.0.0.1:8501 /tmp/console.png
```

## Legacy Streamlit activity bridge

Run the agent in your terminal through the relay and keep the Agent page open
beside it:

```bash
python console/tools/agent_relay.py --provider codex "Run the console checks"
python console/tools/agent_relay.py --provider claude "Run the console checks"
```

The relay preserves terminal output and mirrors normalized events into a
bounded, ignored JSONL file. Only the Agent page polls it, using a two-second
Streamlit fragment; the simulation and measurement pages do not rerun. The
browser cannot execute commands or approve agent actions.

This remains as a compatibility path. The desktop workstation is the primary
interactive agent interface and uses durable WebSocket events instead.

### Provider feasibility probes

Inspect the installed providers, subscription authentication and the local
Codex app-server handshake without submitting a prompt:

```bash
.venv/bin/python tools/provider_probe.py
```

Minimal live probes are deliberately separate because they consume provider
quota and create resumable test sessions:

```bash
.venv/bin/python tools/provider_live_probe.py \
  --provider codex --allow-token-use

.venv/bin/python tools/provider_live_probe.py \
  --provider claude --allow-token-use --persistent
```

They disable Claude tools and use a read-only Codex thread. They are not run by
CI. See the [desktop agent workstation plan](docs/agent-workstation-plan.md)
for verified capabilities, remaining risks and implementation phases.

### Shared Rocketry MCP

Both local agents can call the same engineering tools through
`rocketry_mcp.py`. The server uses stdio, never opens a network listener, and
does not expose ignition or arbitrary shell execution.

Register it from the repository root if the local provider configuration is
ever reset:

```bash
codex mcp add rocketry -- \
  "$PWD/console/.venv/bin/python" "$PWD/console/rocketry_mcp.py"

claude mcp add --transport stdio --scope local rocketry -- \
  "$PWD/console/.venv/bin/python" "$PWD/console/rocketry_mcp.py"
```

`capture_bench`, `run_motor_sweep` and `run_flight` save a normal History run.
Comparisons, CSV exports and test logs are stored under the ignored
`console/.rocketry/artifacts/` directory. File locks prevent separate Codex
and Claude MCP processes from using the same serial or simulator operation at
the same time.

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
- Wiring diagrams are generated from `core/diagrams.py`; bilingual preparation
  and verification guidance lives in `core/wiring_guides.py`. The numbered
  connection sequence remains the physical assembly source of truth.
- The desktop gateway uses Codex app-server and the official Claude Agent SDK.
  Both transports render approvals explicitly instead of bypassing them.
- Provider usage is cached for 60 seconds. Manual refresh reads Claude Code's
  `/usage` output and Codex app-server's account usage/rate-limit endpoints;
  it never estimates an account limit from local tokens.

## Documentation

- [Technical audit](docs/technical-audit-2026-07-23.md)
- [Frontend and UX system](docs/frontend-redesign.md)
- [Desktop agent workstation plan](docs/agent-workstation-plan.md)
- [Desktop workstation implementation](docs/desktop-workstation.md)
