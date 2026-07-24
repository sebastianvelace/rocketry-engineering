// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RunPlot } from "./RunPlot";
import type { RunRecord } from "./types";

vi.hoisted(() => {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: () => ({
      matches: false,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  });
});

const base: Omit<RunRecord, "kind" | "columns" | "rows" | "meta"> = {
  id: 1,
  created_at: "2026-07-24T00:00:00Z",
  note: "",
  row_count: 1,
  offset: 0,
};

describe("engineering run visualizations", () => {
  it("renders openMotor candidates as ranked engineering data", () => {
    const { container } = render(
      <RunPlot
        run={{
          ...base,
          kind: "MOTOR_SWEEP",
          meta: { n_viable: 1 },
          columns: [
            "core_mm",
            "n_segments",
            "peak_pressure_mpa",
            "peak_thrust_n",
            "impulse_ns",
            "burn_time_s",
            "designation",
          ],
          rows: [[12, 4, 3.324, 138.2, 66.54, 0.499, "67F133"]],
        }}
      />,
    );

    expect(screen.getByText("67F133")).not.toBeNull();
    expect(container.textContent).toContain("66.54 N·s");
    expect(container.textContent).toContain("138.2 N");
    expect(container.textContent).toContain("3.324 MPa");
  });

  it("adds engineering units to OpenRocket summary metrics", () => {
    render(
      <RunPlot
        run={{
          ...base,
          kind: "FLIGHT",
          meta: {},
          columns: ["metric", "value"],
          rows: [["apogee", 1503.3], ["mach", 0.826], ["margin", 2.38]],
          row_count: 3,
        }}
      />,
    );

    expect(screen.getByText("1,503.3")).not.toBeNull();
    expect(screen.getByText("m")).not.toBeNull();
    expect(screen.getByText("Ma")).not.toBeNull();
    expect(screen.getByText("cal")).not.toBeNull();
  });
});
