import { useEffect, useRef, useState } from "react";
import type { GatewayApi } from "../api";
import type { AgentEvent, Approval } from "../types";
import { extractRunId } from "../agentEvents";

interface UseSessionTransportOptions {
  api: GatewayApi | null;
  selectedId: string | null;
  onConnectionError: (message: string) => void;
  onSessionActivity: () => Promise<void> | void;
  onRunCompleted: (runId: number | null) => void;
}

// Owns the live WebSocket transport for whichever session is selected:
// warm-connect on first selection, event/approval streaming with
// auto-reconnect, and the actions that mutate that stream. Independent of
// which session is selected, of the composer, and of layout — this is the
// "session transport" boundary the technical audit asked to extract.
export function useSessionTransport({
  api,
  selectedId,
  onConnectionError,
  onSessionActivity,
  onRunCompleted,
}: UseSessionTransportOptions) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [socketConnected, setSocketConnected] = useState(false);
  const [warming, setWarming] = useState(false);
  const warmed = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!api || !selectedId || warmed.current.has(selectedId)) return;
    warmed.current.add(selectedId);
    setWarming(true);
    void api.connectSession(selectedId)
      .then(async () => {
        onConnectionError("");
        await onSessionActivity();
      })
      .catch((error) => {
        warmed.current.delete(selectedId);
        onConnectionError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => setWarming(false));
  }, [api, selectedId, onConnectionError, onSessionActivity]);

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
        if (event.type === "approval_requested" || event.type === "approval_resolved") {
          void api.approvals(selectedId).then(setApprovals);
        }
        if (event.type === "tool_completed") {
          onRunCompleted(extractRunId(event.data));
        }
        if (event.type === "session" || event.type === "error") void onSessionActivity();
      }, (connected) => {
        setSocketConnected(connected);
        if (!connected && active) reconnectTimer = window.setTimeout(connect, 1200);
      });
    };
    void connect().catch((error) => onConnectionError(String(error)));
    return () => { active = false; window.clearTimeout(reconnectTimer); unsubscribe(); setSocketConnected(false); };
  }, [api, selectedId, onConnectionError, onRunCompleted, onSessionActivity]);

  async function resolveApproval(approval: Approval, approved: boolean, forSession = false, answers?: Record<string, string>) {
    if (!api) return;
    await api.resolveApproval(approval.id, approved, forSession, answers);
    setApprovals(await api.approvals(approval.session_id));
  }

  async function retryConnection() {
    if (!api || !selectedId) return;
    setWarming(true);
    onConnectionError("");
    try {
      await api.connectSession(selectedId);
      warmed.current.add(selectedId);
      await onSessionActivity();
    } catch (error) {
      warmed.current.delete(selectedId);
      onConnectionError(error instanceof Error ? error.message : String(error));
    } finally {
      setWarming(false);
    }
  }

  // Lets a caller that deletes a session outside this hook (App owns that
  // flow, see useGatewayWorkspace.deleteSession) drop its warm-connect
  // memory and clear the feed immediately instead of waiting a render.
  function forgetSession(sessionId: string) {
    warmed.current.delete(sessionId);
  }

  function resetTransport() {
    setEvents([]);
    setApprovals([]);
  }

  return {
    events, approvals, socketConnected, warming,
    resolveApproval, retryConnection, forgetSession, resetTransport,
  };
}
