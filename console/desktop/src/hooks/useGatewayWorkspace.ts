import { useCallback, useEffect, useRef, useState } from "react";
import { GatewayApi, connectGateway } from "../api";
import type {
  Artifact,
  EngineeringStatus,
  Provider,
  RunRecord,
  RunSummary,
  Session,
  WorktreeReview,
} from "../types";

export type BootStage = "gateway" | "workspace";

// Owns the gateway connection lifecycle (boot, retry-with-backoff) plus the
// workspace-wide data every view reads: sessions, engineering status, saved
// runs and artifacts. This is the "conversation" side of the app boundary
// the technical audit asked to extract out of App.tsx.
export function useGatewayWorkspace() {
  const [api, setApi] = useState<GatewayApi | null>(null);
  const [connectionError, setConnectionError] = useState("");
  const [bootStage, setBootStage] = useState<BootStage>("gateway");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [status, setStatus] = useState<EngineeringStatus | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState<RunRecord | null>(null);
  const [newAgentRunId, setNewAgentRunId] = useState<number | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const knownRunIds = useRef<Set<number>>(new Set());
  const agentRunTimer = useRef<number | undefined>(undefined);

  const loadGateway = useCallback(async () => {
    setConnectionError("");
    setBootStage("gateway");
    try {
      const client = new GatewayApi(await connectGateway());
      setBootStage("workspace");
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
      knownRunIds.current = new Set(nextRuns.map((run) => run.id));
      setArtifacts(nextArtifacts);
      setSelectedId((current) => current || nextSessions[0]?.id || null);
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : String(error));
    }
  }, []);

  useEffect(() => { void loadGateway(); }, [loadGateway]);
  useEffect(() => () => window.clearTimeout(agentRunTimer.current), []);

  // followNewest asks: after refreshing, did a run we didn't know about
  // appear (the affinity heuristic an agent-triggered capture/sweep/flight
  // relies on)? onNewRun lets the caller react (e.g. switch a tab) without
  // this hook knowing anything about tabs.
  const refreshEngineering = useCallback(async (
    followNewest = false,
    preferredRunId: number | null = null,
    onNewRun?: (run: RunSummary) => void,
  ) => {
    if (!api) return;
    const [nextStatus, nextRuns, nextArtifacts] = await Promise.all([api.status(), api.runs(), api.artifacts()]);
    const newRun = followNewest
      ? nextRuns.find((run) => run.id === preferredRunId)
        || nextRuns.find((run) => !knownRunIds.current.has(run.id))
      : undefined;
    knownRunIds.current = new Set(nextRuns.map((run) => run.id));
    setStatus(nextStatus);
    setRuns(nextRuns);
    setArtifacts(nextArtifacts);
    if (newRun) {
      const record = await api.run(newRun.id);
      setSelectedRun(record);
      setNewAgentRunId(newRun.id);
      window.clearTimeout(agentRunTimer.current);
      agentRunTimer.current = window.setTimeout(() => setNewAgentRunId(null), 10_000);
      onNewRun?.(newRun);
    }
  }, [api]);

  const refreshSessions = useCallback(async () => { if (api) setSessions(await api.sessions()); }, [api]);

  const openSavedRun = useCallback(async (runId: number) => {
    if (!api) return null;
    await refreshEngineering();
    const run = await api.run(runId);
    setSelectedRun(run);
    return run;
  }, [api, refreshEngineering]);

  useEffect(() => {
    if (!api || !runs.length || selectedRun) return;
    void api.run(runs[0].id).then(setSelectedRun);
  }, [api, runs, selectedRun]);

  const createSession = useCallback(async (provider: Provider, title: string, isolated: boolean) => {
    if (!api) throw new Error("Gateway not connected.");
    const session = await api.createSession(provider, title, isolated);
    setSessions((current) => [session, ...current]);
    setSelectedId(session.id);
    return session;
  }, [api]);

  const deleteSession = useCallback(async (sessionId: string, force = false) => {
    if (!api) return;
    await api.deleteSession(sessionId, force);
    setSessions((current) => current.filter((session) => session.id !== sessionId));
  }, [api]);

  const mergeWorktree = useCallback(async (sessionId: string) => {
    if (!api) return;
    await api.mergeWorktree(sessionId);
  }, [api]);

  const getWorktreeReview = useCallback(async (sessionId: string): Promise<WorktreeReview> => {
    if (!api) throw new Error("Gateway not connected.");
    return api.getWorktreeReview(sessionId);
  }, [api]);

  return {
    api, connectionError, setConnectionError, bootStage, loadGateway,
    sessions, setSessions, selectedId, setSelectedId,
    status, runs, artifacts, selectedRun, setSelectedRun, newAgentRunId,
    refreshEngineering, refreshSessions, openSavedRun,
    createSession, deleteSession, mergeWorktree, getWorktreeReview,
  };
}
