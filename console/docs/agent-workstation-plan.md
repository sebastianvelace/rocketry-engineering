# Agent workstation implementation plan

Date: 2026-07-23

## Product decision

Build a personal, Linux-only desktop workstation that:

- launches the locally authenticated Codex and Claude Code installations;
- creates separate conversations for each provider;
- streams visible agent messages, tool activity, tests, diffs and approvals;
- lets both providers call the same Rocketry engineering operations;
- renders Bench, Motor and Flight artifacts beside the conversation;
- isolates concurrent modifying sessions with Git worktrees; and
- keeps Streamlit available until the desktop client reaches feature parity.

The workstation does not combine provider context. A handoff creates a new
session with an explicit, editable context package.

Remote Rocketry operation, multi-user access, Cursor and ignition controls are
outside the first release. Cross-computer conversation continuity requires an
explicit shared session store or a private authenticated relay. The Rocketry
UI and ESP32 remain local by default.

## Architecture

```text
Tauri / React desktop
        |
        | authenticated localhost WebSocket
        v
Python agent gateway
  |                 |
  | stdio JSONL     | stdio JSONL
  v                 v
Codex app-server    Claude Agent SDK
        \           /
         \         /
          Rocketry MCP
                |
    engineering services and runs.db
```

Provider-specific payloads remain available under a raw event field. The UI
uses a normalized envelope for common behavior, but it must not pretend that
permissions or session semantics are identical.

## Phase 0: feasibility evidence

The probes were executed against:

- Codex CLI `0.145.0`;
- Claude Code `2.1.218`;
- Python `3.12.3`;
- Node `24.14.1`; and
- Rust/Cargo `1.94.1`.

No account email, organization identifier, token or credential is persisted by
the harness.

### Authentication

`tools/provider_probe.py` verified without submitting a prompt:

| Provider | Authentication | Result |
| --- | --- | --- |
| Codex | ChatGPT account | Pass |
| Claude | claude.ai Pro subscription | Pass |

The Codex app-server `account/read` response reported a ChatGPT account rather
than API-key authentication. Claude `auth status` reported `claude.ai`,
`firstParty` and `pro`. Identity fields are removed before the report is
printed.

### Codex protocol

The quota-free handshake proved:

- stdio JSONL transport starts successfully outside the test sandbox;
- `initialize` and `initialized` complete;
- `account/read` confirms ChatGPT authentication; and
- the generated schema is specific to the installed CLI version.

The live probe then proved:

- `thread/start`;
- `turn/start`;
- incremental agent-message deltas;
- item, status, usage and completion notifications;
- completion in a read-only sandbox; and
- `thread/resume` from a new app-server process.

Both minimal turns returned the required sentinel text.

Codex omits the normal `"jsonrpc":"2.0"` field on the wire even though its
messages follow JSON-RPC semantics. WebSocket transport is experimental; the
gateway will use stdio.

Official reference:
<https://developers.openai.com/codex/app-server>

### Claude protocol

The live probes used the installed Claude Code binary and the claude.ai
subscription, with all tools removed. They proved:

- `stream-json` output;
- partial stream events;
- session IDs;
- a second process resuming a stored session;
- bidirectional `stream-json` input;
- two turns on one long-lived process; and
- the process remaining alive after the first result.

Claude accepted `--remote-control` together with the persistent structured
process. The CLI stream did not expose a Remote Control URL or independently
verifiable registration state. A later desktop acceptance test must confirm
that the active conversation appears in `claude.ai/code`; until then the
remote UI claim remains manually unverified.

The flags are documented, but the exact stdin NDJSON message schema is not
fully specified in the public CLI reference. The Claude adapter must therefore:

- isolate this transport behind a narrow interface;
- validate every incoming and outgoing event defensively;
- retain contract fixtures for the installed CLI version;
- tolerate unknown event types; and
- fail with a recovery path to the normal Claude CLI.

Official references:

- <https://code.claude.com/docs/en/cli-usage>
- <https://code.claude.com/docs/en/remote-control>
- <https://platform.claude.com/docs/en/agent-sdk/streaming-output>

### Probe commands

Quota-free:

```bash
.venv/bin/python tools/provider_probe.py
```

The Codex handshake may require normal user access to `~/.codex`, which a
restricted test sandbox can block. CI uses unit fixtures and does not execute
provider authentication or network calls.

Quota-consuming and intentionally excluded from CI:

```bash
.venv/bin/python tools/provider_live_probe.py \
  --provider codex --allow-token-use

.venv/bin/python tools/provider_live_probe.py \
  --provider claude --allow-token-use --persistent
```

The live probe requires an explicit acknowledgement flag, disables Claude
tools, and starts Codex with `sandbox=read-only` and
`approvalPolicy=never`.

## Implementation phases

### Phase 1: engineering service boundary — complete

Move UI-independent behavior behind typed services:

```text
BenchService
WiringService
MotorService
FlightService
HistoryService
```

Implemented in `core/services.py`. Streamlit now consumes these services, so
the same contracts can be reused by MCP and the desktop gateway without
importing a page or session state. The boundary includes:

- typed capture, wiring and progress values;
- thread-safe cooperative cancellation;
- stable error codes such as `capture_timeout`, `motor_simulation_failed`,
  `flight_simulation_failed` and `run_not_found`;
- dependency injection for isolated contract tests; and
- history serialization compatible with the existing SQLite records.

All 28 automated checks pass, including every Streamlit page, bilingual
navigation, diagram rendering, service contracts and existing adapters.

Cancellation is checked before a subprocess starts and after it returns.
True mid-process termination belongs in the gateway supervisor in Phase 3,
where a process group can be interrupted and reaped without changing the
trusted simulation adapters prematurely.

### Phase 2: Rocketry MCP — complete

`rocketry_mcp.py` exposes the official Python MCP SDK over local stdio. Both
provider installations are registered with the same `rocketry` server name
and absolute interpreter path:

```text
system_status       list_ports
capture_bench       get_wiring_guide
run_motor_sweep     run_flight
get_run             compare_runs
export_csv          run_tests
```

The implementation deliberately separates the MCP transport
(`rocketry_mcp.py`) from provider-neutral operations (`core/mcp_tools.py`).
Codex, Claude, Streamlit and the future gateway therefore share the service
and persistence layers without importing each other.

Completed acceptance:

- the official SDK client initialized, listed all ten tools and invoked
  `system_status` over a real stdio subprocess;
- Codex invoked `rocketry.system_status` and returned the expected sentinel;
- Claude Code reported the server connected, invoked the same operation and
  returned the expected sentinel;
- captures and simulations automatically receive a History `run_id`;
- comparisons, CSV exports and test logs receive persistent `artifact_id`
  values under the ignored `.rocketry/` data directory;
- row-returning tools are bounded or paginated to protect model context;
- Linux `flock` locks coordinate serial, simulator and test operations across
  the separate provider server processes;
- tool annotations distinguish read-only queries from local writes;
- stable service errors are returned as structured MCP errors; and
- no ignition, actuation, arbitrary shell or arbitrary test command exists.

The complete local suite now contains 33 checks. It found and prevented a
JSON artifact/manifest filename collision during implementation.

Official references:

- <https://learn.chatgpt.com/docs/extend/mcp?surface=cli>
- <https://code.claude.com/docs/en/mcp>
- <https://py.sdk.modelcontextprotocol.io/>

### Phase 3: agent gateway - implemented

Implemented:

- supervised provider processes;
- sessions and normalized events;
- bounded queues and backpressure;
- approvals and interruption;
- event and artifact persistence;
- serial and simulation locks;
- crash recovery.

The process runs on `127.0.0.1` only and uses an ephemeral bearer token for the
desktop connection.

Worktree allocation remains the final concurrency hardening item before a
packaged release.

### Phase 4: desktop shell - developer build implemented

The Tauri/React client now includes:

- workspace and provider selection;
- independent conversation history;
- natural-language composer;
- activity timeline;
- approval surface;
- activity and command-output inspector;
- live engineering plots;
- bilingual persistent settings; and
- reduced-motion support.

The normal experience is structured rather than a raw terminal. Full stdout
and stderr remain available in an advanced inspector.

The diff inspector and structured provider question forms remain open.

### Phase 5: Streamlit migration

Migrate in this order:

1. Agent
2. History
3. Bench
4. Motor
5. Flight
6. Wiring
7. Home

Remove the JSONL relay and polling fragment only after desktop parity and
recovery tests pass.

## Permission policy

| Operation | Policy |
| --- | --- |
| Read inside project | Automatic |
| Edit assigned worktree | Automatic and visible |
| Known tests and simulations | Automatic and visible |
| Open ESP32 serial port | Notify before opening |
| Network, package install, sudo | Approval required |
| Write outside workspace | Approval required |
| Destructive command | Approval required |
| Ignition or hazardous actuation | Unavailable |

## Mandatory acceptance tests

- provider subscription authentication without API keys;
- two concurrent sessions in separate worktrees;
- streaming messages, commands, tests and diffs;
- explicit approval round trip;
- interrupt and resume;
- app window close/reopen while a job continues;
- ESP32 disconnect during capture;
- simulation timeout and cancellation;
- duplicate and out-of-order events;
- English/Spanish persistence;
- visual regression at supported Linux resolutions; and
- manual Claude Remote Control visibility from a second device.

## Commit strategy

Each architectural boundary receives a separate verified commit. Simulation
refactors, provider transports and frontend migration must not be combined in
one commit. Live provider probes are never part of CI because they consume
subscription quota.
