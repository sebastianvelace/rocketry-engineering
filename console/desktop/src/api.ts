import { invoke, isTauri } from "@tauri-apps/api/core";
import type {
  AgentEvent,
  Approval,
  Artifact,
  CommandResult,
  EngineeringStatus,
  FlightConfig,
  GatewayConnection,
  Provider,
  RunRecord,
  RunComparison,
  RunSummary,
  Session,
  UsageSnapshot,
  WiringGuide,
  OperationResult,
} from "./types";

export async function connectGateway(): Promise<GatewayConnection> {
  if (isTauri()) {
    return invoke<GatewayConnection>("start_gateway");
  }
  return {
    baseUrl: import.meta.env.VITE_GATEWAY_URL || "http://127.0.0.1:8765",
    token: import.meta.env.VITE_GATEWAY_TOKEN || "development-token",
    workspace: import.meta.env.VITE_WORKSPACE || "..",
  };
}

export class GatewayApi {
  constructor(readonly connection: GatewayConnection) {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.connection.baseUrl}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${this.connection.token}`,
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
    const payload = await response.json();
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.error?.message || `Gateway request failed (${response.status})`);
    }
    return payload as T;
  }

  async sessions(): Promise<Session[]> {
    return (await this.request<{ sessions: Session[] }>("/api/sessions")).sessions;
  }

  async createSession(provider: Provider, title: string): Promise<Session> {
    const payload = await this.request<{ session: Session }>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({
        provider,
        title,
        workspace: this.connection.workspace,
      }),
    });
    return payload.session;
  }

  async connectSession(sessionId: string): Promise<Session> {
    return (
      await this.request<{ session: Session }>(
        `/api/sessions/${sessionId}/connect`,
        { method: "POST" },
      )
    ).session;
  }

  async setModel(sessionId: string, model: string): Promise<Session> {
    return (
      await this.request<{ session: Session }>(
        `/api/sessions/${sessionId}/model`,
        {
          method: "POST",
          body: JSON.stringify({ model }),
        },
      )
    ).session;
  }

  async executeCommand(
    sessionId: string,
    command: string,
    argumentsText = "",
  ): Promise<CommandResult> {
    return this.request<CommandResult>(`/api/sessions/${sessionId}/commands`, {
      method: "POST",
      body: JSON.stringify({ command, arguments: argumentsText }),
    });
  }

  async usage(force = false): Promise<UsageSnapshot> {
    return this.request<UsageSnapshot>(`/api/usage${force ? "?refresh=1" : ""}`);
  }

  async events(sessionId: string, after = 0): Promise<AgentEvent[]> {
    return (
      await this.request<{ events: AgentEvent[] }>(
        `/api/sessions/${sessionId}/events?after=${after}&limit=2000`,
      )
    ).events;
  }

  async send(sessionId: string, text: string): Promise<void> {
    await this.request(`/api/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  }

  async interrupt(sessionId: string): Promise<void> {
    await this.request(`/api/sessions/${sessionId}/interrupt`, {
      method: "POST",
    });
  }

  async approvals(sessionId: string): Promise<Approval[]> {
    return (
      await this.request<{ approvals: Approval[] }>(
        `/api/sessions/${sessionId}/approvals`,
      )
    ).approvals;
  }

  async resolveApproval(
    approvalId: string,
    approved: boolean,
    forSession = false,
  ): Promise<void> {
    await this.request(`/api/approvals/${approvalId}`, {
      method: "POST",
      body: JSON.stringify({ approved, for_session: forSession }),
    });
  }

  async status(): Promise<EngineeringStatus> {
    return this.request<EngineeringStatus>("/api/status");
  }

  async wiring(language: string): Promise<WiringGuide[]> {
    return (
      await this.request<{ guides: WiringGuide[] }>(
        `/api/wiring?language=${encodeURIComponent(language)}`,
      )
    ).guides;
  }

  async captureBench(payload: Record<string, unknown>): Promise<OperationResult> {
    return (
      await this.request<{ result: OperationResult }>("/api/bench/capture", {
        method: "POST",
        body: JSON.stringify(payload),
      })
    ).result;
  }

  async motorSweep(payload: Record<string, unknown>): Promise<OperationResult> {
    return (
      await this.request<{ result: OperationResult }>("/api/motor/sweep", {
        method: "POST",
        body: JSON.stringify(payload),
      })
    ).result;
  }

  async flightConfig(): Promise<FlightConfig> {
    return this.request<FlightConfig>("/api/flight/config");
  }

  async runFlight(payload: Record<string, unknown>): Promise<OperationResult> {
    return (
      await this.request<{ result: OperationResult }>("/api/flight/run", {
        method: "POST",
        body: JSON.stringify(payload),
      })
    ).result;
  }

  async runs(): Promise<RunSummary[]> {
    return (await this.request<{ runs: RunSummary[] }>("/api/runs")).runs;
  }

  async run(id: number): Promise<RunRecord> {
    return (await this.request<{ run: RunRecord }>(`/api/runs/${id}`)).run;
  }

  async compareRuns(runIds: number[]): Promise<RunComparison> {
    return (
      await this.request<{ comparison: RunComparison }>("/api/runs/compare", {
        method: "POST",
        body: JSON.stringify({ run_ids: runIds }),
      })
    ).comparison;
  }

  async exportRun(id: number): Promise<Artifact> {
    return (
      await this.request<{ artifact: Artifact }>(`/api/runs/${id}/export`, {
        method: "POST",
      })
    ).artifact;
  }

  async deleteRun(id: number): Promise<void> {
    await this.request(`/api/runs/${id}`, { method: "DELETE" });
  }

  async artifacts(): Promise<Artifact[]> {
    return (await this.request<{ artifacts: Artifact[] }>("/api/artifacts")).artifacts;
  }

  artifactUrl(artifact: Artifact): string {
    return `${this.connection.baseUrl}${artifact.download_url}`;
  }

  async openArtifact(artifact: Artifact): Promise<void> {
    const response = await fetch(this.artifactUrl(artifact), {
      headers: { Authorization: `Bearer ${this.connection.token}` },
    });
    if (!response.ok) {
      throw new Error(`Artifact download failed (${response.status})`);
    }
    const objectUrl = URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = artifact.path.split("/").at(-1) || artifact.id;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  }

  subscribe(
    sessionId: string,
    after: number,
    onEvent: (event: AgentEvent) => void,
    onState: (connected: boolean) => void,
  ): () => void {
    const url = new URL(this.connection.baseUrl);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = `/ws/sessions/${sessionId}`;
    url.searchParams.set("after", String(after));
    const socket = new WebSocket(url, ["rocketry", this.connection.token]);
    socket.onopen = () => onState(true);
    socket.onclose = () => onState(false);
    socket.onerror = () => onState(false);
    socket.onmessage = (message) => {
      onEvent(JSON.parse(String(message.data)) as AgentEvent);
    };
    return () => socket.close(1000);
  }
}
