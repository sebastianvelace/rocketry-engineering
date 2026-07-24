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
  GitMerge,
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
import { CSSProperties, FormEvent, lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { activityEvents, extractRunId } from "./agentEvents";
import { AskUserQuestionItem, AskUserQuestionPanel, buildTimeline, DiffBlock, Timeline, unifiedDiffToLines } from "./ActivityFeed";
import { useComposer } from "./hooks/useComposer";
import { useGatewayWorkspace } from "./hooks/useGatewayWorkspace";
import { usePersistedState } from "./hooks/usePersistedState";
import { useResizableRail } from "./hooks/useResizableRail";
import { useSessionTransport } from "./hooks/useSessionTransport";
import { CopyKey, eventLabel, Language, statusLabel, translate } from "./i18n";
import type {
  Approval,
  Provider,
  ProviderCommand,
  ProviderModel,
  RunSummary,
  Session,
  WorktreeReview,
} from "./types";

export { activityEvents, extractRunId };

type View = "agent" | "bench" | "wiring" | "motor" | "flight" | "history" | "usage";
type ResultTab = "runs" | "activity" | "artifacts";

// Deferred: none of these are needed for the default Agent view, so they
// ship in a separate chunk loaded only when the operator first navigates
// to an engineering surface.
const BenchView = lazy(() => import("./EngineeringViews").then((module) => ({ default: module.BenchView })));
const WiringView = lazy(() => import("./EngineeringViews").then((module) => ({ default: module.WiringView })));
const MotorView = lazy(() => import("./EngineeringViews").then((module) => ({ default: module.MotorView })));
const FlightView = lazy(() => import("./EngineeringViews").then((module) => ({ default: module.FlightView })));
const HistoryView = lazy(() => import("./EngineeringViews").then((module) => ({ default: module.HistoryView })));
const UsageView = lazy(() => import("./UsageView").then((module) => ({ default: module.UsageView })));
const RunPlot = lazy(() => import("./RunPlot").then((module) => ({ default: module.RunPlot })));

function ViewLoading() {
  return <div className="view-loading" />;
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
  const [language, setLanguage] = usePersistedState<Language>("rocketry-language", "es");
  const [view, setView] = usePersistedState<View>("rocketry-view", "agent");
  const t = useCallback((key: CopyKey) => translate(language, key), [language]);
  const workspace = useGatewayWorkspace();
  const [tab, setTab] = useState<ResultTab>("runs");
  const [newTaskOpen, setNewTaskOpen] = useState(false);
  const [sessionToDelete, setSessionToDelete] = useState<Session | null>(null);
  const [deletingSession, setDeletingSession] = useState(false);
  const [worktreeReview, setWorktreeReview] = useState<WorktreeReview | null>(null);
  const [worktreeReviewLoading, setWorktreeReviewLoading] = useState(false);
  const [mergingWorktree, setMergingWorktree] = useState(false);
  const [newProvider, setNewProvider] = useState<Provider>("codex");
  const [newTitle, setNewTitle] = useState("");
  const [newIsolated, setNewIsolated] = useState(false);
  const [busy, setBusy] = useState(false);
  const rail = useResizableRail();
  const feedEnd = useRef<HTMLDivElement>(null);

  const requestUsageView = useCallback(() => setView("usage"), [setView]);
  const onRunCompleted = useCallback((runId: number | null) => {
    void workspace.refreshEngineering(true, runId, () => setTab("runs"));
  }, [workspace.refreshEngineering]);

  const transport = useSessionTransport({
    api: workspace.api,
    selectedId: workspace.selectedId,
    onConnectionError: workspace.setConnectionError,
    onSessionActivity: workspace.refreshSessions,
    onRunCompleted,
  });

  const selectedSession = workspace.sessions.find((session) => session.id === workspace.selectedId) || null;
  const timeline = useMemo(() => buildTimeline(transport.events), [transport.events]);
  const activity = useMemo(() => activityEvents(transport.events), [transport.events]);
  const commands = useMemo(() => {
    const capability = [...transport.events].reverse().find((event) => event.text === "Provider capabilities");
    return (capability?.data.commands || []) as ProviderCommand[];
  }, [transport.events]);
  const models = useMemo(() => {
    const capability = [...transport.events].reverse().find((event) => event.text === "Provider capabilities");
    return (capability?.data.models || []) as ProviderModel[];
  }, [transport.events]);
  const currentModel = String(
    selectedSession?.metadata?.model
    || models.find((model) => model.isDefault)?.value
    || models.find((model) => model.value === "default")?.value
    || "default",
  );

  const agentComposer = useComposer({
    api: workspace.api,
    selectedId: workspace.selectedId,
    selectedSession,
    commands,
    busy,
    setBusy,
    onError: workspace.setConnectionError,
    updateSessions: workspace.setSessions,
    selectSession: workspace.setSelectedId,
    requestUsageView,
    refreshSessions: workspace.refreshSessions,
  });

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  useEffect(() => {
    if (workspace.api && view !== "agent") void workspace.refreshEngineering();
  }, [workspace.api, view, workspace.refreshEngineering]);

  useEffect(() => {
    if (!reducedMotion) feedEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [timeline.length, reducedMotion]);

  async function createTask(event: FormEvent) {
    event.preventDefault();
    if (!workspace.api) return;
    setBusy(true);
    try {
      await workspace.createSession(newProvider, newTitle.trim() || t("newTask"), newIsolated);
      setView("agent");
      setNewTaskOpen(false);
      setNewTitle("");
      setNewIsolated(false);
    } finally { setBusy(false); }
  }

  function openDeleteDialog(session: Session) {
    setSessionToDelete(session);
    setWorktreeReview(null);
    if (workspace.api && session.metadata?.isolated_workspace) {
      setWorktreeReviewLoading(true);
      void workspace.getWorktreeReview(session.id)
        .then(setWorktreeReview)
        .catch((error) => workspace.setConnectionError(error instanceof Error ? error.message : String(error)))
        .finally(() => setWorktreeReviewLoading(false));
    }
  }

  async function deleteConversation(force = false) {
    if (!workspace.api || !sessionToDelete || deletingSession) return;
    const deletedId = sessionToDelete.id;
    const remaining = workspace.sessions.filter((session) => session.id !== deletedId);
    setDeletingSession(true);
    workspace.setConnectionError("");
    try {
      await workspace.deleteSession(deletedId, force);
      transport.forgetSession(deletedId);
      if (workspace.selectedId === deletedId) {
        workspace.setSelectedId(remaining[0]?.id || null);
        transport.resetTransport();
      }
      setSessionToDelete(null);
      setWorktreeReview(null);
    } catch (error) {
      workspace.setConnectionError(error instanceof Error ? error.message : String(error));
    } finally {
      setDeletingSession(false);
    }
  }

  async function mergeAndDeleteConversation() {
    if (!workspace.api || !sessionToDelete || mergingWorktree) return;
    setMergingWorktree(true);
    workspace.setConnectionError("");
    try {
      await workspace.mergeWorktree(sessionToDelete.id);
      await deleteConversation(false);
    } catch (error) {
      workspace.setConnectionError(error instanceof Error ? error.message : String(error));
    } finally {
      setMergingWorktree(false);
    }
  }

  if (!workspace.api) return (
    <main className="boot-screen">
      <div className="boot-brand">
        <img src="/rocketry-mark.svg" alt="" />
        <div><strong>ROCKETRY</strong><span>WORKSTATION</span></div>
      </div>
      <div className="boot-trajectory" aria-hidden="true"><i /><span /></div>
      {workspace.connectionError ? (
        <section className="boot-error" role="alert">
          <strong>{t("gatewayError")}</strong>
          <code>{workspace.connectionError}</code>
          <button className="button primary" onClick={() => void workspace.loadGateway()}><ArrowClockwise size={17} />{t("retry")}</button>
        </section>
      ) : (
        <div className="boot-status" role="status" aria-live="polite">
          <strong>
            {workspace.bootStage === "gateway"
              ? (language === "es" ? "Iniciando gateway local" : "Starting local gateway")
              : (language === "es" ? "Restaurando espacio de trabajo" : "Restoring workspace")}
          </strong>
          <span>
            {workspace.bootStage === "gateway"
              ? (language === "es" ? "Conectando servicios del agente" : "Connecting agent services")
              : (language === "es" ? "Cargando sesiones, corridas y artefactos" : "Loading sessions, runs and artifacts")}
          </span>
        </div>
      )}
    </main>
  );

  const api = workspace.api;
  const {
    sessions, selectedId, setSelectedId, status, runs, selectedRun, setSelectedRun,
    artifacts, newAgentRunId, connectionError, loadGateway,
  } = workspace;
  const { approvals, socketConnected, warming, resolveApproval, retryConnection } = transport;
  const {
    composer: composerText, setComposer, modelPickerOpen, setModelPickerOpen,
    commandMatches, sendMessage, chooseCommand, changeModel,
  } = agentComposer;

  const isRunning = ["running", "waiting_approval", "interrupting"].includes(selectedSession?.status || "");
  const canSteer = selectedSession?.provider === "codex" && selectedSession.status === "running";
  const nav = [
    { id: "agent" as View, icon: ChatCircleDots },
    { id: "bench" as View, icon: WaveSine },
    { id: "wiring" as View, icon: PlugsConnected },
    { id: "motor" as View, icon: Fire },
    { id: "flight" as View, icon: RocketLaunch },
    { id: "history" as View, icon: ClockCounterClockwise },
    { id: "usage" as View, icon: Gauge },
  ];
  const shared = { api, language, status, onRunSaved: workspace.openSavedRun };

  return (
    <MotionConfig reducedMotion="user">
      <div
        className={`app-shell view-${view}`}
        style={{ "--rail-width": `${rail.railWidth}px` } as CSSProperties}
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
              <button onClick={() => void (selectedId ? retryConnection() : loadGateway())}>{t("retry")}</button>
              <button aria-label={language === "es" ? "Cerrar error" : "Dismiss error"} onClick={() => workspace.setConnectionError("")}><X size={15} /></button>
            </motion.aside>
          )}
        </AnimatePresence>
        <aside className="global-rail">
          <div className="brand-mark"><img src="/rocketry-mark.svg" alt="Rocketry" /></div>
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
            aria-valuemin={rail.minWidth}
            aria-valuemax={rail.maxWidth}
            aria-valuenow={rail.railWidth}
            tabIndex={0}
            onPointerDown={rail.beginRailResize}
            onDoubleClick={() => rail.setRailWidth(rail.defaultWidth)}
            onKeyDown={(event) => {
              if (event.key === "ArrowLeft") {
                event.preventDefault();
                rail.setRailWidth((width) => Math.max(rail.minWidth, width - 6));
              } else if (event.key === "ArrowRight") {
                event.preventDefault();
                rail.setRailWidth((width) => Math.min(rail.maxWidth, width + 6));
              } else if (event.key === "Home") {
                event.preventDefault();
                rail.setRailWidth(rail.defaultWidth);
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
                    onClick={() => openDeleteDialog(session)}
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
                    <small>
                      {selectedSession.metadata?.isolated_workspace
                        ? `${String(selectedSession.metadata?.worktree_branch ?? "")} · ${t("isolatedWorkspaceLabel")}`
                        : (language === "es" ? "repositorio completo" : "full repository")}
                    </small>
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
              {view === "bench" && <Suspense fallback={<ViewLoading />}><BenchView {...shared} /></Suspense>}
              {view === "wiring" && <Suspense fallback={<ViewLoading />}><WiringView {...shared} /></Suspense>}
              {view === "motor" && <Suspense fallback={<ViewLoading />}><MotorView {...shared} /></Suspense>}
              {view === "flight" && <Suspense fallback={<ViewLoading />}><FlightView {...shared} /></Suspense>}
              {view === "history" && <Suspense fallback={<ViewLoading />}><HistoryView {...shared} runs={runs} selectedRun={selectedRun} setSelectedRun={setSelectedRun} refresh={workspace.refreshEngineering} /></Suspense>}
              {view === "usage" && <Suspense fallback={<ViewLoading />}><UsageView api={api} language={language} /></Suspense>}
              {view === "agent" && (
                <div className="agent-workspace">
                  {!selectedSession ? <section className="empty-workbench"><Robot size={28} /><h1>{t("selectSession")}</h1><button className="button primary" onClick={() => setNewTaskOpen(true)}><Plus size={17} />{t("newTask")}</button></section> : <>
                    <section className="conversation-pane">
                      <header className="pane-header">
                        <div><p>{selectedSession.provider.toUpperCase()} / {selectedSession.workspace.split("/").at(-1)}</p><h1>{selectedSession.title}</h1></div>
                        <div className="pane-header-actions">
                          <div className="agent-state"><span className={socketConnected ? "online" : ""} />{warming ? (language === "es" ? "Conectando" : "Connecting") : isRunning ? t("agentWorking") : t("agentReady")}</div>
                          <button
                            className="delete-current-session"
                            type="button"
                            aria-label={t("deleteCurrentConversation")}
                            title={t("deleteCurrentConversation")}
                            onClick={() => openDeleteDialog(selectedSession)}
                          >
                            <Trash size={15} />
                            <span>{t("delete")}</span>
                          </button>
                        </div>
                      </header>
                      <div className="message-feed">
                        {!timeline.length && <div className="agent-intro"><span>R/ AGENT HARNESS</span><h2>{t("noConversation")}</h2><p>{language === "es" ? "Puedes pedir una prueba en lenguaje natural o escribir / para usar un comando del proveedor." : "Ask for a test in natural language or type / to use a provider command."}</p></div>}
                        <Timeline items={timeline} provider={selectedSession.provider} language={language} />
                        {approvals.map((approval: Approval) => approval.details.kind === "ask_user_question" ? (
                          <AskUserQuestionPanel
                            key={approval.id}
                            questions={approval.details.questions as AskUserQuestionItem[]}
                            language={language}
                            onDeny={() => void resolveApproval(approval, false)}
                            onSubmit={(answers) => void resolveApproval(approval, true, false, answers)}
                          />
                        ) : (
                          <section className="approval-panel" key={approval.id}><div><strong>{t("needsApproval")}</strong><span>{approval.action}</span></div><pre>{compactDetail(approval.details)}</pre><div><button onClick={() => void resolveApproval(approval, false)}><X />{t("deny")}</button><button onClick={() => void resolveApproval(approval, true)}><Check />{t("approve")}</button><button className="primary" onClick={() => void resolveApproval(approval, true, true)}>{t("approveSession")}</button></div></section>
                        ))}
                        <div ref={feedEnd} />
                      </div>
                      <form className="composer" onSubmit={(event) => void sendMessage(event)}>
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
                        <textarea
                          rows={3}
                          value={composerText}
                          onChange={(event) => setComposer(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" && !event.shiftKey) {
                              event.preventDefault();
                              event.currentTarget.form?.requestSubmit();
                            }
                          }}
                          placeholder={canSteer ? t("guidePlaceholder") : t("placeholder")}
                          disabled={(isRunning && !canSteer) || busy || warming}
                        />
                        <div>
                          <span>{canSteer ? "CODEX / ACTIVE TURN" : `${currentModel} / ${commands.length} commands`}</span>
                          {isRunning ? (
                            <div className="active-turn-actions">
                              <button type="button" className="button danger" onClick={() => void api.interrupt(selectedSession.id)}><Stop size={15} />{t("stop")}</button>
                              {canSteer && <button className="button primary" disabled={!composerText.trim() || busy}>{busy ? <CircleNotch className="spin" /> : <Check />}{t("guideTurn")}</button>}
                            </div>
                          ) : (
                            <button className="button primary" disabled={!composerText.trim() || busy || warming}>{busy || warming ? <CircleNotch className="spin" /> : <Check />}{t("send")}</button>
                          )}
                        </div>
                      </form>
                    </section>
                    <section className="result-dock">
                      <header><nav><button className={tab === "runs" ? "active" : ""} onClick={() => setTab("runs")}><ChartLine />{t("runs")}</button><button className={tab === "activity" ? "active" : ""} onClick={() => setTab("activity")}><Pulse />{t("activity")}</button><button className={tab === "artifacts" ? "active" : ""} onClick={() => setTab("artifacts")}><FolderOpen />{t("artifacts")}</button></nav><button onClick={() => void workspace.refreshEngineering()}><ArrowClockwise /></button></header>
                      {tab === "runs" && (
                        <div className={`dock-content ${newAgentRunId ? "agent-result-arrived" : ""}`}>
                          <AnimatePresence>
                            {newAgentRunId && (
                              <motion.div
                                className="agent-result-notice"
                                initial={reducedMotion ? false : { opacity: 0, y: -5 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0 }}
                              >
                                <ChartLine size={14} />
                                <span>{t("newAgentResult")}</span>
                                <strong>#{newAgentRunId}</strong>
                              </motion.div>
                            )}
                          </AnimatePresence>
                          {runs.length ? (
                            <>
                              <select value={selectedRun?.id || runs[0].id} onChange={(event) => void api.run(Number(event.target.value)).then(setSelectedRun)}>
                                {runs.map((run) => <option value={run.id} key={run.id}>#{run.id} {run.kind} {run.note}</option>)}
                              </select>
                              {selectedRun && (
                                <>
                                  <div className="run-dock-title"><span>RUN #{selectedRun.id}</span><h2>{selectedRun.kind.replaceAll("_", " ")}</h2></div>
                                  <Suspense fallback={<div className="run-plot-skeleton" aria-label={language === "es" ? "Cargando visualización" : "Loading visualization"} />}><RunPlot run={selectedRun} /></Suspense>
                                  <div className="data-foot"><span>{selectedRun.row_count} {t("samples")}</span>{Object.entries(selectedRun.meta).slice(0, 5).map(([key, value]) => <span key={key}>{key}: {compactDetail(value)}</span>)}</div>
                                </>
                              )}
                            </>
                          ) : <p>{t("noRuns")}</p>}
                        </div>
                      )}
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

      <AnimatePresence>{newTaskOpen && <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={(event) => { if (event.target === event.currentTarget) setNewTaskOpen(false); }}><motion.form className="new-task-dialog" initial={reducedMotion ? false : { opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} onSubmit={createTask}><header><div><span>NEW SESSION</span><h2>{t("chooseProvider")}</h2></div><button type="button" onClick={() => setNewTaskOpen(false)}><X /></button></header><div className="provider-choice">{(["codex", "claude"] as Provider[]).map((provider) => <button type="button" className={newProvider === provider ? "active" : ""} onClick={() => setNewProvider(provider)} key={provider}>{provider === "codex" ? <Code /> : <Robot />}<strong>{provider === "codex" ? "Codex" : "Claude Code"}</strong><span>{provider === "codex" ? t("codexDescription") : t("claudeDescription")}</span></button>)}</div><label>{t("taskTitle")}<input autoFocus value={newTitle} onChange={(event) => setNewTitle(event.target.value)} /></label><label className="isolated-toggle"><input type="checkbox" checked={newIsolated} onChange={(event) => setNewIsolated(event.target.checked)} /><span><strong>{t("isolatedWorkspace")}</strong><small>{t("isolatedWorkspaceHint")}</small></span></label><footer><button type="button" onClick={() => setNewTaskOpen(false)}>{t("cancel")}</button><button className="primary" disabled={busy}>{busy ? <CircleNotch className="spin" /> : <Plus />}{t("create")}</button></footer></motion.form></motion.div>}</AnimatePresence>
      <AnimatePresence>
        {sessionToDelete && (
          <motion.div
            className="modal-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onMouseDown={(event) => {
              if (event.target === event.currentTarget && !deletingSession && !mergingWorktree) {
                setSessionToDelete(null);
                setWorktreeReview(null);
              }
            }}
          >
            <motion.section
              className={`delete-session-dialog ${worktreeReview?.has_pending ? "with-review" : ""}`}
              role="dialog"
              aria-modal="true"
              aria-labelledby="delete-session-title"
              initial={reducedMotion ? false : { opacity: 0, y: 12, scale: 0.99 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
            >
              <span>DELETE SESSION</span>
              <h2 id="delete-session-title">{t("deleteConversationTitle")}</h2>
              <strong>{sessionToDelete.title}</strong>
              {worktreeReviewLoading && <p>{t("worktreeReviewLoading")}</p>}
              {!worktreeReviewLoading && !worktreeReview?.has_pending && <p>{t("deleteConversationBody")}</p>}
              {!worktreeReviewLoading && worktreeReview?.has_pending && (
                <div className="worktree-review">
                  <p>
                    {language === "es"
                      ? `Esta sesión tiene ${worktreeReview.uncommitted_files} archivo(s) sin commitear y ${worktreeReview.commits_ahead} commit(s) sin fusionar en ${worktreeReview.base_branch}. Borrarla sin fusionar destruye ese trabajo.`
                      : `This session has ${worktreeReview.uncommitted_files} uncommitted file(s) and ${worktreeReview.commits_ahead} commit(s) not merged into ${worktreeReview.base_branch}. Deleting it without merging destroys that work.`}
                  </p>
                  <div className="worktree-review-diff">
                    <DiffBlock lines={unifiedDiffToLines(worktreeReview.diff)} />
                  </div>
                </div>
              )}
              <footer>
                <button disabled={deletingSession || mergingWorktree} onClick={() => { setSessionToDelete(null); setWorktreeReview(null); }}>{t("cancel")}</button>
                {worktreeReview?.has_pending ? (
                  <>
                    <button className="danger" disabled={deletingSession || mergingWorktree} onClick={() => void deleteConversation(true)}>
                      {deletingSession ? <CircleNotch className="spin" /> : <Trash />}
                      {t("discardAndDelete")}
                    </button>
                    <button className="primary" disabled={deletingSession || mergingWorktree} onClick={() => void mergeAndDeleteConversation()}>
                      {mergingWorktree ? <CircleNotch className="spin" /> : <GitMerge />}
                      {t("mergeAndDelete")} {worktreeReview.base_branch}
                    </button>
                  </>
                ) : (
                  <button className="danger" disabled={deletingSession || worktreeReviewLoading} onClick={() => void deleteConversation(false)}>
                    {deletingSession ? <CircleNotch className="spin" /> : <Trash />}
                    {t("delete")}
                  </button>
                )}
              </footer>
            </motion.section>
          </motion.div>
        )}
      </AnimatePresence>
    </MotionConfig>
  );
}
