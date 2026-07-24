# Desktop workstation implementation

Date: 2026-07-23

## Delivered boundary

The desktop workstation is a Linux Tauri 2 application backed by a local
Python gateway. It is intentionally split into four layers:

```text
React client
  -> authenticated REST and durable WebSocket
Python gateway
  -> Codex app-server or Claude Agent SDK
Rocketry MCP
  -> engineering services, runs.db and artifacts
```

The React client never receives provider credentials and cannot start an
arbitrary process. Tauri generates an ephemeral token, starts the gateway on a
random `127.0.0.1` port and passes the connection values through an invoke
command. The packaged client uses Tauri's official `isTauri()` runtime check;
it no longer guesses from an internal global that is not guaranteed in
production builds. Tauri waits for `/health` to answer before returning the
connection, and React retries a bounded set of transient startup failures. The
gateway restricts workspaces to the repository root.

## Provider behavior

Codex uses the documented app-server stdio protocol:

- thread start and resume;
- incremental message, reasoning, command and tool events;
- exact turn interruption;
- command, file-change and permission-profile approvals; and
- `workspace-write` sandboxing with `on-request` approval policy;
- the live model catalog and per-turn model override; and
- native compact, review, rename, fork, account rate-limit and account usage
  requests.

Claude uses the official Python Agent SDK over the installed Claude Code
binary:

- the existing Claude subscription OAuth session;
- persistent session IDs and resume;
- incremental output;
- native `can_use_tool` approval callbacks;
- native interruption; and
- project/local settings without unrelated user hooks in the workstation
  process;
- an explicit, strict Rocketry MCP configuration instead of every connector
  attached to the Claude account;
- a provider prewarm when a session is selected, without submitting a model
  turn; and
- the live command catalog reported by Claude Code for composer completion;
- a native `/model` picker populated from Claude Code's own capability
  response; and
- per-session model persistence and restoration when a conversation reconnects.

Claude uses `acceptEdits` instead of the prompt-heavy default mode. Every tool
from the strictly configured local `rocketry` MCP is preapproved because that
server exposes only bounded measurement, simulation, history and fixed-test
operations—no ignition, launch actuation or arbitrary shell. A small allowlist
covers common read/verification commands such as `eza`, `rg --files`, project
builds and test runners. Package installation, arbitrary Bash, publishing,
network-sensitive commands and sandbox escapes still require approval.

On Linux, Claude's Bash sandbox is enabled automatically only when both
`bubblewrap` and `socat` are installed. If either dependency is missing, the
adapter does not pretend the sandbox is active and falls back to the narrow
allowlist plus interactive approval. "Allow for session" rewrites the SDK's
suggested permission destination to the current session; it no longer silently
writes a permanent project-local rule.

The composer uses a small provider-aware router. `/model`, `/usage`, `/status`,
`/rename` and `/clear` have consistent workstation behavior. Codex additionally
maps `/compact`, `/review` and `/fork` to app-server methods. Other Claude
commands are accepted only when the installed Claude process reports them in
its initialization capability catalog; unknown commands are rejected instead
of being disguised as ordinary prompts.

Internal Claude status and hook payloads are not persisted. The gateway keeps
only a compact initialization event, visible tool activity, assistant output
and usage. This prevents private hook context from leaking into the UI and
keeps SQLite bounded.

## Persistence and live updates

`.rocketry/gateway.db` uses SQLite WAL mode and stores:

- provider-independent sessions;
- ordered, idempotent events;
- pending and resolved approvals; and
- provider session IDs required for resume.

On restart, active turns become interrupted and orphaned approvals become
cancelled. A new message reconnects the matching provider session.
Conversations can be deleted from the session rail after an explicit
confirmation. Deleting a live conversation first closes its provider process,
then atomically removes the session; SQLite foreign-key cascades remove its
events and approvals.

The UI replays durable events, then subscribes by WebSocket from the last
sequence number. Subscriber queues are bounded. If a client is slow, SQLite
remains the source of truth and reconnect replay fills the gap.

There is no one-second timer. Engineering status, runs and artifacts load at
startup and refresh after a tool completes, a manual operation finishes or
the operator presses refresh.

Usage is also pull-based. Its provider snapshot is cached for 60 seconds and
can be refreshed manually:

- Claude percentages and reset labels come from the authenticated CLI's
  `/usage` response. Claude's request/session contribution figures are its
  approximate local activity and can omit other devices.
- Codex limits and historical token buckets come from
  `account/rateLimits/read` and `account/usage/read` on the authenticated
  app-server process.
- "Local tokens" are computed only from durable turns observed by this
  workstation. They are labelled separately and are not billing totals.

Raw Claude usage prose and Codex reset-credit identifiers are not exposed to
the React client.

## Visual system

The interface is treated as an engineering instrument:

- dark neutral surfaces;
- signal red as the single interaction accent;
- green only for real connected/ready state;
- Geist and Geist Mono self-hosted in the bundle;
- hierarchy through spacing and rules instead of repeated cards;
- Phosphor icons from one family;
- Motion only for message, modal and button state transitions;
- uPlot canvas charts for numeric series;
- a categorical metric field for Flight summary runs; and
- reduced-motion fallbacks.

The global rail owns Agent, Bench, Wiring, Motor, Flight and History. Agent
opens a secondary session rail, a conversation and approval pane, and a result
dock. Engineering surfaces use rules, forms and data fields rather than a
dashboard of repeated cards. English and Spanish labels persist in local
storage across views and restarts. The global rail can be resized from 58 to
118 pixels by dragging its right edge (or with the arrow keys while its
separator is focused); a double click or the Home key restores the default.
Native selects use the same dark instrument styling as the rest of the
application.

Agent messages render GitHub-flavored Markdown, including emphasis, lists,
links, tables and code blocks. Raw HTML is deliberately not enabled, so
provider output cannot inject executable markup into the desktop client.

## Native agent parity — 2026-07-23

Comparing this client against using Codex or Claude Code directly in a
terminal surfaced concrete gaps, not vague polish:

- Conversation text and everything else the agent did (tool calls, edits,
  reasoning) were split across a chat pane and a disconnected "Activity"
  tab, rendered as raw JSON — losing the single narrative a terminal
  session shows.
- Claude's extended thinking (`ThinkingBlock`) was silently dropped by the
  adapter.
- Claude subagents (the `Task` tool) were invisible — the Agent SDK's
  `TaskStartedMessage` / `TaskProgressMessage` / `TaskNotificationMessage` /
  `TaskUpdatedMessage` were unhandled.
- Codex's `turn/plan/updated` (its TodoWrite-equivalent) was mislabeled as a
  `"usage"` event — a real normalization bug, not a rendering gap.

`gateway/providers/claude.py` and `gateway/providers/codex.py` now emit
dedicated `thinking`, `subagent_started`/`subagent_progress`/
`subagent_completed`, and `plan_updated` events (`gateway/models.py`'s
`EventType` documents the full set); the event pipeline required no schema
change since `ProviderEvent.type`/`data` are free-form columns already
passed through unfiltered by `manager.py` and `server.py`.

`desktop/src/ActivityFeed.tsx` replaces the old text-only conversation
projection with a single chronological timeline: tool calls render as
collapsible cards correlated across their `tool_started`/`tool_completed`
pair (by `data.tool.id` for Claude, `data.item.id` for Codex) so one card
transitions from running to done/failed instead of two disconnected list
rows; thinking and Codex reasoning render as dimmed inline bubbles;
subagent activity renders as its own card; Codex plan updates render as a
checklist. The "Activity" tab remains as a secondary raw event log for
troubleshooting — it is no longer the primary way to see what the agent is
doing.

Verified with adapter unit tests (`tests/test_provider_adapters.py`) for
every new message/payload shape, a frontend unit test
(`desktop/src/App.test.ts`) asserting the merge order, and a mocked-gateway
Playwright scenario (`desktop/e2e/workstation.e2e.ts`) asserting thinking,
a tool call, a subagent and a plan update all render inline in the
conversation. Not yet exercised against a live Claude or Codex turn — the
Codex `fileChange` diff field (needed for the next phase) still needs that
live confirmation before its parser is considered final.

### Structured `AskUserQuestion` (Claude)

`AskUserQuestion` previously flowed through the generic tool-approval panel
as raw JSON with only approve/deny — there was no way to actually pick an
answer. The Agent SDK has no dedicated control-protocol subtype for this
tool (confirmed by inspecting `claude_agent_sdk/types.py`'s
`SDKControlRequest` subtypes: only `interrupt`, `can_use_tool`,
`initialize`, `set_permission_mode`, `hook_callback`, `mcp_message`,
`rewind_files`, `mcp_reconnect`, `mcp_toggle`, `stop_task`), so it must run
through the same `can_use_tool` permission callback this gateway already
implements — the selected answers are delivered back as the tool's
`updated_input`, the same mechanism `can_use_tool` already uses to modify
any tool call's arguments before it runs.

`gateway/providers/claude.py`'s `_request_permission` now tags
`ProviderApproval.details` with `kind: "ask_user_question"` and the parsed
`questions` array when the tool name matches. `resolve_approval` across
`claude.py`, `manager.py` and `server.py`'s `/api/approvals/{id}` route now
accepts an optional `answers` object, merged into the permission result's
`updated_input` as `{questions: [...], answers: {...}}`. The desktop client
(`ActivityFeed.tsx`'s `AskUserQuestionPanel`) renders an actual
radio/checkbox picker per question instead of raw JSON.

Codex's app-server protocol (`CODEX_COMMANDS`, `normalize_codex`) has no
equivalent method locally, so this is Claude-only for now — Codex keeps the
existing generic approval flow.

**Verification gap, stated plainly**: this is verified by adapter and E2E
tests against the assumed schema, not against a real `AskUserQuestion` call.
Before trusting it in daily use, trigger one for real and confirm the
`input_data` shape and that `updated_input` is actually consumed as the
tool's result rather than the CLI expecting a different interactive path —
per this project's own measure-before-you-trust discipline, this is
exactly the kind of assumption that needs a real measurement, not a second
inference.

## Workspace and model scope

Every session receives the detected `rocketry-portfolio` repository root as
its workspace, rather than only the `console/` directory. The session footer exposes that boundary as
`rocketry-portfolio / full repository` so the operator can verify the scope
without trusting hidden configuration. Codex applies the current
`workspace-write` sandbox preset to that root; Claude Code starts with the same working directory and its normal
built-in repository tools.

Typing `/model` in either provider opens the native model selector instead of
sending a conversational prompt. Selecting a model calls the Agent SDK's live
`set_model` operation for Claude or applies the app-server model override for
Codex, then saves the choice in session metadata. A resumed session restores
that choice before accepting the next turn. Model options are never hard-coded
in React; they come from the installed provider process, so the interface
follows the authenticated account's actual availability.

## Native engineering surfaces

The desktop client now calls the shared service boundary through authenticated
gateway endpoints:

```text
Bench   -> capture, detect, save, plot
Wiring  -> prepare, connect, verify, generated SVG and pin sequence
Motor   -> bounded openMotor sweep, save, plot
Flight  -> validated motor curve, OpenRocket run, save, metrics
History -> filter, reopen, overlay, export and delete
```

Agent MCP calls and manual UI calls converge on `core/services.py`,
`runs.db`, the artifact store and the same cross-process operation locks.
There is no duplicate simulation implementation in React.

## Acceptance on 2026-07-23

- Strict Claude startup connected in 0.52 seconds in an isolated probe.
- Gateway prewarm connected a real Claude session in 1.08 seconds.
- Claude reported 44 commands, including `/model` and `/compact`.
- A one-geometry openMotor request completed in 3.36 seconds and saved run #6.
- An OpenRocket minimum-diameter flight completed in 4.96 seconds and saved
  run #7 with a 1503.31 m apogee.
- Wiring JSON delivered visible UTF-8 SVG and localized pin instructions.
- Visual inspection covered Agent, Wiring prepare/connect and Motor at
  1600 by 960.
- Follow-up acceptance verified the live Claude model catalog and a model
  change to Haiku, semantic Markdown output without literal `**` markers, a
  112-pixel expanded navigation rail, and dark Flight selectors.
- Codex 0.145.0 rejected the legacy `workspaceWrite` request value. Updating
  thread start and resume to `workspace-write` restored the provider; a real
  streamed turn completed with `CODEX_E2E_OK` in about five seconds.
- A fresh Claude session completed a real streamed turn with
  `CLAUDE_E2E_OK` in about 1.5 seconds.
- Codex returned its live six-model catalog, accepted a switch to
  `gpt-5.6-terra`, and completed native status, rename, fork, clear and compact
  command acceptance.
- The live Usage endpoint returned both accounts in about three seconds:
  Claude subscription windows through `/usage` and Codex rate-limit plus
  historical-token data through app-server. Its cached response avoids
  continuous provider polling.
- A cold packaged-app start opened the canonical
  `console/.rocketry/gateway.db`, passed the native `/health` readiness probe
  and returned all 10 stored sessions. Browser E2E also recovered after an
  injected first-request `503`.
- A real Claude turn ran the previously prompt-triggering
  `eza -la console | head -5` inspection with zero approval callbacks under
  the narrow allowlist. This workstation currently has `bubblewrap` but not
  `socat`, so full Claude Bash sandboxing remains disabled until that system
  dependency is installed.
- A one-geometry openMotor E2E created run #8 with one viable `67F133`
  configuration and 66.54 N·s simulated impulse.
- An OpenRocket E2E created run #9 with 1503.33 m simulated apogee and no
  reported warnings.
- `/dev/ttyUSB0` was enumerated, but the Bench E2E timed out without receiving
  a complete block. The application reported `capture_timeout` correctly; the
  firmware/serial trigger remains an open hardware acceptance item.

## Security constraints

- The gateway binds to `127.0.0.1` only.
- REST requires a bearer token.
- WebSocket authentication uses a subprotocol, not a query-string token.
- CORS accepts only Tauri and dynamic localhost development origins.
- Artifact paths are validated under `.rocketry/artifacts`.
- Event sizes and result pages are bounded.
- Serial and simulator operations use Linux file locks across both providers.
- No MCP ignition, launch actuation or arbitrary shell tool exists.

## Verification completed

- Python store, gateway, adapter and API unit tests.
- Real REST and WebSocket replay on localhost.
- Real Claude Agent SDK subscription turn returning
  `CLAUDE_GATEWAY_OK`.
- Existing real Codex app-server start, stream and resume probe.
- React event projection and bilingual copy tests.
- Playwright browser E2E for Markdown, repository scope, native model
  selection, navigation resizing, dark engineering controls and the dual
  provider Usage view.
- TypeScript/Vite production build.
- Rust `cargo check`.
- Tauri debug executable build.
- Ten-second executable startup under Xvfb, including the embedded gateway.
- Headless visual captures at 1440 x 900 with empty and populated sessions.

## Remaining release work

The current application is a verified local developer build, not a portable
installer. Before calling it a first packaged release:

1. add automatic Git worktree allocation for concurrent modifying sessions;
2. add structured answers for Claude `AskUserQuestion` and Codex
   `requestUserInput`;
3. add a diff inspector and per-operation progress detail;
4. add a Bench handshake/diagnostic view (bytes received, last protocol line,
   expected block markers) and repeat capture acceptance with the firmware
   actively emitting a block;
5. add visual regression snapshots for 900, 1280 and 1440 pixel widths;
6. package the Python gateway as a sidecar instead of depending on the
   repository `.venv`; and
7. choose a remote-session strategy.

Remote access is deliberately not enabled by binding the gateway to the LAN.
For a second computer, the safe options are:

- Tailscale plus an authenticated HTTPS relay to this gateway while the
  engineering machine remains the execution host; or
- a shared transcript/session store for conversation-only continuity.

The second option matches the stated need to keep the Claude conversation
available without remotely controlling the ESP32. It should be implemented
after choosing the storage account and retention policy.
