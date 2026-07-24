import { useCallback, useMemo, useState } from "react";
import type { FormEvent } from "react";
import type { GatewayApi } from "../api";
import type { ProviderCommand, Session } from "../types";

interface UseComposerOptions {
  api: GatewayApi | null;
  selectedId: string | null;
  selectedSession: Session | null;
  commands: ProviderCommand[];
  busy: boolean;
  setBusy: (busy: boolean) => void;
  onError: (message: string) => void;
  updateSessions: (updater: (sessions: Session[]) => Session[]) => void;
  selectSession: (sessionId: string) => void;
  requestUsageView: () => void;
  refreshSessions: () => Promise<void>;
}

// Owns composer text, slash-command matching, model selection and message
// dispatch (send, steer an active Codex turn, or run a provider command).
// This is the "conversation behavior" boundary the technical audit asked to
// extract out of App.tsx, kept independent of transport and layout.
export function useComposer({
  api, selectedId, selectedSession, commands, busy, setBusy,
  onError, updateSessions, selectSession, requestUsageView, refreshSessions,
}: UseComposerOptions) {
  const [composer, setComposer] = useState("");
  const [modelPickerOpen, setModelPickerOpen] = useState(false);

  const commandMatches = useMemo(() => {
    if (!composer.startsWith("/") || composer.includes(" ")) return [];
    const query = composer.slice(1).toLowerCase();
    return commands.filter((command) => command.name.toLowerCase().includes(query)).slice(0, 7);
  }, [commands, composer]);

  const changeModel = useCallback(async (model: string) => {
    if (!api || !selectedId) return;
    setBusy(true);
    onError("");
    try {
      const updated = await api.setModel(selectedId, model);
      updateSessions((current) => current.map((session) => session.id === updated.id ? updated : session));
      setComposer("");
      setModelPickerOpen(false);
    } catch (error) {
      onError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }, [api, selectedId, setBusy, onError, updateSessions]);

  const executeAgentCommand = useCallback(async (command: string, argumentsText: string) => {
    if (!api || !selectedId) return;
    setBusy(true);
    onError("");
    try {
      const result = await api.executeCommand(selectedId, command, argumentsText);
      if (result.action === "usage") {
        requestUsageView();
      } else if (result.action === "created") {
        updateSessions((current) => [result.session, ...current.filter((item) => item.id !== result.session.id)]);
        selectSession(result.session.id);
      } else {
        updateSessions((current) => current.map((session) => session.id === result.session.id ? result.session : session));
      }
      setComposer("");
      await refreshSessions();
    } catch (error) {
      onError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }, [api, selectedId, setBusy, onError, requestUsageView, updateSessions, selectSession, refreshSessions]);

  const sendMessage = useCallback(async (event: FormEvent) => {
    event.preventDefault();
    if (!api || !selectedId || !composer.trim() || busy) return;
    const value = composer.trim();
    const steeringActiveTurn = selectedSession?.provider === "codex" && selectedSession.status === "running";
    if (steeringActiveTurn) {
      setComposer("");
      setBusy(true);
      try {
        await api.steer(selectedId, value);
      } catch (error) {
        onError(error instanceof Error ? error.message : String(error));
        setComposer(value);
      } finally {
        setBusy(false);
      }
      return;
    }
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
    try {
      await api.send(selectedId, value);
      await refreshSessions();
    } catch (error) {
      onError(error instanceof Error ? error.message : String(error));
      setComposer(value);
    } finally {
      setBusy(false);
    }
  }, [api, selectedId, composer, busy, selectedSession, setBusy, onError, changeModel, executeAgentCommand, refreshSessions]);

  function chooseCommand(command: ProviderCommand) {
    if (command.name === "model") {
      setComposer("");
      setModelPickerOpen(true);
      return;
    }
    setComposer(`/${command.name}${command.argumentHint ? " " : ""}`);
  }

  return {
    composer, setComposer, modelPickerOpen, setModelPickerOpen,
    commandMatches, sendMessage, executeAgentCommand, changeModel, chooseCommand,
  };
}
