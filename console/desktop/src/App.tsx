import {
  ArrowClockwise,
  ChartLine,
  Check,
  CircleNotch,
  Code,
  DownloadSimple,
  Flask,
  FolderOpen,
  Plus,
  Pulse,
  Robot,
  Stop,
  X,
} from "@phosphor-icons/react";
import { AnimatePresence, MotionConfig, motion, useReducedMotion } from "motion/react";
import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { GatewayApi, connectGateway } from "./api";
import {
  CopyKey,
  eventLabel,
  Language,
  statusLabel,
  translate,
} from "./i18n";
import { RunPlot } from "./RunPlot";
import type {
  AgentEvent,
  Approval,
  Artifact,
  EngineeringStatus,
  Provider,
  RunRecord,
  RunSummary,
  Session,
} from "./types";

type ResultTab = "runs" | "activity" | "artifacts";

interface ConversationItem {
  id: string;
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
}

export function conversationFrom(events: AgentEvent[]): ConversationItem[] {
  const messages: ConversationItem[] = [];
  let streaming = "";
  let streamingId = "";
  for (const event of events) {
    if (event.type === "user_message") {
      if (streaming) {
        messages.push({ id: streamingId, role: "assistant", text: streaming, streaming: true });
        streaming = "";
      }
      messages.push({ id: event.id, role: "user", text: event.text });
    } else if (event.type === "assistant_delta") {
      streamingId ||= event.id;
      streaming += event.text;
    } else if (event.type === "assistant_message") {
      streaming = "";
      streamingId = "";
      messages.push({ id: event.id, role: "assistant", text: event.text });
    }
  }
  if (streaming) {
    messages.push({ id: streamingId, role: "assistant", text: streaming, streaming: true });
  }
  return messages;
}

export function activityEvents(events: AgentEvent[]): AgentEvent[] {
  return events.filter((event) =>
    [
      "tool_started",
      "tool_progress",
      "tool_completed",
      "command_output",
      "reasoning",
      "error",
    ].includes(event.type),
  );
}

function compactDetail(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  return JSON.stringify(value, null, 2);
}

export default function App() {
  const reducedMotion = useReducedMotion();
  const [language, setLanguage] = useState<Language>(
    () => (localStorage.getItem("rocketry-language") as Language) || "es",
  );
  const t = useCallback(
    (key: CopyKey) => translate(language, key),
    [language],
  );
  const [api, setApi] = useState<GatewayApi | null>(null);
  const [connectionError, setConnectionError] = useState("");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [status, setStatus] = useState<EngineeringStatus | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState<RunRecord | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [tab, setTab] = useState<ResultTab>("runs");
  const [composer, setComposer] = useState("");
  const [newTaskOpen, setNewTaskOpen] = useState(false);
  const [newProvider, setNewProvider] = useState<Provider>("codex");
  const [newTitle, setNewTitle] = useState("");
  const [socketConnected, setSocketConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const feedEnd = useRef<HTMLDivElement>(null);
  const latestRunId = useRef<number | null>(null);

  const selectedSession = sessions.find((session) => session.id === selectedId) || null;
  const conversation = useMemo(() => conversationFrom(events), [events]);
  const activity = useMemo(() => activityEvents(events), [events]);

  const loadGateway = useCallback(async () => {
    setConnectionError("");
    try {
      const client = new GatewayApi(await connectGateway());
      setApi(client);
      const [nextSessions, nextStatus, nextRuns, nextArtifacts] = await Promise.all([
        client.sessions(),
        client.status(),
        client.runs(),
        client.artifacts(),
      ]);
      setSessions(nextSessions);
      setStatus(nextStatus);
      setRuns(nextRuns);
      latestRunId.current = nextRuns[0]?.id || null;
      setArtifacts(nextArtifacts);
      setSelectedId((current) => current || nextSessions[0]?.id || null);
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : String(error));
    }
  }, []);

  useEffect(() => {
    void loadGateway();
  }, [loadGateway]);

  useEffect(() => {
    localStorage.setItem("rocketry-language", language);
    document.documentElement.lang = language;
  }, [language]);

  const refreshEngineering = useCallback(async () => {
    if (!api) return;
    const [nextStatus, nextRuns, nextArtifacts] = await Promise.all([
      api.status(),
      api.runs(),
      api.artifacts(),
    ]);
    setStatus(nextStatus);
    setRuns(nextRuns);
    setArtifacts(nextArtifacts);
    const newest = nextRuns[0]?.id || null;
    if (newest !== null && newest !== latestRunId.current) {
      setSelectedRun(await api.run(newest));
    }
    latestRunId.current = newest;
  }, [api]);

  const refreshSessions = useCallback(async () => {
    if (api) setSessions(await api.sessions());
  }, [api]);

  useEffect(() => {
    if (!api || !selectedId) {
      setEvents([]);
      return;
    }
    let active = true;
    let unsubscribe = () => {};
    let reconnectTimer: number | undefined;
    let lastSequence = 0;

    const connect = async () => {
      const history = await api.events(selectedId);
      if (!active) return;
      setEvents(history);
      lastSequence = history.at(-1)?.sequence || 0;
      setApprovals(await api.approvals(selectedId));
      unsubscribe = api.subscribe(
        selectedId,
        lastSequence,
        (event) => {
          lastSequence = Math.max(lastSequence, event.sequence);
          setEvents((current) =>
            current.some((item) => item.id === event.id) ? current : [...current, event],
          );
          if (event.type === "approval_requested" || event.type === "approval_resolved") {
            void api.approvals(selectedId).then(setApprovals);
          }
          if (event.type === "tool_completed") {
            void refreshEngineering();
          }
          if (event.type === "session" || event.type === "error") {
            void refreshSessions();
          }
        },
        (connected) => {
          setSocketConnected(connected);
          if (!connected && active) {
            window.clearTimeout(reconnectTimer);
            reconnectTimer = window.setTimeout(connect, 1200);
          }
        },
      );
    };
    void connect().catch((error) => setConnectionError(String(error)));
    return () => {
      active = false;
      window.clearTimeout(reconnectTimer);
      unsubscribe();
      setSocketConnected(false);
    };
  }, [api, selectedId, refreshEngineering, refreshSessions]);

  useEffect(() => {
    if (!reducedMotion) feedEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation.length, reducedMotion]);

  useEffect(() => {
    if (!api || runs.length === 0) {
      setSelectedRun(null);
      return;
    }
    const nextId = selectedRun && runs.some((run) => run.id === selectedRun.id)
      ? selectedRun.id
      : runs[0].id;
    void api.run(nextId).then(setSelectedRun);
  }, [api, runs, selectedRun?.id]);

  async function createTask(event: FormEvent) {
    event.preventDefault();
    if (!api) return;
    setBusy(true);
    try {
      const session = await api.createSession(
        newProvider,
        newTitle.trim() || t("newTask"),
      );
      setSessions((current) => [session, ...current]);
      setSelectedId(session.id);
      setNewTaskOpen(false);
      setNewTitle("");
    } finally {
      setBusy(false);
    }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    if (!api || !selectedId || !composer.trim() || busy) return;
    const text = composer.trim();
    setComposer("");
    setBusy(true);
    try {
      await api.send(selectedId, text);
      await refreshSessions();
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : String(error));
      setComposer(text);
    } finally {
      setBusy(false);
    }
  }

  async function resolveApproval(
    approval: Approval,
    approved: boolean,
    forSession = false,
  ) {
    if (!api) return;
    await api.resolveApproval(approval.id, approved, forSession);
    setApprovals(await api.approvals(approval.session_id));
  }

  if (!api) {
    return (
      <main className="boot-screen">
        <div className="brand-lockup"><span>R/</span> ROCKETRY</div>
        {connectionError ? (
          <>
            <p>{t("gatewayError")}</p>
            <code>{connectionError}</code>
            <button className="button primary" onClick={() => void loadGateway()}>
              <ArrowClockwise size={17} /> {t("retry")}
            </button>
          </>
        ) : (
          <div className="boot-line"><CircleNotch className="spin" size={18} /> Starting local gateway</div>
        )}
      </main>
    );
  }

  const isRunning = selectedSession?.status === "running"
    || selectedSession?.status === "waiting_approval"
    || selectedSession?.status === "interrupting";

  return (
    <MotionConfig reducedMotion="user">
      <div className="app-shell">
        <aside className="session-rail">
          <header className="brand-lockup"><span>R/</span> ROCKETRY</header>
          <div className="rail-heading">
            <span>{t("sessions")}</span>
            <motion.button
              whileTap={{ scale: 0.94 }}
              className="icon-button"
              aria-label={t("newTask")}
              onClick={() => setNewTaskOpen(true)}
            >
              <Plus size={17} weight="bold" />
            </motion.button>
          </div>
          <nav className="session-list" aria-label={t("sessions")}>
            {sessions.length === 0 && <p className="empty-rail">{t("noSessions")}</p>}
            {sessions.map((session) => (
              <button
                key={session.id}
                className={`session-row ${selectedId === session.id ? "active" : ""}`}
                onClick={() => setSelectedId(session.id)}
              >
                <span className="provider-mark">
                  {session.provider === "codex" ? <Code size={16} /> : <Robot size={16} />}
                </span>
                <span>
                  <strong>{session.title}</strong>
                  <small>{session.provider} / {statusLabel(language, session.status)}</small>
                </span>
              </button>
            ))}
          </nav>
          <footer className="rail-footer">
            <div className="language-control" aria-label="Language">
              {(["es", "en"] as Language[]).map((item) => (
                <button
                  key={item}
                  className={language === item ? "active" : ""}
                  onClick={() => setLanguage(item)}
                >
                  {item.toUpperCase()}
                </button>
              ))}
            </div>
            <div className="hardware-line">
              <span data-online={Boolean(status?.ports.length)} />
              {status?.ports.length ? t("connected") : t("disconnected")}
            </div>
            <small>{status?.saved_runs ?? 0} {t("savedRuns")}</small>
          </footer>
        </aside>

        <main className="workbench">
          {!selectedSession ? (
            <section className="empty-workbench">
              <Robot size={28} />
              <h1>{t("selectSession")}</h1>
              <button className="button primary" onClick={() => setNewTaskOpen(true)}>
                <Plus size={17} /> {t("newTask")}
              </button>
            </section>
          ) : (
            <>
              <section className="conversation-pane">
                <header className="pane-header">
                  <div>
                    <p>{t("conversation")}</p>
                    <h1>{selectedSession.title}</h1>
                  </div>
                  <div className="agent-state">
                    <span className={socketConnected ? "online" : ""} />
                    {isRunning ? t("agentWorking") : t("agentReady")}
                  </div>
                </header>

                <div className="message-feed">
                  {conversation.length === 0 && (
                    <div className="empty-state">
                      <Flask size={22} />
                      <p>{t("noConversation")}</p>
                    </div>
                  )}
                  <AnimatePresence initial={false}>
                    {conversation.map((message) => (
                      <motion.article
                        key={message.id}
                        initial={reducedMotion ? false : { opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0 }}
                        className={`message ${message.role}`}
                      >
                        <span>{message.role === "user" ? "YOU" : selectedSession.provider.toUpperCase()}</span>
                        <div>{message.text}</div>
                        {message.streaming && <i aria-label="streaming" />}
                      </motion.article>
                    ))}
                  </AnimatePresence>
                  {approvals.map((approval) => (
                    <section className="approval-panel" key={approval.id}>
                      <div>
                        <strong>{t("needsApproval")}</strong>
                        <span>{approval.action}</span>
                      </div>
                      <pre>{compactDetail(approval.details)}</pre>
                      <div className="approval-actions">
                        <button onClick={() => void resolveApproval(approval, false)}>
                          <X size={16} /> {t("deny")}
                        </button>
                        <button onClick={() => void resolveApproval(approval, true)}>
                          <Check size={16} /> {t("approve")}
                        </button>
                        <button className="primary" onClick={() => void resolveApproval(approval, true, true)}>
                          <Check size={16} /> {t("approveSession")}
                        </button>
                      </div>
                    </section>
                  ))}
                  <div ref={feedEnd} />
                </div>

                <form className="composer" onSubmit={sendMessage}>
                  <label htmlFor="agent-message">{t("placeholder")}</label>
                  <textarea
                    id="agent-message"
                    rows={3}
                    value={composer}
                    onChange={(event) => setComposer(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        event.currentTarget.form?.requestSubmit();
                      }
                    }}
                    placeholder={t("placeholder")}
                    disabled={isRunning || busy}
                  />
                  <div>
                    <span>{selectedSession.provider} / {statusLabel(language, selectedSession.status)}</span>
                    {isRunning ? (
                      <motion.button
                        whileTap={{ scale: 0.97 }}
                        type="button"
                        className="button danger"
                        onClick={() => void api.interrupt(selectedSession.id)}
                      >
                        <Stop size={16} weight="fill" /> {t("stop")}
                      </motion.button>
                    ) : (
                      <motion.button
                        whileTap={{ scale: 0.97 }}
                        className="button primary"
                        disabled={!composer.trim() || busy}
                      >
                        {busy ? <CircleNotch className="spin" size={16} /> : <Check size={16} />}
                        {t("send")}
                      </motion.button>
                    )}
                  </div>
                </form>
              </section>

              <section className="results-pane">
                <header className="results-header">
                  <nav aria-label={t("results")}>
                    <button className={tab === "runs" ? "active" : ""} onClick={() => setTab("runs")}>
                      <ChartLine size={17} /> {t("runs")}
                    </button>
                    <button className={tab === "activity" ? "active" : ""} onClick={() => setTab("activity")}>
                      <Pulse size={17} /> {t("activity")}
                    </button>
                    <button className={tab === "artifacts" ? "active" : ""} onClick={() => setTab("artifacts")}>
                      <FolderOpen size={17} /> {t("artifacts")}
                    </button>
                  </nav>
                  <button className="icon-button" onClick={() => void refreshEngineering()} aria-label={t("retry")}>
                    <ArrowClockwise size={17} />
                  </button>
                </header>

                {tab === "runs" && (
                  <div className="runs-view">
                    {runs.length === 0 ? (
                      <div className="empty-state"><ChartLine size={22} /><p>{t("noRuns")}</p></div>
                    ) : (
                      <>
                        <div className="run-selector">
                          <label htmlFor="run-select">{t("results")}</label>
                          <select
                            id="run-select"
                            value={selectedRun?.id || runs[0].id}
                            onChange={(event) => void api.run(Number(event.target.value)).then(setSelectedRun)}
                          >
                            {runs.map((run) => (
                              <option value={run.id} key={run.id}>
                                #{run.id} {run.kind} {run.note}
                              </option>
                            ))}
                          </select>
                        </div>
                        {selectedRun && (
                          <motion.div
                            key={selectedRun.id}
                            initial={reducedMotion ? false : { opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="run-detail"
                          >
                            <div className="run-title">
                              <div><strong>{selectedRun.kind}</strong><span>#{selectedRun.id}</span></div>
                              <time>{new Date(selectedRun.created_at).toLocaleString(language)}</time>
                            </div>
                            <RunPlot run={selectedRun} />
                            <div className="run-meta">
                              <span>{selectedRun.row_count} {t("samples")}</span>
                              <span>{selectedRun.columns.length} {t("columns")}</span>
                              {Object.entries(selectedRun.meta).slice(0, 4).map(([key, value]) => (
                                <span key={key}>{key}: {compactDetail(value)}</span>
                              ))}
                            </div>
                          </motion.div>
                        )}
                      </>
                    )}
                  </div>
                )}

                {tab === "activity" && (
                  <div className="activity-view">
                    {activity.length === 0 && <div className="empty-state"><Pulse size={22} /><p>{t("noActivity")}</p></div>}
                    {activity.map((event) => (
                      <article className={`activity-row ${event.type}`} key={event.id}>
                        <span>{eventLabel(language, event.type)}</span>
                        <div>
                          <strong>{event.text || event.type}</strong>
                          {event.type === "command_output" && <pre>{event.text}</pre>}
                        </div>
                        <time>{new Date(event.created_at).toLocaleTimeString(language)}</time>
                      </article>
                    ))}
                  </div>
                )}

                {tab === "artifacts" && (
                  <div className="artifact-view">
                    {artifacts.length === 0 && <div className="empty-state"><FolderOpen size={22} /><p>{t("noRuns")}</p></div>}
                    {artifacts.map((artifact) => (
                      <article className="artifact-row" key={artifact.id}>
                        <div><strong>{artifact.kind}</strong><span>{artifact.media_type}</span></div>
                        <time>{new Date(artifact.created_at).toLocaleString(language)}</time>
                        <button
                          className="icon-button"
                          title={t("download")}
                          onClick={() => void api.openArtifact(artifact)}
                        >
                          <DownloadSimple size={17} />
                        </button>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}
        </main>
      </div>

      <AnimatePresence>
        {newTaskOpen && (
          <motion.div
            className="modal-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onMouseDown={(event) => {
              if (event.currentTarget === event.target) setNewTaskOpen(false);
            }}
          >
            <motion.form
              className="new-task-dialog"
              initial={reducedMotion ? false : { opacity: 0, y: 18, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10 }}
              onSubmit={createTask}
            >
              <header><div><span>{t("newTask")}</span><h2>{t("chooseProvider")}</h2></div><button type="button" className="icon-button" onClick={() => setNewTaskOpen(false)}><X size={18} /></button></header>
              <div className="provider-choice">
                {(["codex", "claude"] as Provider[]).map((provider) => (
                  <button
                    type="button"
                    key={provider}
                    className={newProvider === provider ? "active" : ""}
                    onClick={() => setNewProvider(provider)}
                  >
                    {provider === "codex" ? <Code size={22} /> : <Robot size={22} />}
                    <strong>{provider === "codex" ? "Codex" : "Claude Code"}</strong>
                    <span>{provider === "codex" ? t("codexDescription") : t("claudeDescription")}</span>
                  </button>
                ))}
              </div>
              <label htmlFor="task-title">{t("taskTitle")}</label>
              <input id="task-title" autoFocus value={newTitle} onChange={(event) => setNewTitle(event.target.value)} />
              <footer>
                <button type="button" className="button" onClick={() => setNewTaskOpen(false)}>{t("cancel")}</button>
                <button className="button primary" disabled={busy}>{t("create")}</button>
              </footer>
            </motion.form>
          </motion.div>
        )}
      </AnimatePresence>
    </MotionConfig>
  );
}
