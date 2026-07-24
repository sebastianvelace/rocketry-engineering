# Rocketry Console technical audit

Date: 2026-07-23

## Scope

The audit covered the six Streamlit surfaces, serial block parsing, Plotly
dispatch, SQLite persistence, openMotor and OpenRocket subprocess adapters,
path portability, error states, responsive behavior and operator safety cues.

## Executive assessment

The original implementation had a sound small-system architecture:

```text
ESP32 -> serial block parser -> plot dispatch -> SQLite

UI -> openMotor adapter -> isolated Python process
UI -> OpenRocket adapter -> isolated JVM process
```

Keeping physics and flight behavior in the existing project modules was the
right decision. The main weaknesses were missing automated regression
coverage, UI duplication, incomplete edge-state handling and a few silent or
uncaught failure paths.

After remediation, all six pages share one UI layer, every page has a guided
empty/error/success path, and the critical integrations have automated and
real-environment checks.

## Findings and disposition

| Severity | Finding | Disposition |
| --- | --- | --- |
| High | `FFT` was detected but absent from the plot dispatcher, so valid FFT blocks silently used the generic time-series plot. | Fixed and regression-tested. |
| High | OpenRocket subprocess timeouts escaped the adapter as raw exceptions. | Converted to `OpenRocketError` with an actionable message and test. |
| High | A relative `.eng` path failed because the subprocess changes its working directory to the OpenRocket installation. | Adapter now validates and resolves the motor curve to an absolute path. |
| Medium | Serial discovery either missed non-Linux devices or, after broad discovery, could mistake `ttyS0` for an ESP32. | Uses pyserial metadata plus USB device naming; motherboard UARTs are excluded. |
| Medium | Inconsistent serial row widths were accepted and failed later inside plots. | Malformed rows are skipped during capture; stored mixed-width blocks are rejected clearly. |
| Medium | Empty blocks could trigger indexing errors in generic plots. | Empty and mixed-width blocks now produce explicit validation errors. |
| Medium | Flight could fail during page construction if no `.eng` curves existed. | Added a blocking empty state with the expected path and route to Motor. |
| Medium | History could fail with empty filters and compared the first two columns even when they were not meaningful or numeric. | Empty filters are handled; comparison exposes only common numeric axes. |
| Medium | Run deletion had no confirmation and required manual refresh. | Added explicit confirmation and immediate rerun. |
| Medium | Repository paths were tied to `~/rocketry-portfolio`. | Simulation paths now derive from the repository location. External tool environments remain documented prerequisites. |
| Medium | Dependencies were unconstrained. | Added compatible major-version ranges for reproducibility. |
| Medium | No automated test suite existed. | Added protocol, plotting, storage, adapter and all-page smoke tests. |
| Low | Home copy still described unfinished future pages. | Replaced with current system status and product map. |
| Low | Plotly and Streamlit deprecations were visible. | Standardized `width="stretch"` and a shared Plotly theme. |

## Verification evidence

### Automated

`bash tools/ci_check.sh` covers:

- Python compilation
- serial protocol metadata and malformed-row behavior
- USB serial filtering
- FFT dispatch
- empty and inconsistent plot input
- SQLite save, list, reopen and delete
- openMotor and OpenRocket timeout mapping
- missing motor-curve handling
- render smoke test for Home, Bench, Wiring, Motor, Flight and History
- `git diff --check`

### Real integrations

The following checks were executed on the audited workstation:

- ESP32 at `/dev/ttyUSB0`: captured one `SINE` block with 200 rows,
  `F_SIGNAL=50`, `F_SAMPLE=1000`, `N=200`.
- openMotor: one candidate at 12 mm core, 4 segments and 45 mm segment length.
  The run returned one viable `67F133` configuration.
- OpenRocket: `E_sintubo.eng`, minimum-diameter architecture and baseline fins.
  The run completed at about 1503 m apogee, 281 m/s maximum speed, 2.38 cal
  launch stability and 41.0 m/s rail exit.

These values confirm integration execution. They are not independent
validation of the physical models.

### Visual

Browser captures were reviewed at:

- 1440 x 1200 Home
- 1440 x 1200 Wiring
- 390 x 844 Home

The responsive check caught and fixed an always-expanded mobile sidebar.

## Remaining risks

1. `runs.db` has no migration framework or built-in backup workflow. This is
   acceptable for the current single-user local scope, but should change
   before shared or long-lived operational use.
2. Simulation calls block the current Streamlit session while their isolated
   subprocess runs. A job queue is the next step if concurrent users or long
   sweeps become a requirement.
3. The serial protocol has no checksum, schema version or explicit device
   identity. A future firmware protocol should add all three.
4. Wiring guidance is a reproducible aid, not electrical design-rule checking.
5. There is no end-to-end test that clicks every browser widget. Streamlit
   smoke tests and real browser screenshots cover page construction and
   responsive presentation.

## Recommended next technical increments

1. Add a protocol version and board identifier to `# BLOCK` metadata.
2. Add a cancellable background job model for Motor and Flight.
3. Add SQLite backup/import and a schema version.
4. Persist the exact simulation input envelope as a first-class object instead
   of only embedding it in result metadata.
5. Add named acceptance profiles for rail speed, stability, pressure and flow
   gates so warnings remain traceable to a reviewed standard.

## Desktop agent harness follow-up

The later desktop audit added a second application boundary around the same
engineering services. Its highest-severity finding was a Codex app-server
schema drift: the installed 0.145.0 CLI accepts `workspace-write` in
`thread/start` and `thread/resume`, while the adapter still sent
`workspaceWrite`. That prevented every Codex session from connecting. The
request preset is corrected and protected by an adapter regression test.

Provider connection failures are now persisted, partial provider processes are
closed, and the desktop displays an actionable retry notice. The browser suite
uses Playwright with deterministic gateway responses; separate live acceptance
turns verified the installed Claude Code and Codex subscription transports.

### Prioritized remaining improvements

1. **Bench observability:** an enumerated serial port is not proof that the
   firmware is emitting the expected block. Expose bytes received, the last
   parsed line, reset/handshake state and the expected `# BLOCK` marker. This is
   the immediate priority because the attached ESP32 timed out during E2E.
2. **Protocol compatibility:** generate or inspect the installed Codex
   app-server schema during dependency upgrades. The targeted preset test
   prevents the specific regression, but a small compatibility probe should
   cover initialization, thread start, resume and approval response shapes.
3. **Long-session rendering:** Markdown is memoized, but the conversation feed
   is not virtualized. Add windowing once sessions routinely exceed a few
   hundred messages or tool events.
4. **Frontend boundaries:** `App.tsx` still owns transport lifecycle, session
   state, composer behavior and layout. Extract session transport and
   conversation hooks before adding more provider-specific controls.
5. **Session management:** add rename, archive/delete and a clear indication
   when a provider session is already active in another workstation process.
6. **Release portability:** package the Python gateway as a Tauri sidecar and
   add a migration/backup command for `.rocketry/gateway.db`.
7. **Remote continuity:** conversation access from another computer still
   needs an authenticated relay or synchronized transcript store; the local
   gateway must not simply bind to the LAN.
