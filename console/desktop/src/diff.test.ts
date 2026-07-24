import { describe, expect, it } from "vitest";
import { lineDiff } from "./diff";

describe("lineDiff", () => {
  it("marks unchanged lines as context", () => {
    const lines = lineDiff("a\nb\nc", "a\nb\nc");
    expect(lines.every((line) => line.kind === "context")).toBe(true);
  });

  it("detects a single-line replacement", () => {
    const lines = lineDiff("a\nb\nc", "a\nX\nc");
    expect(lines).toEqual([
      { kind: "context", text: "a" },
      { kind: "remove", text: "b" },
      { kind: "add", text: "X" },
      { kind: "context", text: "c" },
    ]);
  });

  it("detects a pure insertion", () => {
    const lines = lineDiff("a\nc", "a\nb\nc");
    expect(lines).toEqual([
      { kind: "context", text: "a" },
      { kind: "add", text: "b" },
      { kind: "context", text: "c" },
    ]);
  });
});
