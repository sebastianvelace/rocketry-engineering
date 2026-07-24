import { useEffect, useMemo, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import type { RunRecord } from "./types";

interface RunPlotProps {
  run: RunRecord;
}

function numericColumns(run: RunRecord): number[] {
  return run.columns
    .map((_, index) => index)
    .filter((index) =>
      run.rows.some((row) => typeof row[index] === "number" && Number.isFinite(row[index])),
    );
}

const flightUnits: Record<string, string> = {
  apogee: "m",
  mach: "Ma",
  vmax: "m/s",
  mass: "g",
  margin: "cal",
  margin_bo: "cal",
  rail: "m/s",
  wind: "m/s",
};

function MotorCandidateView({ run }: RunPlotProps) {
  const host = useRef<HTMLDivElement>(null);
  const column = (name: string) => run.columns.indexOf(name);
  const burnIndex = column("burn_time_s");
  const impulseIndex = column("impulse_ns");
  const designationIndex = column("designation");
  const pressureIndex = column("peak_pressure_mpa");
  const thrustIndex = column("peak_thrust_n");
  const candidates = useMemo(
    () => run.rows
      .filter((row) => (
        burnIndex >= 0
        && impulseIndex >= 0
        && typeof row[burnIndex] === "number"
        && typeof row[impulseIndex] === "number"
      ))
      .sort((left, right) => Number(left[burnIndex]) - Number(right[burnIndex])),
    [burnIndex, impulseIndex, run.rows],
  );

  useEffect(() => {
    if (!host.current || candidates.length < 2) return;
    const element = host.current;
    const plot = new uPlot(
      {
        width: Math.max(320, element.clientWidth),
        height: Math.max(230, element.clientHeight),
        cursor: { drag: { x: true, y: false } },
        legend: { show: true },
        axes: [
          {
            label: "burn time (s)",
            stroke: "#768292",
            grid: { stroke: "#242b35", width: 1 },
            ticks: { stroke: "#303846" },
          },
          {
            label: "impulse (N·s)",
            stroke: "#768292",
            grid: { stroke: "#242b35", width: 1 },
            ticks: { stroke: "#303846" },
          },
        ],
        scales: { x: { time: false } },
        series: [
          { label: "burn time (s)" },
          {
            label: "impulse (N·s)",
            stroke: "#ef4444",
            width: 1.5,
            points: { show: true, size: 7, fill: "#ef4444", stroke: "#ffafb2" },
          },
        ],
      },
      [
        candidates.map((row) => Number(row[burnIndex])),
        candidates.map((row) => Number(row[impulseIndex])),
      ],
      element,
    );
    const observer = new ResizeObserver(([entry]) => {
      plot.setSize({
        width: Math.max(320, Math.floor(entry.contentRect.width)),
        height: Math.max(230, Math.floor(entry.contentRect.height)),
      });
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
      plot.destroy();
    };
  }, [burnIndex, candidates, impulseIndex]);

  const best = [...run.rows].sort((a, b) => Number(b[impulseIndex] || 0) - Number(a[impulseIndex] || 0))[0];
  const maximum = (index: number) => index < 0 || !run.rows.length
    ? null
    : Math.max(...run.rows.map((row) => Number(row[index] || 0)));
  return (
    <div className="motor-result">
      <div className="motor-result-summary">
        <div><span>viable</span><strong>{Number(run.meta.n_viable ?? run.rows.length).toLocaleString()}</strong></div>
        <div><span>best impulse</span><strong>{best && impulseIndex >= 0 ? Number(best[impulseIndex]).toLocaleString() : "n/a"} <small>N·s</small></strong></div>
        <div><span>peak thrust</span><strong>{maximum(thrustIndex)?.toLocaleString() ?? "n/a"} <small>N</small></strong></div>
        <div><span>peak pressure</span><strong>{maximum(pressureIndex)?.toLocaleString() ?? "n/a"} <small>MPa</small></strong></div>
      </div>
      {candidates.length > 1 && <div className="motor-envelope-plot" ref={host} />}
      <div className="motor-candidates">
        <header><span>candidate</span><span>geometry</span><span>impulse</span><span>burn</span><span>pressure</span></header>
        {[...run.rows]
          .sort((a, b) => Number(b[impulseIndex] || 0) - Number(a[impulseIndex] || 0))
          .slice(0, 8)
          .map((row, index) => (
            <div key={`${String(row[designationIndex])}-${index}`}>
              <strong>{designationIndex >= 0 ? String(row[designationIndex]) : `#${index + 1}`}</strong>
              <span>{String(row[column("core_mm")])} mm × {String(row[column("n_segments")])}</span>
              <span>{String(row[impulseIndex])} N·s</span>
              <span>{String(row[burnIndex])} s</span>
              <span>{String(row[pressureIndex])} MPa</span>
            </div>
          ))}
      </div>
    </div>
  );
}

export function RunPlot({ run }: RunPlotProps) {
  const host = useRef<HTMLDivElement>(null);
  const numeric = useMemo(() => numericColumns(run), [run]);
  const motorSweep = run.kind === "MOTOR_SWEEP";

  const categoricalMetrics =
    numeric.length === 1 &&
    run.rows.some((row) => typeof row[0] === "string" && typeof row[numeric[0]] === "number");

  useEffect(() => {
    if (!host.current || numeric.length === 0 || categoricalMetrics || motorSweep) return;
    const element = host.current;
    const xIndex = numeric[0];
    const yIndexes = numeric.slice(1, 5);
    const plottedY = yIndexes.length > 0 ? yIndexes : [xIndex];
    const rows = run.rows.filter((row) =>
      [xIndex, ...plottedY].every((index) => typeof row[index] === "number"),
    );
    const x =
      yIndexes.length > 0
        ? rows.map((row) => Number(row[xIndex]))
        : rows.map((_, index) => index);
    const data: uPlot.AlignedData = [
      x,
      ...plottedY.map((index) => rows.map((row) => Number(row[index]))),
    ];
    const colors = ["#ef4444", "#88a4c2", "#d4d9e0", "#8b6f73"];
    const plot = new uPlot(
      {
        width: Math.max(320, element.clientWidth),
        height: Math.max(240, element.clientHeight),
        cursor: { drag: { x: true, y: false } },
        legend: { show: true },
        axes: [
          {
            stroke: "#768292",
            grid: { stroke: "#242b35", width: 1 },
            ticks: { stroke: "#303846" },
          },
          {
            stroke: "#768292",
            grid: { stroke: "#242b35", width: 1 },
            ticks: { stroke: "#303846" },
          },
        ],
        scales: { x: { time: false } },
        series: [
          { label: yIndexes.length > 0 ? run.columns[xIndex] : "sample" },
          ...plottedY.map((index, seriesIndex) => ({
            label: run.columns[index] || `column ${index + 1}`,
            stroke: colors[seriesIndex],
            width: seriesIndex === 0 ? 2 : 1.5,
            points: { show: false },
          })),
        ],
      },
      data,
      element,
    );
    const observer = new ResizeObserver(([entry]) => {
      plot.setSize({
        width: Math.max(320, Math.floor(entry.contentRect.width)),
        height: Math.max(240, Math.floor(entry.contentRect.height)),
      });
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
      plot.destroy();
    };
  }, [categoricalMetrics, motorSweep, numeric, run]);

  if (motorSweep) {
    return <MotorCandidateView run={run} />;
  }
  if (numeric.length === 0) {
    return <div className="plot-empty">This run has no numeric series.</div>;
  }
  if (categoricalMetrics) {
    return (
      <div className="metric-field">
        {run.rows
          .filter((row) => typeof row[0] === "string" && typeof row[numeric[0]] === "number")
          .map((row) => (
            <div key={String(row[0])}>
              <span>{String(row[0]).replaceAll("_", " ")}</span>
              <strong>
                {Number(row[numeric[0]]).toLocaleString(undefined, { maximumFractionDigits: 3 })}
                {flightUnits[String(row[0])] && <small>{flightUnits[String(row[0])]}</small>}
              </strong>
            </div>
          ))}
      </div>
    );
  }
  return <div className="run-plot" ref={host} />;
}
