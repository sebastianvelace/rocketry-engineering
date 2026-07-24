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
allowlist plus interactive approval. Both dependencies are present on this
workstation as of 2026-07-23 and the sandbox is confirmed active (see
"Acceptance" below). "Allow for session" rewrites the SDK's suggested
permission destination to the current session; it no longer silently
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

### Resuming a conversation whose provider session has expired

A stored `provider_session_id` can stop being resumable for reasons outside
this gateway's knowledge — the provider prunes or clears its own local
session state. Reproduced for real against a live Claude Code CLI and a
genuinely old session from this workstation's own `gateway.db`: `client.
connect()` raised `ProcessError`, and the CLI's stderr (delivered separately
through the `stderr` callback, since the SDK deliberately does not embed it
in the exception) read `No conversation found with session ID: <id>`.
Before this fix, `SessionManager._ensure_adapter` treated that identically
to a real connection failure — marked the session `failed` and left it
there. Every reconnect attempt repeated the same failure, permanently
bricking the conversation; the operator saw only a generic "Command failed
with exit code 1" with no explanation and no way to continue that chat.

`SessionManager._start_with_resume_fallback` now catches a failed resume
specifically (only when a `provider_session_id` was already stored, i.e.
this is a reconnect, not a first connect) and retries once with a fresh
provider session instead of failing outright. A `notice`-type event records
what happened and renders inline in the conversation timeline (not just the
raw log) so the operator knows the old provider-side thread is gone even
though the durable transcript here is intact. This is provider-agnostic —
the same fallback covers Codex if its app-server ever prunes a thread the
same way — and it also means every command that goes through
`_ensure_adapter` (`/status`, `/rename`, `/compact`, `/review`, dynamic
Claude commands) self-heals from an unresumable session instead of failing.
Verified against the actual broken session ID pulled from this
workstation's real database (not a synthetic fixture), plus a unit test in
`tests/test_session_manager.py`.

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

### Bundle size

`BenchView`, `WiringView`, `MotorView`, `FlightView`, `HistoryView` and
`UsageView` are lazy-loaded (`React.lazy` + `Suspense`, following the
existing `MessageContent` pattern) instead of shipped in the main chunk —
none of them are needed for the default Agent view. Confirmed the
`@phosphor-icons/react` barrel import was not the bloat source first
(`sideEffects: false` in its `package.json`, so unused icons were already
tree-shaken); the remaining ~490 KB main chunk is dominated by React,
`motion/react` and uPlot (`RunPlot`, needed eagerly since the Agent view's
result dock defaults to its "runs" tab). Main chunk: 522 KB → 492 KB
minified; `EngineeringViews` (26 KB) and `UsageView` (6 KB) now load only
when the operator first navigates there.

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
conversation.

**Every event type in this section is now confirmed against a real
provider turn**, not just the assumed schema:

- Claude `thinking`, `tool_started`/`tool_completed` — confirmed (see
  `AskUserQuestion` below for the same live-check approach).
- Claude subagents — a live `Task` tool call matched the assumed shape
  exactly, including a detail the SDK's own docs call out but that's easy
  to miss: a completed subagent fires **two** `subagent_completed` events
  (one generic `TaskUpdatedMessage` patch, one `TaskNotificationMessage`
  with the actual output). Both target the same timeline card via
  `task_id`, so the card updates in place instead of duplicating, and the
  more useful notification text — the subagent's real output — naturally
  wins since it arrives second.
- Codex `plan_updated` — the assumed `{plan: [{step, status}]}` shape was
  right, but the live turn used `status: "inProgress"` (camelCase) where
  the CSS only had a `status-in_progress` (snake_case) selector — a real,
  if minor, bug: in-progress plan steps never got the accent-color
  treatment. Fixed with a selector for both spellings; `desktop/e2e/
  workstation.e2e.ts` now asserts the computed color on an `inProgress`
  step so this can't silently regress again.

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

**Verified against a real Claude turn** (not just the assumed schema): a
live `AskUserQuestion` call was forced with a real Claude Code process, the
raw `input_data` matched the assumed `{questions: [{question, header,
options: [{label, description}], multiSelect}]}` shape exactly, and
resolving the approval with `answers={"<question>": "F-class"}` produced a
final assistant reply of exactly `"F-class"` — confirming `updated_input`
is genuinely consumed as the tool's result rather than the CLI expecting a
separate interactive path.

### Diff inspector

Tool call cards (`ActivityFeed.tsx`'s `ToolCard`) now detect a diffable
call from its **input shape**, not its tool name, since Claude (`Edit`/
`Write`) and Codex (`fileChange`) disagree on both: `old_string`/
`new_string` renders a real line diff (`desktop/src/diff.ts`, a
dependency-free ~40-line LCS differ — no new npm package, matching how the
repo only added `react-markdown`/`remark-gfm` before this), a `diff`/
`unifiedDiff`/`patch` string is parsed as a standard unified diff, and a
bare `content` + `file_path` (Claude `Write`) renders as a pure addition.
Running tool calls show a live elapsed-time counter, cleared once the
paired `tool_completed` event lands (Phase 1's started/completed
correlation makes this possible without new plumbing).

**Verified and corrected against a real Codex edit turn.** The original
guess (a top-level `diff`/`unifiedDiff`/`patch` string on the item) was
wrong. The real shape, confirmed against a live Codex process editing a
scratch file: `{ type: "fileChange", changes: [{ path, kind, diff }] }` —
one entry per touched file, `diff` a bare hunk (`@@ ... @@` plus `-`/`+`
lines, no `+++`/`---` file headers). `extractDiff` in `ActivityFeed.tsx` now
reads `input.changes[]`, prefixing each file's hunk with its path so a
multi-file `fileChange` call reads as one card per touched file instead of
one opaque blob.

### Bench handshake/diagnostic view

Unrelated to the agent work above: a Bench capture timeout used to report
nothing beyond "no complete block was received." `core/blocks.py`'s
`read_one_block` (and `open_and_read`) now always return a
`BlockReadDiagnostics` record alongside the `Block | None` result — bytes
received, line count, the last non-empty line seen, whether a `# BLOCK`
marker ever arrived, and rows captured so far — whether or not the read
timed out. `ServiceError` gained an optional `details` field to carry it;
`gateway/server.py`'s `error_response` and `rocketry_mcp.py`'s error
formatting both forward it, so both the desktop client and an agent driving
the Bench MCP tool see the same diagnostic. The desktop client
(`GatewayApiError` in `api.ts`, `BenchDiagnosticsPanel` in
`EngineeringViews.tsx`) renders it inline under the error line on a
`capture_timeout`.

This directly targets the open acceptance note above: *"`/dev/ttyUSB0` was
enumerated, but the Bench E2E timed out without receiving a complete
block."* The diagnostic surface and its parsing are verified (unit tests in
`tests/test_blocks.py`, `tests/test_services.py`, `tests/test_gateway_server.py`,
a mocked-gateway E2E scenario), but the underlying hardware acceptance
re-test — confirming the firmware actually reaches this workstation and
what the diagnostics say when it does — needs a session with the ESP32
connected and emitting a block, which this implementation session did not
have.

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

### Optional isolated workspaces

By default every session shares the `rocketry-portfolio` repository root, which
is fine for read-mostly or single-session work but means two sessions
editing files at the same time can collide. The new-session dialog now has
an opt-in "isolated workspace" toggle: `gateway/worktrees.py`'s
`WorktreeManager` allocates a `git worktree` at
`.rocketry/worktrees/<session_id>` on its own `workstation/<session_id>`
branch, guarded by an in-process `asyncio.Lock` (the gateway is a single
process, so no cross-process file lock is needed here — unlike the Rocketry
MCP's serial/simulator locks). `SessionManager.create_session` allocates the
worktree before the session record exists, and `delete_session` removes it
(`git worktree remove --force` plus the branch) after the session and its
provider process are gone. Removal refuses to touch anything outside
`.rocketry/worktrees/` — it never reaches into the user's real working
tree. The session footer shows the worktree branch instead of "full
repository" when a session is isolated. Verified with real git repositories
in `tests/test_worktrees.py` and an integration test in
`tests/test_session_manager.py`, not mocked subprocess calls.

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
  the narrow allowlist.
- `socat` was installed alongside the already-present `bubblewrap`, and a
  follow-up live turn confirmed `sandbox_enabled` is now `True` and a Bash
  call runs through the real bubblewrap sandbox (`autoAllowBashIfSandboxed`)
  with zero `can_use_tool` callbacks — not just the narrow allowlist. Full
  Claude Bash sandboxing is active on this workstation.
- A one-geometry openMotor E2E created run #8 with one viable `67F133`
  configuration and 66.54 N·s simulated impulse.
- An OpenRocket E2E created run #9 with 1503.33 m simulated apogee and no
  reported warnings.
- `/dev/ttyUSB0` was enumerated, but the Bench E2E timed out without receiving
  a complete block. The application reported `capture_timeout` correctly; the
  firmware/serial trigger remains an open hardware acceptance item.

### Visual regression snapshots

`desktop/e2e/visual.e2e.ts` renders the populated agent workspace at 900,
1280 and 1440 px with `reducedMotion: "reduce"` emulated (removing
animation timing as a source of flakiness) and asserts pixel-level
stability against baselines in `desktop/e2e/visual.e2e.ts-snapshots/`. The
shared mock-gateway fixture used by `workstation.e2e.ts` was extracted into
`desktop/e2e/gateway-fixture.ts` so both specs reuse it — Playwright
disallows one test file importing another directly. Baselines are
platform-tagged (`-linux.png`) and were generated on this workstation;
regenerate them deliberately after an intentional layout change with
`pnpm exec playwright test visual.e2e.ts --update-snapshots`, never to make
a failure disappear without looking at the diff first.

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
installer, and this is intentionally a personal-use tool rather than a
distributed product. Status of the items originally tracked here:

1. **Done** — automatic Git worktree allocation for concurrent modifying
   sessions (see "Optional isolated workspaces" above).
2. **Done, Claude only** — structured answers for `AskUserQuestion` (see
   "Structured `AskUserQuestion` (Claude)" above). Codex has no equivalent
   method in its app-server protocol locally, so `requestUserInput` stays
   unimplemented until one is confirmed to exist.
3. **Done** — diff inspector and per-operation elapsed time (see "Diff
   inspector" above).
4. **Done, hardware re-test still open** — a Bench handshake/diagnostic view
   (bytes received, last protocol line, expected block markers; see
   "Bench handshake/diagnostic view" above). Repeating capture acceptance
   with the firmware actively emitting a block needs a session with the
   ESP32 connected.
5. **Done** — visual regression snapshots for 900, 1280 and 1440 pixel
   widths (see "Visual regression snapshots" above).
6. **Out of scope** — packaging the Python gateway as a sidecar. This is a
   personal-use tool; openMotor and OpenRocket would remain external
   dependencies at fixed paths regardless of packaging, so a real installer
   was decided against.
7. **Deferred** — a remote-session strategy. Remote access is deliberately
   not enabled by binding the gateway to the LAN. If revisited, the two
   options considered were Tailscale plus an authenticated HTTPS relay
   (engineering machine stays the execution host), or a shared
   transcript/session store for conversation-only continuity. Neither is
   built; this stays a documented option, not a plan.
