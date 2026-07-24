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
  metadata: Record<string, unknown>;
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

export interface ProviderCommand {
  name: string;
  description: string;
  argumentHint?: string;
  aliases?: string[];
}

export interface ProviderModel {
  value: string;
  resolvedModel: string;
  displayName: string;
  description: string;
  supportsEffort?: boolean;
  supportedEffortLevels?: string[];
  supportsFastMode?: boolean;
  isDefault?: boolean;
}

export interface CommandResult {
  action: "usage" | "created" | "event" | "renamed" | "running";
  session: Session;
  event?: AgentEvent;
}

export interface UsageWindow {
  id?: string;
  used_percent?: number;
  usedPercent?: number;
  resets_at_label?: string;
  resetsAt?: number | null;
  windowDurationMins?: number | null;
}

export interface ProviderUsage {
  available: boolean;
  error?: string;
  source?: string;
  subscription?: boolean;
  windows?: UsageWindow[];
  activity?: Record<string, { requests: number; sessions: number }>;
  rate_limits?: {
    rateLimits?: {
      planType?: string;
      primary?: UsageWindow | null;
      secondary?: UsageWindow | null;
      credits?: { balance?: string | null; hasCredits?: boolean; unlimited?: boolean } | null;
    };
    rateLimitsByLimitId?: Record<string, {
      planType?: string;
      primary?: UsageWindow | null;
      secondary?: UsageWindow | null;
    }> | null;
    rateLimitResetCredits?: { availableCount: number };
  };
  token_usage?: {
    summary?: {
      lifetimeTokens?: number | null;
      peakDailyTokens?: number | null;
      longestRunningTurnSec?: number | null;
      currentStreakDays?: number | null;
      longestStreakDays?: number | null;
    };
    dailyUsageBuckets?: Array<{ startDate: string; tokens: number }> | null;
  };
}

export interface UsageSnapshot {
  ok: boolean;
  refreshed_at: string;
  cached: boolean;
  providers: {
    claude: ProviderUsage;
    codex: ProviderUsage;
  };
  local: {
    claude: Record<string, number>;
    codex: Record<string, number>;
  };
}

export interface WiringPin {
  from: string;
  to: string;
  how: string;
}

export interface WiringGuide {
  artifact_id: string;
  circuit: string;
  short: string;
  purpose: string;
  use_for: string;
  parts: string[];
  before: string;
  verify: string[];
  pins: WiringPin[];
  svg: string;
}

export interface OperationResult {
  run_id: number;
  [key: string]: unknown;
}

export interface FlightConfig {
  motor_curves: string[];
  architectures: string[];
}

export interface ComparisonSeries {
  run_id: number;
  note: string;
  points: { x: number; y: number }[];
}

export interface RunComparison {
  artifact_id: string;
  artifact_path: string;
  kind: string;
  x_column: string;
  y_column: string;
  series: ComparisonSeries[];
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
