export type Provider = "codex" | "claude";

export type SessionStatus =
  | "created"
  | "ready"
  | "running"
  | "waiting_approval"
  | "interrupting"
  | "interrupted"
  | "completed"
  | "failed";

export interface Session {
  id: string;
  provider: Provider;
  provider_session_id: string | null;
  workspace: string;
  title: string;
  status: SessionStatus;
  created_at: string;
  updated_at: string;
}

export interface AgentEvent {
  sequence: number;
  id: string;
  session_id: string;
  created_at: string;
  type: string;
  role: string | null;
  text: string;
  data: Record<string, unknown>;
}

export interface Approval {
  id: string;
  session_id: string;
  status: "pending" | "approved" | "denied" | "cancelled";
  action: string;
  details: Record<string, unknown>;
}

export interface RunSummary {
  id: number;
  created_at: string;
  kind: string;
  meta: Record<string, unknown>;
  note: string;
}

export interface RunRecord extends RunSummary {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  offset: number;
}

export interface EngineeringStatus {
  ports: string[];
  saved_runs: number;
  openmotor_ready: boolean;
  openrocket_ready: boolean;
}

export interface Artifact {
  id: string;
  kind: string;
  created_at: string;
  media_type: string;
  path: string;
  metadata: Record<string, unknown>;
  download_url: string;
}

export interface GatewayConnection {
  baseUrl: string;
  token: string;
  workspace: string;
}
