import { CaretDown, CaretRight, CheckSquare, Sparkle, Terminal, UsersThree, WarningCircle } from "@phosphor-icons/react";
import { lazy, Suspense, useEffect, useState } from "react";
import type { AgentEvent } from "./types";
import { Language } from "./i18n";
import { DiffLine, lineDiff } from "./diff";

const MessageContent = lazy(() => import("./MessageContent").then((module) => ({ default: module.MessageContent })));

export type ToolStatus = "running" | "done" | "error";

export type TimelineItem =
  | { kind: "user"; id: string; text: string }
  | { kind: "assistant"; id: string; text: string; streaming?: boolean }
  | { kind: "thinking"; id: string; text: string; label: "thinking" | "reasoning"; streaming?: boolean }
  | {
      kind: "tool";
      id: string;
      name: string;
      input: unknown;
      status: ToolStatus;
      output: string;
      isError: boolean;
      startedAt: string;
    }
  | {
      kind: "subagent";
      id: string;
      taskId: string;
      description: string;
      status: ToolStatus;
      lastToolName?: string;
      summary?: string;
    }
  | { kind: "plan"; id: string; steps: Array<{ label: string; status?: string }> }
  | { kind: "error"; id: string; text: string };

function toolLabel(data: Record<string, unknown>): { id: string; name: string; input: unknown } {
  const tool = data.tool as Record<string, unknown> | undefined;
  if (tool) return { id: String(tool.id ?? ""), name: String(tool.name ?? "tool"), input: tool.input };
  const item = data.item as Record<string, unknown> | undefined;
  if (item) {
    return {
      id: String(item.id ?? ""),
      name: String(item.command ?? item.tool ?? item.type ?? "tool"),
      input: item,
    };
  }
  return { id: "", name: "tool", input: undefined };
}

function toolResult(data: Record<string, unknown>): { id: string; output: string; isError: boolean } {
  const toolResult = data.tool_result as Record<string, unknown> | undefined;
  if (toolResult) {
    const content = toolResult.content;
    return {
      id: String(toolResult.tool_use_id ?? ""),
      output: typeof content === "string" ? content : JSON.stringify(content ?? "", null, 2),
      isError: Boolean(toolResult.is_error),
    };
  }
  const item = data.item as Record<string, unknown> | undefined;
  if (item) {
    return {
      id: String(item.id ?? ""),
      output: String(item.output ?? item.status ?? ""),
      isError: String(item.status ?? "") === "failed",
    };
  }
  return { id: "", output: "", isError: false };
}

function planSteps(data: Record<string, unknown>): Array<{ label: string; status?: string }> {
  const plan = data.plan;
  if (Array.isArray(plan)) {
    return plan.map((entry) => {
      if (entry && typeof entry === "object") {
        const record = entry as Record<string, unknown>;
        return { label: String(record.step ?? record.title ?? record.text ?? ""), status: record.status ? String(record.status) : undefined };
      }
      return { label: String(entry) };
    });
  }
  return [];
}

export function buildTimeline(events: AgentEvent[]): TimelineItem[] {
  const items: TimelineItem[] = [];
  const toolIndex = new Map<string, number>();
  let textBuffer = "";
  let textId = "";
  let reasoningBuffer = "";
  let reasoningId = "";

  const flushText = () => {
    if (textBuffer) items.push({ kind: "assistant", id: textId, text: textBuffer, streaming: true });
    textBuffer = "";
    textId = "";
  };
  const flushReasoning = () => {
    if (reasoningBuffer) items.push({ kind: "thinking", id: reasoningId, text: reasoningBuffer, label: "reasoning", streaming: true });
    reasoningBuffer = "";
    reasoningId = "";
  };

  for (const event of events) {
    // assistant_message carries the final, complete answer for a turn that
    // streamed via assistant_delta — discard the partial buffer instead of
    // flushing it, or the same answer renders twice.
    if (event.type !== "assistant_delta" && event.type !== "assistant_message" && textBuffer) flushText();
    if (event.type !== "reasoning" && reasoningBuffer) flushReasoning();

    switch (event.type) {
      case "user_message":
        items.push({ kind: "user", id: event.id, text: event.text });
        break;
      case "assistant_delta":
        textId ||= event.id;
        textBuffer += event.text;
        break;
      case "assistant_message":
        textBuffer = "";
        textId = "";
        items.push({ kind: "assistant", id: event.id, text: event.text });
        break;
      case "reasoning":
        reasoningId ||= event.id;
        reasoningBuffer += event.text;
        break;
      case "thinking":
        items.push({ kind: "thinking", id: event.id, text: event.text, label: "thinking" });
        break;
      case "tool_started": {
        const { id, name, input } = toolLabel(event.data);
        const item: TimelineItem = { kind: "tool", id: event.id, name, input, status: "running", output: "", isError: false, startedAt: event.created_at };
        items.push(item);
        if (id) toolIndex.set(id, items.length - 1);
        break;
      }
      case "tool_completed": {
        const { id, output, isError } = toolResult(event.data);
        const index = id ? toolIndex.get(id) : undefined;
        if (index !== undefined) {
          const current = items[index];
          if (current.kind === "tool") {
            items[index] = { ...current, status: isError ? "error" : "done", output, isError };
            break;
          }
        }
        items.push({ kind: "tool", id: event.id, name: "tool", input: undefined, status: isError ? "error" : "done", output, isError, startedAt: event.created_at });
        break;
      }
      case "command_output": {
        const itemId = event.data.item_id ? String(event.data.item_id) : "";
        const index = itemId ? toolIndex.get(itemId) : undefined;
        if (index !== undefined && items[index].kind === "tool") {
          const current = items[index] as Extract<TimelineItem, { kind: "tool" }>;
          items[index] = { ...current, output: current.output + event.text };
        }
        break;
      }
      case "subagent_started": {
        const taskId = String(event.data.task_id ?? "");
        items.push({ kind: "subagent", id: event.id, taskId, description: event.text, status: "running" });
        if (taskId) toolIndex.set(`task:${taskId}`, items.length - 1);
        break;
      }
      case "subagent_progress": {
        const taskId = String(event.data.task_id ?? "");
        const index = toolIndex.get(`task:${taskId}`);
        if (index !== undefined && items[index].kind === "subagent") {
          const current = items[index] as Extract<TimelineItem, { kind: "subagent" }>;
          items[index] = { ...current, description: event.text, lastToolName: event.data.last_tool_name ? String(event.data.last_tool_name) : current.lastToolName };
          break;
        }
        items.push({ kind: "subagent", id: event.id, taskId, description: event.text, status: "running" });
        break;
      }
      case "subagent_completed": {
        const taskId = String(event.data.task_id ?? "");
        const index = toolIndex.get(`task:${taskId}`);
        if (index !== undefined && items[index].kind === "subagent") {
          const current = items[index] as Extract<TimelineItem, { kind: "subagent" }>;
          items[index] = { ...current, status: "done", summary: event.text };
          break;
        }
        items.push({ kind: "subagent", id: event.id, taskId, description: event.text, status: "done", summary: event.text });
        break;
      }
      case "plan_updated":
        items.push({ kind: "plan", id: event.id, steps: planSteps(event.data) });
        break;
      case "error":
        items.push({ kind: "error", id: event.id, text: event.text });
        break;
      default:
        break;
    }
  }
  flushText();
  flushReasoning();
  return items;
}

function compact(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  return JSON.stringify(value, null, 2);
}

export function unifiedDiffToLines(text: string): DiffLine[] {
  return text
    .split("\n")
    .filter((line) => !line.startsWith("+++") && !line.startsWith("---") && !line.startsWith("@@"))
    .map((line) => {
      if (line.startsWith("+")) return { kind: "add", text: line.slice(1) };
      if (line.startsWith("-")) return { kind: "remove", text: line.slice(1) };
      return { kind: "context", text: line.replace(/^ /, "") };
    });
}

// Detects a diffable tool call from its input shape rather than its name,
// since Claude (Edit/Write) and Codex (fileChange) disagree on both.
export function extractDiff(input: unknown): DiffLine[] | null {
  if (!input || typeof input !== "object") return null;
  const record = input as Record<string, unknown>;
  if (typeof record.old_string === "string" && typeof record.new_string === "string") {
    return lineDiff(record.old_string, record.new_string);
  }
  const unified = record.diff ?? record.unifiedDiff ?? record.patch;
  if (typeof unified === "string" && unified.trim()) {
    return unifiedDiffToLines(unified);
  }
  if (typeof record.content === "string" && typeof record.file_path === "string") {
    return lineDiff("", record.content);
  }
  return null;
}

function DiffBlock({ lines }: { lines: DiffLine[] }) {
  return (
    <pre className="timeline-diff">
      {lines.map((line, index) => (
        <span className={`diff-${line.kind}`} key={index}>
          {line.kind === "add" ? "+" : line.kind === "remove" ? "-" : " "}
          {line.text}
          {"\n"}
        </span>
      ))}
    </pre>
  );
}

function useElapsedSeconds(startedAt: string, live: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!live) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [live]);
  return Math.max(0, Math.round((now - new Date(startedAt).getTime()) / 1000));
}

function ToolCard({ item, language }: { item: Extract<TimelineItem, { kind: "tool" }>; language: Language }) {
  const [open, setOpen] = useState(false);
  const diff = extractDiff(item.input);
  const elapsed = useElapsedSeconds(item.startedAt, item.status === "running");
  return (
    <article className={`timeline-tool status-${item.status}`}>
      <button type="button" className="timeline-tool-head" onClick={() => setOpen((value) => !value)}>
        {open ? <CaretDown size={12} /> : <CaretRight size={12} />}
        <Terminal size={14} />
        <span>{item.name}</span>
        {item.status === "running" && <small>{elapsed}s</small>}
        <em>{item.status === "running" ? (language === "es" ? "ejecutando" : "running") : item.status === "error" ? (language === "es" ? "error" : "failed") : (language === "es" ? "listo" : "done")}</em>
      </button>
      {open && (
        <div className="timeline-tool-body">
          {diff ? <DiffBlock lines={diff} /> : item.input !== undefined && <pre>{compact(item.input)}</pre>}
          {item.output && <pre className={item.isError ? "is-error" : ""}>{item.output}</pre>}
        </div>
      )}
    </article>
  );
}

function SubagentCard({ item, language }: { item: Extract<TimelineItem, { kind: "subagent" }>; language: Language }) {
  return (
    <article className={`timeline-subagent status-${item.status}`}>
      <UsersThree size={14} />
      <div>
        <span>{language === "es" ? "Subagente" : "Subagent"}{item.lastToolName ? ` · ${item.lastToolName}` : ""}</span>
        <p>{item.summary || item.description}</p>
      </div>
    </article>
  );
}

function PlanCard({ item }: { item: Extract<TimelineItem, { kind: "plan" }> }) {
  return (
    <article className="timeline-plan">
      <header>
        <CheckSquare size={14} />
        <span>Plan</span>
      </header>
      <ul>
        {item.steps.map((step, index) => (
          <li key={index} className={step.status ? `status-${step.status}` : ""}>{step.label}</li>
        ))}
      </ul>
    </article>
  );
}

export interface AskUserQuestionOption {
  label: string;
  description?: string;
}

export interface AskUserQuestionItem {
  question: string;
  header?: string;
  multiSelect?: boolean;
  options: AskUserQuestionOption[];
}

export function AskUserQuestionPanel({
  questions,
  language,
  onSubmit,
  onDeny,
}: {
  questions: AskUserQuestionItem[];
  language: Language;
  onSubmit: (answers: Record<string, string>) => void;
  onDeny: () => void;
}) {
  const [selected, setSelected] = useState<Record<string, string[]>>({});

  function toggle(question: string, label: string, multiSelect: boolean) {
    setSelected((current) => {
      const chosen = current[question] || [];
      if (multiSelect) {
        return {
          ...current,
          [question]: chosen.includes(label) ? chosen.filter((value) => value !== label) : [...chosen, label],
        };
      }
      return { ...current, [question]: [label] };
    });
  }

  const answered = questions.every((entry) => (selected[entry.question] || []).length > 0);

  return (
    <section className="approval-panel ask-user-question">
      <div><strong>{language === "es" ? "El agente necesita una respuesta" : "The agent needs an answer"}</strong></div>
      {questions.map((entry) => (
        <fieldset key={entry.question}>
          <legend>{entry.header || entry.question}</legend>
          <p>{entry.question}</p>
          <div className="ask-user-question-options">
            {entry.options.map((option) => {
              const checked = (selected[entry.question] || []).includes(option.label);
              return (
                <label className={checked ? "active" : ""} key={option.label}>
                  <input
                    type={entry.multiSelect ? "checkbox" : "radio"}
                    name={entry.question}
                    checked={checked}
                    onChange={() => toggle(entry.question, option.label, Boolean(entry.multiSelect))}
                  />
                  <span><strong>{option.label}</strong>{option.description && <small>{option.description}</small>}</span>
                </label>
              );
            })}
          </div>
        </fieldset>
      ))}
      <div>
        <button onClick={onDeny}>{language === "es" ? "Cancelar" : "Cancel"}</button>
        <button
          className="primary"
          disabled={!answered}
          onClick={() =>
            onSubmit(
              Object.fromEntries(
                questions.map((entry) => [entry.question, (selected[entry.question] || []).join(", ")]),
              ),
            )
          }
        >
          {language === "es" ? "Responder" : "Answer"}
        </button>
      </div>
    </section>
  );
}

export function Timeline({ items, provider, language }: { items: TimelineItem[]; provider: string; language: Language }) {
  return (
    <>
      {items.map((item) => {
        switch (item.kind) {
          case "user":
            return (
              <article className="message user" key={item.id}>
                <span>YOU</span>
                <Suspense fallback={<div>{item.text}</div>}><MessageContent text={item.text} /></Suspense>
              </article>
            );
          case "assistant":
            return (
              <article className="message assistant" key={item.id}>
                <span>{provider.toUpperCase()}</span>
                <Suspense fallback={<div>{item.text}</div>}><MessageContent text={item.text} /></Suspense>
                {item.streaming && <i />}
              </article>
            );
          case "thinking":
            return (
              <article className="timeline-thinking" key={item.id}>
                <Sparkle size={13} />
                <p>{item.text}</p>
              </article>
            );
          case "tool":
            return <ToolCard item={item} language={language} key={item.id} />;
          case "subagent":
            return <SubagentCard item={item} language={language} key={item.id} />;
          case "plan":
            return <PlanCard item={item} key={item.id} />;
          case "error":
            return (
              <article className="timeline-error" key={item.id}>
                <WarningCircle size={14} />
                <p>{item.text}</p>
              </article>
            );
          default:
            return null;
        }
      })}
    </>
  );
}
