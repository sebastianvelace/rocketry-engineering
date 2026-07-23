# Agent harness feasibility

## Original bridge decision

Keep the terminal as the execution and approval surface. Use Rocketry Console
as a read-only observation and results surface.

The included `tools/agent_relay.py` starts a non-interactive Codex or Claude
turn, preserves its terminal stream and mirrors normalized events to
`.console/agent-events.jsonl`. The Agent page reads only the last events.

## Why this boundary

- Codex app-server exposes bidirectional JSON-RPC threads, turns, streamed
  items, command progress and approval requests. It is the correct foundation
  for a dedicated interactive client:
  <https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md>
- Claude supports `--output-format stream-json` for programmatic streaming:
  <https://docs.anthropic.com/en/docs/claude-code/cli-usage>
- Streamlit fragments rerun independently of the complete script and are
  intended for live job status:
  <https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment>

Embedding an unrestricted PTY in a local web page would combine display,
command execution and approvals in one attack surface. The current bridge
therefore cannot run shell commands, send prompts or approve operations.

## Efficiency

The two-second fragment exists only on the Agent page. Each tick reads at most
80 tail records from a file capped at 2 MB and one small SQLite query. Bench,
Motor, Flight and History are not rerun.

For higher event rates, replace polling with a Streamlit component v2 connected
to an authenticated local WebSocket. Components v2 support bidirectional,
frameless communication:
<https://docs.streamlit.io/develop/concepts/custom-components/overview>.

## Next stage

The bidirectional desktop client is now approved and its provider feasibility
has been verified. The bridge remains a fallback until that client reaches
parity. See [the agent workstation implementation plan](agent-workstation-plan.md)
for the tested transports, security boundary and migration phases.

A full client will:

1. launch one authenticated local app-server process;
2. map threads and turns to an explicit session model;
3. stream messages and tool items over a bounded queue;
4. render approval requests inline and never auto-accept them;
5. write simulation outputs through the existing `store` API;
6. keep the terminal available as a recovery path.
