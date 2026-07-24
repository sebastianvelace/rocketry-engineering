import {
  ArrowClockwise,
  ChartLine,
  Check,
  CircleNotch,
  Code,
  DownloadSimple,
  Fire,
  FolderOpen,
  Plus,
  Pulse,
  Robot,
  RocketLaunch,
  Stop,
  WaveSine,
  ClockCounterClockwise,
  PlugsConnected,
  ChatCircleDots,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { AnimatePresence, MotionConfig, motion, useReducedMotion } from "motion/react";
import { CSSProperties, FormEvent, lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GatewayApi, connectGateway } from "./api";
import {
  BenchView,
  FlightView,
  HistoryView,
  MotorView,
  WiringView,
} from "./EngineeringViews";
import { CopyKey, eventLabel, Language, statusLabel, translate } from "./i18n";
import { RunPlot } from "./RunPlot";
import type {
  AgentEvent,
  Approval,
  Artifact,
  EngineeringStatus,
  Provider,
  ProviderCommand,
  ProviderModel,
  RunRecord,
  RunSummary,
  Session,
} from "./types";

type View = "agent" | "bench" | "wiring" | "motor" | "flight" | "history";
type ResultTab = "runs" | "activity" | "artifacts";
const MessageContent = lazy(() =>
  import("./MessageContent").then((module) => ({ default: module.MessageContent })),
);

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
      if (streaming) messages.push({ id: streamingId, role: "assistant", text: streaming, streaming: true });
      streaming = "";
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
  if (streaming) messages.push({ id: streamingId, role: "assistant", text: streaming, streaming: true });
  return messages;
}

export function activityEvents(events: AgentEvent[]): AgentEvent[] {
  return events.filter((event) =>
    ["tool_started", "tool_progress", "tool_completed", "command_output", "reasoning", "error"].includes(event.type),
  );
}

function compactDetail(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  return JSON.stringify(value, null, 2);
}

const viewCopy: Record<View, { es: string; en: string }> = {
  agent: { es: "Agente", en: "Agent" },
  bench: { es: "Banco", en: "Bench" },
  wiring: { es: "Cableado", en: "Wiring" },
  motor: { es: "Motor", en: "Motor" },
  flight: { es: "Vuelo", en: "Flight" },
  history: { es: "Historial", en: "History" },
};

export default function App() {
  const reducedMotion = useReducedMotion();
  const [language, setLanguage] = useState<Language>(() => (localStorage.getItem("rocketry-language") as Language) || "es");
  const [view, setView] = useState<View>(() => (localStorage.getItem("rocketry-view") as View) || "agent");
  const t = useCallback((key: CopyKey) => translate(language, key), [language]);
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
  const [warming, setWarming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [railWidth, setRailWidth] = useState(() => Number(localStorage.getItem("rocketry-rail-width")) || 72);
  const feedEnd = useRef<HTMLDivElement>(null);
  const warmed = useRef<Set<string>>(new Set());

  const selectedSession = sessions.find((session) => session.id === selectedId) || null;
  const conversation = useMemo(() => conversationFrom(events), [events]);
  const activity = useMemo(() => activityEvents(events), [events]);
  const commands = useMemo(() => {
    const capability = [...events].reverse().find((event) => event.text === "Provider capabilities");
    return (capability?.data.commands || []) as ProviderCommand[];
  }, [events]);
  const models = useMemo(() => {
    const capability = [...events].reverse().find((event) => event.text === "Provider capabilities");
    return (capability?.data.models || []) as ProviderModel[];
  }, [events]);
  const currentModel = String(selectedSession?.metadata?.model || "default");
  const commandMatches = useMemo(() => {
    if (!composer.startsWith("/") || composer.includes(" ")) return [];
    const query = composer.slice(1).toLowerCase();
    return commands.filter((command) => command.name.toLowerCase().includes(query)).slice(0, 7);
  }, [commands, composer]);

  const loadGateway = useCallback(async () => {
    setConnectionError("");
    try {
      const client = new GatewayApi(await connectGateway());
      setApi(client);
      const [nextSessions, nextStatus, nextRuns, nextArtifacts] = await Promise.all([
        client.sessions(), client.status(), client.runs(), client.artifacts(),
      ]);
      setSessions(nextSessions);
      setStatus(nextStatus);
      setRuns(nextRuns);
      setArtifacts(nextArtifacts);
      setSelectedId((current) => current || nextSessions[0]?.id || null);
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : String(error));
    }
  }, []);

  useEffect(() => { void loadGateway(); }, [loadGateway]);
  useEffect(() => {
    localStorage.setItem("rocketry-language", language);
    document.documentElement.lang = language;
  }, [language]);
  useEffect(() => { localStorage.setItem("rocketry-view", view); }, [view]);
  useEffect(() => { localStorage.setItem("rocketry-rail-width", String(railWidth)); }, [railWidth]);

  const refreshEngineering = useCallback(async () => {
    if (!api) return;
    const [nextStatus, nextRuns, nextArtifacts] = await Promise.all([api.status(), api.runs(), api.artifacts()]);
    setStatus(nextStatus);
    setRuns(nextRuns);
    setArtifacts(nextArtifacts);
  }, [api]);
  const refreshSessions = useCallback(async () => { if (api) setSessions(await api.sessions()); }, [api]);

  useEffect(() => {
    if (api && view !== "agent") void refreshEngineering();
  }, [api, view, refreshEngineering]);

  const openSavedRun = useCallback(async (runId: number) => {
    if (!api) return null;
    await refreshEngineering();
    const run = await api.run(runId);
    setSelectedRun(run);
    return run;
  }, [api, refreshEngineering]);

  useEffect(() => {
    if (!api || !selectedId || warmed.current.has(selectedId)) return;
    warmed.current.add(selectedId);
    setWarming(true);
    void api.connectSession(selectedId)
      .then(() => {
        setConnectionError("");
        return refreshSessions();
      })
      .catch((error) => {
        warmed.current.delete(selectedId);
        setConnectionError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => setWarming(false));
  }, [api, selectedId, refreshSessions]);

  useEffect(() => {
    if (!api || !selectedId) { setEvents([]); return; }
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
      unsubscribe = api.subscribe(selectedId, lastSequence, (event) => {
        lastSequence = Math.max(lastSequence, event.sequence);
        setEvents((current) => current.some((item) => item.id === event.id) ? current : [...current, event]);
        if (event.type === "approval_requested" || event.type === "approval_resolved") void api.approvals(selectedId).then(setApprovals);
        if (event.type === "tool_completed") void refreshEngineering();
        if (event.type === "session" || event.type === "error") void refreshSessions();
      }, (connected) => {
        setSocketConnected(connected);
        if (!connected && active) reconnectTimer = window.setTimeout(connect, 1200);
      });
    };
    void connect().catch((error) => setConnectionError(String(error)));
    return () => { active = false; window.clearTimeout(reconnectTimer); unsubscribe(); setSocketConnected(false); };
  }, [api, selectedId, refreshEngineering, refreshSessions]);

  useEffect(() => {
    if (!reducedMotion) feedEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation.length, reducedMotion]);

  useEffect(() => {
    if (!api || !runs.length || selectedRun) return;
    void api.run(runs[0].id).then(setSelectedRun);
  }, [api, runs, selectedRun]);

  async function createTask(event: FormEvent) {
    event.preventDefault();
    if (!api) return;
    setBusy(true);
    try {
      const session = await api.createSession(newProvider, newTitle.trim() || t("newTask"));
      setSessions((current) => [session, ...current]);
      setSelectedId(session.id);
      setView("agent");
      setNewTaskOpen(false);
      setNewTitle("");
    } finally { setBusy(false); }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    if (!api || !selectedId || !composer.trim() || busy) return;
    const value = composer.trim();
    const modelCommand = value.match(/^\/model(?:\s+(.+))?$/i);
    if (selectedSession?.provider === "claude" && modelCommand) {
      if (!modelCommand[1]) {
        setComposer("");
        setModelPickerOpen(true);
        return;
      }
      await changeModel(modelCommand[1].trim());
      setComposer("");
      return;
    }
    setComposer("");
    setBusy(true);
    try { await api.send(selectedId, value); await refreshSessions(); }
    catch (error) {
      setConnectionError(error instanceof Error ? error.message : String(error));
      setComposer(value);
    } finally { setBusy(false); }
  }

  async function resolveApproval(approval: Approval, approved: boolean, forSession = false) {
    if (!api) return;
    await api.resolveApproval(approval.id, approved, forSession);
    setApprovals(await api.approvals(approval.session_id));
  }

  async function retrySelectedConnection() {
    if (!api || !selectedId) return;
    setWarming(true);
    setConnectionError("");
    try {
      await api.connectSession(selectedId);
      warmed.current.add(selectedId);
      await refreshSessions();
    } catch (error) {
      warmed.current.delete(selectedId);
      setConnectionError(error instanceof Error ? error.message : String(error));
    } finally {
      setWarming(false);
    }
  }

  async function changeModel(model: string) {
    if (!api || !selectedId) return;
    setBusy(true);
    setConnectionError("");
    try {
      const updated = await api.setModel(selectedId, model);
      setSessions((current) => current.map((session) => session.id === updated.id ? updated : session));
      setComposer("");
      setModelPickerOpen(false);
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  function chooseCommand(command: ProviderCommand) {
    if (command.name === "model" && selectedSession?.provider === "claude") {
      setComposer("");
      setModelPickerOpen(true);
      return;
    }
    setComposer(`/${command.name}${command.argumentHint ? " " : ""}`);
  }

  function beginRailResize(event: React.PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = railWidth;
    const move = (next: PointerEvent) => {
      setRailWidth(Math.max(58, Math.min(118, startWidth + next.clientX - startX)));
    };
    const stop = () => {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", stop);
      document.body.classList.remove("resizing-rail");
    };
    document.body.classList.add("resizing-rail");
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", stop);
  }

  if (!api) return (
    <main className="boot-screen">
      <div className="brand-lockup"><span>R/</span> ROCKETRY</div>
      {connectionError ? <><p>{t("gatewayError")}</p><code>{connectionError}</code><button className="button primary" onClick={() => void loadGateway()}><ArrowClockwise size={17} />{t("retry")}</button></> : <div className="boot-line"><CircleNotch className="spin" size={18} />Starting local gateway</div>}
    </main>
  );

  const isRunning = ["running", "waiting_approval", "interrupting"].includes(selectedSession?.status || "");
  const nav = [
    { id: "agent" as View, icon: ChatCircleDots },
    { id: "bench" as View, icon: WaveSine },
    { id: "wiring" as View, icon: PlugsConnected },
    { id: "motor" as View, icon: Fire },
    { id: "flight" as View, icon: RocketLaunch },
    { id: "history" as View, icon: ClockCounterClockwise },
  ];
  const shared = { api, language, status, onRunSaved: openSavedRun };

  return (
    <MotionConfig reducedMotion="user">
      <div
        className={`app-shell view-${view}`}
        style={{ "--rail-width": `${railWidth}px` } as CSSProperties}
      >
        <AnimatePresence>
          {connectionError && (
            <motion.aside
              className="app-notice"
              role="alert"
              initial={reducedMotion ? false : { opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -5 }}
            >
              <WarningCircle size={17} />
              <div>
                <strong>{language === "es" ? "No se pudo conectar el agente" : "Agent connection failed"}</strong>
                <span>{connectionError}</span>
              </div>
              {selectedId && <button onClick={() => void retrySelectedConnection()}>{t("retry")}</button>}
              <button aria-label={language === "es" ? "Cerrar error" : "Dismiss error"} onClick={() => setConnectionError("")}><X size={15} /></button>
            </motion.aside>
          )}
        </AnimatePresence>
        <aside className="global-rail">
          <div className="brand-mark">R<span>/</span></div>
          <nav>{nav.map(({ id, icon: Icon }) => <motion.button whileTap={{ scale: 0.92 }} className={view === id ? "active" : ""} onClick={() => setView(id)} key={id}><Icon size={21} weight={view === id ? "fill" : "regular"} /><span>{viewCopy[id][language]}</span></motion.button>)}</nav>
          <footer>
            <button onClick={() => setLanguage(language === "es" ? "en" : "es")}><strong>{language.toUpperCase()}</strong><span>{language === "es" ? "EN" : "ES"}</span></button>
            <i className={status?.ports.length ? "online" : ""} title={status?.ports[0] || "ESP32 offline"} />
          </footer>
          <div
            className="rail-resizer"
            role="separator"
            aria-label={language === "es" ? "Cambiar tamaño de navegación" : "Resize navigation"}
            aria-orientation="vertical"
            aria-valuemin={58}
            aria-valuemax={118}
            aria-valuenow={railWidth}
            tabIndex={0}
            onPointerDown={beginRailResize}
            onDoubleClick={() => setRailWidth(72)}
            onKeyDown={(event) => {
              if (event.key === "ArrowLeft") {
                event.preventDefault();
                setRailWidth((width) => Math.max(58, width - 6));
              } else if (event.key === "ArrowRight") {
                event.preventDefault();
                setRailWidth((width) => Math.min(118, width + 6));
              } else if (event.key === "Home") {
                event.preventDefault();
                setRailWidth(72);
              }
            }}
          />
        </aside>

        {view === "agent" && (
          <aside className="session-panel">
            <header><span>{t("sessions")}</span><button onClick={() => setNewTaskOpen(true)}><Plus size={16} /></button></header>
            <nav>
              {sessions.map((session) => (
                <button className={selectedId === session.id ? "active" : ""} onClick={() => setSelectedId(session.id)} key={session.id}>
                  {session.provider === "codex" ? <Code size={15} /> : <Robot size={15} />}
                  <span><strong>{session.title}</strong><small>{session.provider} / {statusLabel(language, session.status)}</small></span>
                </button>
              ))}
              {!sessions.length && <p>{t("noSessions")}</p>}
            </nav>
            <footer>
              {selectedSession && (
                <div className="workspace-scope" title={selectedSession.workspace}>
                  <FolderOpen size={14} />
                  <span>
                    <strong>{selectedSession.workspace.split("/").at(-1)}</strong>
                    <small>{language === "es" ? "repositorio completo" : "full repository"}</small>
                  </span>
                </div>
              )}
              <span>{status?.saved_runs || 0} {t("savedRuns")}</span>
              <span>{status?.ports[0] || t("disconnected")}</span>
            </footer>
          </aside>
        )}

        <main className="main-stage">
          <AnimatePresence mode="wait">
            <motion.div key={view} className="view-motion" initial={reducedMotion ? false : { opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
              {view === "bench" && <BenchView {...shared} />}
              {view === "wiring" && <WiringView {...shared} />}
              {view === "motor" && <MotorView {...shared} />}
              {view === "flight" && <FlightView {...shared} />}
              {view === "history" && <HistoryView {...shared} runs={runs} selectedRun={selectedRun} setSelectedRun={setSelectedRun} refresh={refreshEngineering} />}
              {view === "agent" && (
                <div className="agent-workspace">
                  {!selectedSession ? <section className="empty-workbench"><Robot size={28} /><h1>{t("selectSession")}</h1><button className="button primary" onClick={() => setNewTaskOpen(true)}><Plus size={17} />{t("newTask")}</button></section> : <>
                    <section className="conversation-pane">
                      <header className="pane-header">
                        <div><p>{selectedSession.provider.toUpperCase()} / {selectedSession.workspace.split("/").at(-1)}</p><h1>{selectedSession.title}</h1></div>
                        <div className="agent-state"><span className={socketConnected ? "online" : ""} />{warming ? (language === "es" ? "Conectando" : "Connecting") : isRunning ? t("agentWorking") : t("agentReady")}</div>
                      </header>
                      <div className="message-feed">
                        {!conversation.length && <div className="agent-intro"><span>R/ AGENT HARNESS</span><h2>{t("noConversation")}</h2><p>{language === "es" ? "Puedes pedir una prueba en lenguaje natural o escribir / para usar un comando del proveedor." : "Ask for a test in natural language or type / to use a provider command."}</p></div>}
                        {conversation.map((message) => <motion.article initial={reducedMotion ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className={`message ${message.role}`} key={message.id}><span>{message.role === "user" ? "YOU" : selectedSession.provider.toUpperCase()}</span><Suspense fallback={<div>{message.text}</div>}><MessageContent text={message.text} /></Suspense>{message.streaming && <i />}</motion.article>)}
                        {approvals.map((approval) => <section className="approval-panel" key={approval.id}><div><strong>{t("needsApproval")}</strong><span>{approval.action}</span></div><pre>{compactDetail(approval.details)}</pre><div><button onClick={() => void resolveApproval(approval, false)}><X />{t("deny")}</button><button onClick={() => void resolveApproval(approval, true)}><Check />{t("approve")}</button><button className="primary" onClick={() => void resolveApproval(approval, true, true)}>{t("approveSession")}</button></div></section>)}
                        <div ref={feedEnd} />
                      </div>
                      <form className="composer" onSubmit={sendMessage}>
                        <AnimatePresence>
                          {modelPickerOpen && (
                            <motion.div className="model-picker" initial={reducedMotion ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }}>
                              <header>
                                <div><span>{language === "es" ? "MODELO DE CLAUDE" : "CLAUDE MODEL"}</span><strong>{language === "es" ? "Selecciona para esta sesión" : "Select for this session"}</strong></div>
                                <button type="button" onClick={() => setModelPickerOpen(false)}><X size={16} /></button>
                              </header>
                              <div>
                                {!models.length && (
                                  <p className="model-picker-empty">
                                    {language === "es" ? "Conecta la sesión para cargar los modelos disponibles." : "Connect the session to load available models."}
                                  </p>
                                )}
                                {models.map((model) => (
                                  <button type="button" className={currentModel === model.value ? "active" : ""} onClick={() => void changeModel(model.value)} key={model.value}>
                                    <i>{currentModel === model.value && <Check size={13} weight="bold" />}</i>
                                    <span><strong>{model.displayName}</strong><small>{model.description}</small></span>
                                    {model.supportsFastMode && <em>FAST</em>}
                                  </button>
                                ))}
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                        {!modelPickerOpen && commandMatches.length > 0 && <div className="command-palette">{commandMatches.map((command) => <button type="button" onClick={() => chooseCommand(command)} key={command.name}><code>/{command.name}</code><span>{command.description}</span><small>{command.argumentHint}</small></button>)}</div>}
                        <textarea rows={3} value={composer} onChange={(event) => setComposer(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} placeholder={t("placeholder")} disabled={isRunning || busy || warming} />
                        <div><span>{selectedSession.provider === "claude" ? `${currentModel} / ${commands.length} commands` : `${selectedSession.provider} / ${statusLabel(language, selectedSession.status)}`}</span>{isRunning ? <button type="button" className="button danger" onClick={() => void api.interrupt(selectedSession.id)}><Stop size={15} />{t("stop")}</button> : <button className="button primary" disabled={!composer.trim() || busy || warming}>{busy || warming ? <CircleNotch className="spin" /> : <Check />}{t("send")}</button>}</div>
                      </form>
                    </section>
                    <section className="result-dock">
                      <header><nav><button className={tab === "runs" ? "active" : ""} onClick={() => setTab("runs")}><ChartLine />{t("runs")}</button><button className={tab === "activity" ? "active" : ""} onClick={() => setTab("activity")}><Pulse />{t("activity")}</button><button className={tab === "artifacts" ? "active" : ""} onClick={() => setTab("artifacts")}><FolderOpen />{t("artifacts")}</button></nav><button onClick={() => void refreshEngineering()}><ArrowClockwise /></button></header>
                      {tab === "runs" && <div className="dock-content">{runs.length ? <><select value={selectedRun?.id || runs[0].id} onChange={(event) => void api.run(Number(event.target.value)).then(setSelectedRun)}>{runs.map((run) => <option value={run.id} key={run.id}>#{run.id} {run.kind} {run.note}</option>)}</select>{selectedRun && <><div className="run-dock-title"><span>RUN #{selectedRun.id}</span><h2>{selectedRun.kind.replaceAll("_", " ")}</h2></div><RunPlot run={selectedRun} /><div className="data-foot"><span>{selectedRun.row_count} {t("samples")}</span>{Object.entries(selectedRun.meta).slice(0, 5).map(([key, value]) => <span key={key}>{key}: {compactDetail(value)}</span>)}</div></>}</> : <p>{t("noRuns")}</p>}</div>}
                      {tab === "activity" && <div className="activity-view">{activity.map((event) => <article key={event.id}><span>{eventLabel(language, event.type)}</span><p>{event.text}</p><time>{new Date(event.created_at).toLocaleTimeString(language)}</time></article>)}</div>}
                      {tab === "artifacts" && <div className="artifact-view">{artifacts.map((artifact) => <article key={artifact.id}><div><strong>{artifact.kind}</strong><span>{artifact.media_type}</span></div><button onClick={() => void api.openArtifact(artifact)}><DownloadSimple /></button></article>)}</div>}
                    </section>
                  </>}
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      <AnimatePresence>{newTaskOpen && <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={(event) => { if (event.target === event.currentTarget) setNewTaskOpen(false); }}><motion.form className="new-task-dialog" initial={reducedMotion ? false : { opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} onSubmit={createTask}><header><div><span>NEW SESSION</span><h2>{t("chooseProvider")}</h2></div><button type="button" onClick={() => setNewTaskOpen(false)}><X /></button></header><div className="provider-choice">{(["codex", "claude"] as Provider[]).map((provider) => <button type="button" className={newProvider === provider ? "active" : ""} onClick={() => setNewProvider(provider)} key={provider}>{provider === "codex" ? <Code /> : <Robot />}<strong>{provider === "codex" ? "Codex" : "Claude Code"}</strong><span>{provider === "codex" ? t("codexDescription") : t("claudeDescription")}</span></button>)}</div><label>{t("taskTitle")}<input autoFocus value={newTitle} onChange={(event) => setNewTitle(event.target.value)} /></label><footer><button type="button" onClick={() => setNewTaskOpen(false)}>{t("cancel")}</button><button className="primary" disabled={busy}>{busy ? <CircleNotch className="spin" /> : <Plus />}{t("create")}</button></footer></motion.form></motion.div>}</AnimatePresence>
    </MotionConfig>
  );
}
