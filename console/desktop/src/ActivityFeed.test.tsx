// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AskUserQuestionPanel, buildTimeline } from "./ActivityFeed";
import type { AgentEvent } from "./types";

describe("structured agent questions", () => {
  it("returns Codex question ids and supports a custom answer", () => {
    const onSubmit = vi.fn();
    render(
      <AskUserQuestionPanel
        language="es"
        questions={[
          {
            id: "motor",
            header: "Motor",
            question: "¿Qué motor usamos?",
            options: [{ label: "F-class", description: "Menor impulso" }],
            isOther: true,
          },
        ]}
        onDeny={() => {}}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.change(screen.getByLabelText("Especificar otra respuesta"), { target: { value: "G-class" } });
    fireEvent.click(screen.getByRole("button", { name: "Responder" }));

    expect(onSubmit).toHaveBeenCalledWith({ motor: "G-class" });
  });

  it("uses a protected free-form field for a secret prompt", () => {
    render(
      <AskUserQuestionPanel
        language="en"
        questions={[
          {
            id: "token",
            question: "Provide the token",
            options: [],
            isSecret: true,
          },
        ]}
        onDeny={() => {}}
        onSubmit={() => {}}
      />,
    );

    expect(screen.getByLabelText("Provide the token").getAttribute("type")).toBe("password");
  });

  it("streams Codex MCP progress into its active tool entry", () => {
    const base = {
      session_id: "session-1",
      created_at: "2026-07-24T00:00:00Z",
      role: null,
      raw: {},
    };
    const timeline = buildTimeline([
      {
        ...base,
        id: "start",
        sequence: 1,
        type: "tool_started",
        text: "run_motor_sweep",
        data: { item: { id: "tool-1", type: "mcpToolCall", tool: "run_motor_sweep" } },
      },
      {
        ...base,
        id: "progress",
        sequence: 2,
        type: "tool_progress",
        text: "Simulating candidate 3 of 8",
        data: { item_id: "tool-1" },
      },
    ] as AgentEvent[]);

    expect(timeline[0]).toMatchObject({
      kind: "tool",
      status: "running",
      output: "Simulating candidate 3 of 8",
    });
  });
});
