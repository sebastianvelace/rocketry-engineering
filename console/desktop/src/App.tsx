import {
  ArrowClockwise,
  ChartLine,
  Check,
  CircleNotch,
  Code,
  DownloadSimple,
  Fire,
  FolderOpen,
  Gauge,
  Plus,
  Pulse,
  Robot,
  RocketLaunch,
  Stop,
  Trash,
  WaveSine,
  ClockCounterClockwise,
  PlugsConnected,
  ChatCircleDots,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { AnimatePresence, MotionConfig, motion, useReducedMotion } from "motion/react";
import { CSSProperties, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GatewayApi, connectGateway } from "./api";
import { buildTimeline, Timeline } from "./ActivityFeed";
import {
  BenchView,
  FlightView,
  HistoryView,
  MotorView,
  WiringView,
} from "./EngineeringViews";
import { CopyKey, eventLabel, Language, statusLabel, translate } from "./i18n";
import { RunPlot } from "./RunPlot";
import { UsageView } from "./UsageView";
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

type View = "agent" | "bench" | "wiring" | "motor" | "flight" | "history" | "usage";
type ResultTab = "runs" | "activity" | "artifacts";

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
  "error",
];

export function activityEvents(events: AgentEvent[]): AgentEvent[] {
  return events.filter((event) => RAW_LOG_EVENT_TYPES.includes(event.type));
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
  usage: { es: "Uso", en: "Usage" },
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
  const [sessionToDelete, setSessionToDelete] = useState<Session | null>(null);
  const [deletingSession, setDeletingSession] = useState(false);
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
  const timeline = useMemo(() => buildTimeline(events), [events]);
  const activity = useMemo(() => activityEvents(events), [events]);
  const commands = useMemo(() => {
    const capability = [...events].reverse().find((event) => event.text === "Provider capabilities");
    return (capability?.data.commands || []) as ProviderCommand[];
  }, [events]);
  const models = useMemo(() => {
    const capability = [...events].reverse().find((event) => event.text === "Provider capabilities");
    return (capability?.data.models || []) as ProviderModel[];
  }, [events]);
  const currentModel = String(
    selectedSession?.metadata?.model
    || models.find((model) => model.isDefault)?.value
    || models.find((model) => model.value === "default")?.value
    || "default",
  );
  const commandMatches = useMemo(() => {
    if (!composer.startsWith("/") || composer.includes(" ")) return [];
    const query = composer.slice(1).toLowerCase();
    return commands.filter((command) => command.name.toLowerCase().includes(query)).slice(0, 7);
  }, [commands, composer]);

  const loadGateway = useCallback(async () => {
    setConnectionError("");
    try {
      const client = new GatewayApi(await connectGateway());
      let loaded: [Session[], EngineeringStatus, RunSummary[], Artifact[]] | null = null;
      let lastError: unknown;
      for (const delay of [0, 150, 300, 600, 1200]) {
        if (delay) await new Promise((resolve) => window.setTimeout(resolve, delay));
        try {
          loaded = await Promise.all([
            client.sessions(), client.status(), client.runs(), client.artifacts(),
          ]);
          break;
        } catch (error) {
          lastError = error;
        }
      }
      if (!loaded) throw lastError || new Error("Gateway unavailable.");
      const [nextSessions, nextStatus, nextRuns, nextArtifacts] = loaded;
      setApi(client);
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
  }, [timeline.length, reducedMotion]);

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

  async function deleteConversation() {
    if (!api || !sessionToDelete || deletingSession) return;
    const deletedId = sessionToDelete.id;
    setDeletingSession(true);
    setConnectionError("");
    try {
      await api.deleteSession(deletedId);
      warmed.current.delete(deletedId);
      const remaining = sessions.filter((session) => session.id !== deletedId);
      setSessions(remaining);
      if (selectedId === deletedId) {
        setSelectedId(remaining[0]?.id || null);
        setEvents([]);
        setApprovals([]);
      }
      setSessionToDelete(null);
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : String(error));
    } finally {
      setDeletingSession(false);
    }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    if (!api || !selectedId || !composer.trim() || busy) return;
    const value = composer.trim();
    const slashCommand = value.match(/^\/([^\s]+)(?:\s+([\s\S]+))?$/);
    if (slashCommand) {
      if (slashCommand[1].toLowerCase() === "model" && !slashCommand[2]) {
        setComposer("");
        setModelPickerOpen(true);
        return;
      }
      if (slashCommand[1].toLowerCase() === "model") {
        await changeModel(slashCommand[2].trim());
        return;
      }
      await executeAgentCommand(slashCommand[1], slashCommand[2] || "");
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

  async function executeAgentCommand(command: string, argumentsText: string) {
    if (!api || !selectedId) return;
    setBusy(true);
    setConnectionError("");
    try {
      const result = await api.executeCommand(selectedId, command, argumentsText);
      if (result.action === "usage") {
        setView("usage");
      } else if (result.action === "created") {
        setSessions((current) => [result.session, ...current.filter((item) => item.id !== result.session.id)]);
        setSelectedId(result.session.id);
      } else {
        setSessions((current) => current.map((session) => session.id === result.session.id ? result.session : session));
      }
      setComposer("");
      await refreshSessions();
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  function chooseCommand(command: ProviderCommand) {
    if (command.name === "model") {
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
    { id: "usage" as View, icon: Gauge },
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
              <button onClick={() => void (selectedId ? retrySelectedConnection() : loadGateway())}>{t("retry")}</button>
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
                <div className={`session-row ${selectedId === session.id ? "active" : ""}`} key={session.id}>
                  <button className="session-select" onClick={() => setSelectedId(session.id)}>
                    {session.provider === "codex" ? <Code size={15} /> : <Robot size={15} />}
                    <span><strong>{session.title}</strong><small>{session.provider} / {statusLabel(language, session.status)}</small></span>
                  </button>
                  <button
                    className="session-delete"
                    aria-label={`${t("deleteConversation")}: ${session.title}`}
                    title={t("deleteConversation")}
                    onClick={() => setSessionToDelete(session)}
                  >
                    <Trash size={14} />
                  </button>
                </div>
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
              {view === "usage" && <UsageView api={api} language={language} />}
              {view === "agent" && (
                <div className="agent-workspace">
                  {!selectedSession ? <section className="empty-workbench"><Robot size={28} /><h1>{t("selectSession")}</h1><button className="button primary" onClick={() => setNewTaskOpen(true)}><Plus size={17} />{t("newTask")}</button></section> : <>
                    <section className="conversation-pane">
                      <header className="pane-header">
                        <div><p>{selectedSession.provider.toUpperCase()} / {selectedSession.workspace.split("/").at(-1)}</p><h1>{selectedSession.title}</h1></div>
                        <div className="agent-state"><span className={socketConnected ? "online" : ""} />{warming ? (language === "es" ? "Conectando" : "Connecting") : isRunning ? t("agentWorking") : t("agentReady")}</div>
                      </header>
                      <div className="message-feed">
                        {!timeline.length && <div className="agent-intro"><span>R/ AGENT HARNESS</span><h2>{t("noConversation")}</h2><p>{language === "es" ? "Puedes pedir una prueba en lenguaje natural o escribir / para usar un comando del proveedor." : "Ask for a test in natural language or type / to use a provider command."}</p></div>}
                        <Timeline items={timeline} provider={selectedSession.provider} language={language} />
                        {approvals.map((approval) => <section className="approval-panel" key={approval.id}><div><strong>{t("needsApproval")}</strong><span>{approval.action}</span></div><pre>{compactDetail(approval.details)}</pre><div><button onClick={() => void resolveApproval(approval, false)}><X />{t("deny")}</button><button onClick={() => void resolveApproval(approval, true)}><Check />{t("approve")}</button><button className="primary" onClick={() => void resolveApproval(approval, true, true)}>{t("approveSession")}</button></div></section>)}
                        <div ref={feedEnd} />
                      </div>
                      <form className="composer" onSubmit={sendMessage}>
                        <AnimatePresence>
                          {modelPickerOpen && (
                            <motion.div className="model-picker" initial={reducedMotion ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }}>
                              <header>
                                <div><span>{selectedSession.provider.toUpperCase()} / MODEL</span><strong>{language === "es" ? "Selecciona para esta sesión" : "Select for this session"}</strong></div>
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
                        <div><span>{`${currentModel} / ${commands.length} commands`}</span>{isRunning ? <button type="button" className="button danger" onClick={() => void api.interrupt(selectedSession.id)}><Stop size={15} />{t("stop")}</button> : <button className="button primary" disabled={!composer.trim() || busy || warming}>{busy || warming ? <CircleNotch className="spin" /> : <Check />}{t("send")}</button>}</div>
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
      <AnimatePresence>
        {sessionToDelete && (
          <motion.div
            className="modal-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onMouseDown={(event) => {
              if (event.target === event.currentTarget && !deletingSession) setSessionToDelete(null);
            }}
          >
            <motion.section
              className="delete-session-dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby="delete-session-title"
              initial={reducedMotion ? false : { opacity: 0, y: 12, scale: 0.99 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
            >
              <span>DELETE SESSION</span>
              <h2 id="delete-session-title">{t("deleteConversationTitle")}</h2>
              <strong>{sessionToDelete.title}</strong>
              <p>{t("deleteConversationBody")}</p>
              <footer>
                <button disabled={deletingSession} onClick={() => setSessionToDelete(null)}>{t("cancel")}</button>
                <button className="danger" disabled={deletingSession} onClick={() => void deleteConversation()}>
                  {deletingSession ? <CircleNotch className="spin" /> : <Trash />}
                  {t("delete")}
                </button>
              </footer>
            </motion.section>
          </motion.div>
        )}
      </AnimatePresence>
    </MotionConfig>
  );
}
