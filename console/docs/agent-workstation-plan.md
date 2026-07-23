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
outside the first release. Claude's native Remote Control may expose its
conversation on another device while the local process remains alive; the
Rocketry UI and ESP32 remain local.

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
Codex app-server    Claude Code CLI
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

### Phase 1: engineering service boundary

Move UI-independent behavior behind typed services:

```text
SerialService
BenchService
WiringService
MotorService
FlightService
RunService
```

Acceptance:

- existing tests and results remain equivalent;
- no engineering operation depends on Streamlit session state;
- long operations expose progress and cancellation; and
- errors have stable codes.

### Phase 2: Rocketry MCP

Expose a shared, local MCP server:

```text
rocketry.list_ports
rocketry.capture_bench
rocketry.get_wiring_guide
rocketry.run_motor_sweep
rocketry.run_flight
rocketry.get_run
rocketry.compare_runs
rocketry.export_csv
rocketry.run_tests
```

Acceptance:

- Codex and Claude can invoke the same deterministic operation;
- every result receives a run or artifact ID;
- serial access is exclusive; and
- no hazardous actuation tool exists.

### Phase 3: agent gateway

Implement:

- supervised provider processes;
- sessions and normalized events;
- bounded queues and backpressure;
- approvals and interruption;
- event and artifact persistence;
- serial and simulation locks;
- worktree allocation; and
- crash recovery.

The process runs on `127.0.0.1` only and uses an ephemeral bearer token for the
desktop connection.

### Phase 4: desktop shell

Create a Tauri/React client with:

- workspace and provider selection;
- independent conversation history;
- natural-language composer;
- activity timeline;
- approval surface;
- test and diff inspector;
- live engineering plots;
- bilingual persistent settings; and
- reduced-motion support.

The normal experience is structured rather than a raw terminal. Full stdout
and stderr remain available in an advanced inspector.

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
