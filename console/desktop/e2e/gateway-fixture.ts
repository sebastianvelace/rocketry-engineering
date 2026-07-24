import type { Page } from "@playwright/test";

export const now = "2026-07-23T23:00:00Z";
export const baseSession = {
  id: "session-1",
  provider: "claude",
  provider_session_id: "claude-thread",
  workspace: "/workspace/rocketry-portfolio",
  title: "Acceptance session",
  status: "ready",
  created_at: now,
  updated_at: now,
  metadata: {},
};

export const events = [
  {
    sequence: 1,
    id: "capabilities",
    session_id: "session-1",
    created_at: now,
    type: "session",
    role: null,
    text: "Provider capabilities",
    data: {
      commands: [
        { name: "model", description: "Select model", argumentHint: "<model>" },
        { name: "compact", description: "Compact context", argumentHint: "" },
      ],
      models: [
        {
          value: "default",
          resolvedModel: "claude-sonnet-5",
          displayName: "Default (recommended)",
          description: "Sonnet 5 · Efficient for routine tasks",
        },
        {
          value: "opus",
          resolvedModel: "claude-opus-4-8",
          displayName: "Opus",
          description: "Best for complex tasks",
          supportsFastMode: true,
        },
      ],
    },
    raw: {},
  },
  {
    sequence: 2,
    id: "user-message",
    session_id: "session-1",
    created_at: now,
    type: "user_message",
    role: "user",
    text: "Audit the test",
    data: {},
    raw: {},
  },
  {
    sequence: 3,
    id: "assistant-message",
    session_id: "session-1",
    created_at: now,
    type: "assistant_message",
    role: "assistant",
    text: "**Verified**\n\n- Serial path\n- Simulation path",
    data: {},
    raw: {},
  },
];

type MockRun = {
  id: number;
  kind: string;
  note: string;
  created_at: string;
  columns: string[];
  rows: unknown[][];
  meta: Record<string, unknown>;
};

export type MockGatewayController = {
  session: Record<string, unknown>;
  runs: MockRun[];
  lastSteer: string;
  isSocketConnected: () => boolean;
  emit: (event: Record<string, unknown>) => Promise<void>;
};

const controllers = new WeakMap<Page, MockGatewayController>();

export function mockGatewayController(page: Page): MockGatewayController {
  const controller = controllers.get(page);
  if (!controller) throw new Error("The mock gateway has not been installed for this page.");
  return controller;
}

export async function mockGateway(
  page: Page,
  sessionEvents: typeof events = events,
  sessionApprovals: Record<string, unknown>[] = [],
  worktreeReviewBySessionId: Record<string, Record<string, unknown>> = {},
) {
  let selectedModel = "default";
  let sessionLoads = 0;
  let sessionDeleted = false;
  let lastResolvedApproval: Record<string, unknown> | null = null;
  const createdSessions: Record<string, unknown>[] = [];
  const mergedSessionIds = new Set<string>();
  const deletedSessionIds = new Set<string>();
  let socket: { send: (message: string) => void } | null = null;
  const controller: MockGatewayController = {
    session: { ...baseSession },
    runs: [],
    lastSteer: "",
    isSocketConnected: () => socket !== null,
    emit: async (event) => {
      // Playwright reports the routed socket as open just before the page-side
      // message listener is guaranteed to be active. Real gateway events are
      // durable and replay after reconnect; deliver this fixture event more
      // than once to model that at-least-once contract and verify client-side
      // idempotency instead of relying on a single in-memory timing window.
      const payload = JSON.stringify(event);
      for (const delay of [50, 100, 150]) {
        await new Promise((resolve) => setTimeout(resolve, delay));
        socket?.send(payload);
      }
    },
  };
  controllers.set(page, controller);
  await page.routeWebSocket("ws://gateway.test/**", (route) => {
    socket = route;
  });
  await page.route("http://gateway.test/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    let payload: Record<string, unknown>;
    let status = 200;

    if (path === "/api/sessions" && method === "GET") {
      sessionLoads += 1;
      if (sessionLoads === 1) {
        status = 503;
        payload = { ok: false, error: { message: "Gateway is still starting" } };
      } else {
        payload = {
          ok: true,
          sessions: [
            ...createdSessions.filter((session) => !deletedSessionIds.has(session.id as string)),
            ...(sessionDeleted ? [] : [{ ...controller.session, metadata: { ...((controller.session.metadata as Record<string, unknown>) || {}), model: selectedModel } }]),
          ],
        };
      }
    } else if (path === "/api/sessions" && method === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      const id = `session-${createdSessions.length + 2}`;
      const isolated = Boolean(body.isolated);
      const session = {
        ...baseSession,
        id,
        title: body.title || "New task",
        provider: body.provider,
        workspace: isolated ? `/workspace/rocketry-portfolio/.rocketry/worktrees/${id}` : baseSession.workspace,
        metadata: isolated ? { isolated_workspace: true, worktree_branch: `workstation/${id}` } : {},
      };
      createdSessions.unshift(session);
      payload = { ok: true, session };
      status = 201;
    } else if (path === "/api/status") {
      payload = {
        ok: true,
        ports: ["/dev/ttyUSB0"],
        saved_runs: 3,
        openmotor_ready: true,
        openrocket_ready: true,
      };
    } else if (path === "/api/runs") {
      payload = {
        ok: true,
        runs: controller.runs.map((run) => ({
          id: run.id,
          kind: run.kind,
          note: run.note,
          created_at: run.created_at,
          row_count: run.rows.length,
          columns: run.columns,
          meta: run.meta,
        })),
      };
    } else if (path === "/api/runs/compare" && method === "POST") {
      const ids = (request.postDataJSON().run_ids || []) as number[];
      const selected = ids
        .map((id) => controller.runs.find((run) => run.id === id))
        .filter((run): run is MockRun => Boolean(run));
      const metricNames = selected[0]?.rows
        .filter((row) => typeof row[0] === "string" && typeof row[1] === "number")
        .map((row) => String(row[0])) || [];
      payload = {
        ok: true,
        comparison: {
          artifact_id: "comparison-1",
          artifact_path: "/tmp/comparison.json",
          mode: "flight_metrics",
          kind: "FLIGHT",
          x_column: "metric",
          y_column: "value",
          series: [],
          runs: selected.map((run) => ({
            run_id: run.id,
            note: run.note,
            created_at: run.created_at,
            meta: run.meta,
          })),
          metrics: metricNames.map((name) => ({
            name,
            unit: name === "apogee" ? "m" : name === "mach" ? "Ma" : "",
            values: selected.map((run) => ({
              run_id: run.id,
              value: Number(run.rows.find((row) => row[0] === name)?.[1]),
            })),
          })),
        },
      };
    } else if (path.match(/^\/api\/runs\/\d+$/)) {
      const id = Number(path.split("/").pop());
      const run = controller.runs.find((item) => item.id === id);
      if (run) {
        payload = { ok: true, run: { ...run, row_count: run.rows.length } };
      } else {
        status = 404;
        payload = { ok: false, error: { code: "not_found", message: "Run not found" } };
      }
    } else if (path === "/api/artifacts") {
      payload = { ok: true, artifacts: [] };
    } else if (path === "/api/usage") {
      payload = {
        ok: true,
        refreshed_at: now,
        cached: false,
        providers: {
          claude: {
            available: true,
            source: "claude /usage",
            windows: [
              { id: "session", used_percent: 3, resets_at_label: "11:30pm" },
              { id: "week", used_percent: 54, resets_at_label: "Jul 25" },
            ],
            activity: {
              day: { requests: 282, sessions: 9 },
              week: { requests: 1105, sessions: 19 },
            },
          },
          codex: {
            available: true,
            source: "codex app-server",
            rate_limits: {
              rateLimits: {
                planType: "plus",
                primary: { usedPercent: 78, resetsAt: 1780000000 },
              },
            },
            token_usage: {
              summary: { lifetimeTokens: 480718386, peakDailyTokens: 28000000 },
              dailyUsageBuckets: [
                { startDate: "2026-07-22", tokens: 12000000 },
                { startDate: "2026-07-23", tokens: 28000000 },
              ],
            },
          },
        },
        local: {
          claude: { input_tokens: 24, output_tokens: 5831 },
          codex: { total_tokens: 59144 },
        },
      };
    } else if (path === "/api/sessions/session-1" && method === "DELETE") {
      sessionDeleted = true;
      payload = { ok: true, deleted_session_id: "session-1" };
    } else if (path === "/api/sessions/session-1/connect") {
      payload = { ok: true, session: { ...controller.session, metadata: { model: selectedModel } } };
    } else if (path === "/api/sessions/session-1/events") {
      payload = { ok: true, events: sessionEvents };
    } else if (path === "/api/sessions/session-1/approvals") {
      payload = { ok: true, approvals: lastResolvedApproval ? [] : sessionApprovals };
    } else if (path.startsWith("/api/approvals/") && method === "POST") {
      lastResolvedApproval = request.postDataJSON();
      payload = { ok: true, approval: { id: path.split("/").pop(), status: "approved" } };
    } else if (path === "/api/sessions/session-1/model" && method === "POST") {
      selectedModel = String(request.postDataJSON().model);
      payload = { ok: true, session: { ...baseSession, metadata: { model: selectedModel } } };
    } else if (path === "/api/sessions/session-1/steer" && method === "POST") {
      controller.lastSteer = String(request.postDataJSON().text || "");
      payload = { ok: true, event: { ...events[0], id: "steer", text: "Active turn guided" } };
    } else if (path.match(/^\/api\/sessions\/[^/]+\/worktree\/merge$/) && method === "POST") {
      const id = path.split("/")[3];
      mergedSessionIds.add(id);
      const review = worktreeReviewBySessionId[id] || {};
      payload = { ok: true, merge: { base_branch: review.base_branch || "main", merge_result: "deadbeef" } };
    } else if (path.match(/^\/api\/sessions\/[^/]+\/worktree$/) && method === "GET") {
      const id = path.split("/")[3];
      const review = worktreeReviewBySessionId[id];
      const hasPending = Boolean(review) && !mergedSessionIds.has(id);
      payload = {
        ok: true,
        review: {
          branch: `workstation/${id}`,
          base_branch: "main",
          uncommitted_files: 0,
          commits_ahead: 0,
          diff: "",
          ...review,
          has_pending: hasPending,
        },
      };
    } else if (path.match(/^\/api\/sessions\/[^/]+$/) && method === "DELETE") {
      const id = path.split("/")[3];
      const review = worktreeReviewBySessionId[id];
      const forced = url.searchParams.get("force") === "true";
      if (review && !mergedSessionIds.has(id) && !forced) {
        status = 409;
        payload = {
          ok: false,
          error: {
            code: "worktree_has_pending_changes",
            message: "Worktree has pending changes.",
            details: {
              status: {
                branch: `workstation/${id}`,
                base_branch: review.base_branch || "main",
                uncommitted_files: review.uncommitted_files ?? 1,
                commits_ahead: review.commits_ahead ?? 0,
              },
            },
          },
        };
      } else {
        deletedSessionIds.add(id);
        if (id === "session-1") sessionDeleted = true;
        payload = { ok: true, deleted_session_id: id };
      }
    } else if (path.match(/^\/api\/sessions\/[^/]+\/connect$/)) {
      const id = path.split("/")[3];
      const created = createdSessions.find((session) => session.id === id);
      payload = { ok: true, session: created || { ...baseSession, metadata: { model: selectedModel } } };
    } else if (path.match(/^\/api\/sessions\/[^/]+\/events$/)) {
      payload = { ok: true, events: [] };
    } else if (path.match(/^\/api\/sessions\/[^/]+\/approvals$/)) {
      payload = { ok: true, approvals: [] };
    } else if (path === "/api/bench/capture" && method === "POST") {
      status = 422;
      payload = {
        ok: false,
        error: {
          code: "capture_timeout",
          message: "No complete block was received before the timeout.",
          details: {
            diagnostics: {
              bytes_received: 96,
              lines_received: 4,
              last_line: "# BLOCK STEP R=220",
              saw_block_start: true,
              rows_captured: 0,
              elapsed_s: 15.03,
            },
          },
        },
      };
    } else if (path === "/api/flight/config") {
      payload = {
        ok: true,
        motor_curves: ["E_sintubo.eng"],
        architectures: ["minimum_diameter"],
      };
    } else {
      payload = { ok: true };
    }

    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
}
