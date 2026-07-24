import { describe, expect, it } from "vitest";
import { buildTimeline, extractDiff, unifiedDiffToLines } from "./ActivityFeed";
import { activityEvents } from "./App";
import { translate } from "./i18n";
import type { AgentEvent } from "./types";

function event(
  sequence: number,
  type: string,
  text: string,
  role: string | null = null,
  data: Record<string, unknown> = {},
): AgentEvent {
  return {
    sequence,
    id: `event-${sequence}`,
    session_id: "session-1",
    created_at: "2026-07-23T00:00:00Z",
    type,
    role,
    text,
    data,
  };
}

describe("unified activity timeline", () => {
  it("coalesces streaming deltas and replaces them with the final answer", () => {
    const timeline = buildTimeline([
      event(1, "user_message", "Run the test", "user"),
      event(2, "assistant_delta", "Test "),
      event(3, "assistant_delta", "running"),
      event(4, "assistant_message", "Test passed", "assistant"),
    ]);

    expect(timeline).toEqual([
      { kind: "user", id: "event-1", text: "Run the test" },
      { kind: "assistant", id: "event-4", text: "Test passed" },
    ]);
  });

  it("keeps incomplete streaming text visible", () => {
    const timeline = buildTimeline([
      event(1, "assistant_delta", "Capturing"),
      event(2, "assistant_delta", "..."),
    ]);
    expect(timeline[0]).toMatchObject({
      kind: "assistant",
      text: "Capturing...",
      streaming: true,
    });
  });

  it("interleaves tool calls, thinking and subagent activity inline instead of a separate tab", () => {
    const timeline = buildTimeline([
      event(1, "user_message", "Investigate the flaky test", "user"),
      event(2, "thinking", "Let me check the logs first"),
      event(3, "tool_started", "Bash", "assistant", { tool: { id: "tool-1", name: "Bash", input: { command: "pytest" } } }),
      event(4, "tool_completed", "done", null, { tool_result: { tool_use_id: "tool-1", content: "1 passed", is_error: false } }),
      event(5, "subagent_started", "Investigate flaky test", null, { task_id: "task-1", tool_use_id: "tool-2" }),
      event(6, "subagent_completed", "Found root cause", null, { task_id: "task-1", status: "completed" }),
      event(7, "assistant_message", "Fixed it.", "assistant"),
    ]);

    expect(timeline.map((item) => item.kind)).toEqual([
      "user",
      "thinking",
      "tool",
      "subagent",
      "assistant",
    ]);
    const tool = timeline[2] as { status: string; output: string };
    expect(tool.status).toBe("done");
    expect(tool.output).toBe("1 passed");
    const subagent = timeline[3] as { status: string; summary?: string };
    expect(subagent.status).toBe("done");
    expect(subagent.summary).toBe("Found root cause");
  });

  it("labels Codex plan updates as a plan, not usage telemetry", () => {
    const timeline = buildTimeline([
      event(1, "plan_updated", "turn/plan/updated", null, {
        plan: [{ step: "Read config", status: "completed" }],
      }),
    ]);
    expect(timeline[0]).toMatchObject({
      kind: "plan",
      steps: [{ label: "Read config", status: "completed" }],
    });
  });

  it("still exposes the raw event log for troubleshooting", () => {
    expect(
      activityEvents([
        event(1, "user_message", "hello"),
        event(2, "tool_started", "run_tests"),
        event(3, "command_output", "ok"),
      ]).map((item) => item.type),
    ).toEqual(["tool_started", "command_output"]);
  });
});

describe("tool call diff detection", () => {
  it("diffs a Claude Edit tool call from old_string/new_string", () => {
    const diff = extractDiff({ file_path: "a.py", old_string: "x = 1", new_string: "x = 2" });
    expect(diff).toEqual([{ kind: "remove", text: "x = 1" }, { kind: "add", text: "x = 2" }]);
  });

  it("treats a Claude Write tool call as a pure addition", () => {
    const diff = extractDiff({ file_path: "a.py", content: "print(1)" });
    expect(diff).toEqual([{ kind: "add", text: "print(1)" }]);
  });

  it("parses a Codex fileChange unified diff field", () => {
    const diff = extractDiff({ type: "fileChange", diff: "--- a\n+++ b\n@@\n-old\n+new\n context" });
    expect(diff).toEqual([
      { kind: "remove", text: "old" },
      { kind: "add", text: "new" },
      { kind: "context", text: "context" },
    ]);
  });

  it("does not treat a plain Bash command as a diff", () => {
    expect(extractDiff({ command: "pytest -q" })).toBeNull();
  });

  it("parses standalone unified diff text", () => {
    expect(unifiedDiffToLines("+added\n-removed\n unchanged")).toEqual([
      { kind: "add", text: "added" },
      { kind: "remove", text: "removed" },
      { kind: "context", text: "unchanged" },
    ]);
  });
});

describe("persistent bilingual copy", () => {
  it("ships equivalent English and Spanish navigation", () => {
    expect(translate("en", "newTask")).toBe("New task");
    expect(translate("es", "newTask")).toBe("Nueva tarea");
  });
});
