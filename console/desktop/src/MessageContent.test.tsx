// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MessageContent } from "./MessageContent";

describe("agent markdown", () => {
  it("renders emphasis and lists instead of exposing markdown punctuation", () => {
    render(
      <MessageContent text={"**Verified**\n\n- First check\n- Second check"} />,
    );

    expect(screen.getByText("Verified").tagName).toBe("STRONG");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByText("**Verified**")).toBeNull();
  });

  it("does not execute raw HTML from a provider message", () => {
    const { container } = render(
      <MessageContent text={'<script>alert("unsafe")</script>Safe'} />,
    );

    expect(container.querySelector("script")).toBeNull();
  });
});
