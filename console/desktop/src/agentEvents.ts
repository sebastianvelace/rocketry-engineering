import type { AgentEvent } from "./types";

const RAW_LOG_EVENT_TYPES = [
  "tool_started",
  "tool_progress",
  "tool_completed",
  "command_output",
  "reasoning",
  "thinking",
  "subagent_started",
  "subagent_progress",
  "subagent_completed",
  "plan_updated",
  "notice",
  "error",
];

export function activityEvents(events: AgentEvent[]): AgentEvent[] {
  return events.filter((event) => RAW_LOG_EVENT_TYPES.includes(event.type));
}

export function extractRunId(value: unknown, depth = 0): number | null {
  if (depth > 6 || value === null || value === undefined) return null;
  if (typeof value === "string") {
    if (!value.includes("run_id")) return null;
    try {
      return extractRunId(JSON.parse(value), depth + 1);
    } catch {
      const match = value.match(/["']?run_id["']?\s*[:=]\s*(\d+)/);
      return match ? Number(match[1]) : null;
    }
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = extractRunId(item, depth + 1);
      if (found !== null) return found;
    }
    return null;
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    const direct = record.run_id;
    if (typeof direct === "number" && Number.isInteger(direct)) return direct;
    if (typeof direct === "string" && /^\d+$/.test(direct)) return Number(direct);
    for (const nested of Object.values(record)) {
      const found = extractRunId(nested, depth + 1);
      if (found !== null) return found;
    }
  }
  return null;
}
