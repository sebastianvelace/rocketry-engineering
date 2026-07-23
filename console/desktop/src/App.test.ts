import { describe, expect, it } from "vitest";
import { activityEvents, conversationFrom } from "./App";
import { translate } from "./i18n";
import type { AgentEvent } from "./types";

function event(
  sequence: number,
  type: string,
  text: string,
  role: string | null = null,
): AgentEvent {
  return {
    sequence,
    id: `event-${sequence}`,
    session_id: "session-1",
    created_at: "2026-07-23T00:00:00Z",
    type,
    role,
    text,
    data: {},
  };
}

describe("conversation event projection", () => {
  it("coalesces streaming deltas and replaces them with the final answer", () => {
    const projected = conversationFrom([
      event(1, "user_message", "Run the test", "user"),
      event(2, "assistant_delta", "Test "),
      event(3, "assistant_delta", "running"),
      event(4, "assistant_message", "Test passed", "assistant"),
    ]);

    expect(projected).toEqual([
      { id: "event-1", role: "user", text: "Run the test" },
      { id: "event-4", role: "assistant", text: "Test passed" },
    ]);
  });

  it("keeps incomplete streaming text visible", () => {
    const projected = conversationFrom([
      event(1, "assistant_delta", "Capturing"),
      event(2, "assistant_delta", "..."),
    ]);
    expect(projected[0]).toMatchObject({
      role: "assistant",
      text: "Capturing...",
      streaming: true,
    });
  });

  it("separates activity from conversation", () => {
    expect(
      activityEvents([
        event(1, "user_message", "hello"),
        event(2, "tool_started", "run_tests"),
        event(3, "command_output", "ok"),
      ]).map((item) => item.type),
    ).toEqual(["tool_started", "command_output"]);
  });
});

describe("persistent bilingual copy", () => {
  it("ships equivalent English and Spanish navigation", () => {
    expect(translate("en", "newTask")).toBe("New task");
    expect(translate("es", "newTask")).toBe("Nueva tarea");
  });
});
