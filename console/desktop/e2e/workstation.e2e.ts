import { expect, test, type Page } from "@playwright/test";

const now = "2026-07-23T23:00:00Z";
const baseSession = {
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

const events = [
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

async function mockGateway(
  page: Page,
  sessionEvents: typeof events = events,
  sessionApprovals: Record<string, unknown>[] = [],
) {
  let selectedModel = "default";
  let sessionLoads = 0;
  let sessionDeleted = false;
  let lastResolvedApproval: Record<string, unknown> | null = null;
  const createdSessions: Record<string, unknown>[] = [];
  await page.routeWebSocket("ws://gateway.test/**", () => {});
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
            ...createdSessions,
            ...(sessionDeleted ? [] : [{ ...baseSession, metadata: { model: selectedModel } }]),
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
      payload = { ok: true, runs: [] };
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
      payload = { ok: true, session: { ...baseSession, metadata: { model: selectedModel } } };
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

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("rocketry-language", "es");
    localStorage.setItem("rocketry-view", "agent");
    localStorage.setItem("rocketry-rail-width", "72");
  });
  await mockGateway(page);
});

test("agent workspace renders Markdown, repository scope and native model selection", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Acceptance session" })).toBeVisible();
  await expect(page.locator(".workspace-scope")).toContainText("repositorio completo");
  await expect(page.locator(".message.assistant strong")).toHaveText("Verified");
  await expect(page.locator(".message.assistant li")).toHaveCount(2);
  await expect(page.locator(".message-feed")).not.toContainText("**");

  const composer = page.locator("textarea");
  await composer.fill("/model");
  await composer.press("Enter");
  await expect(page.locator(".model-picker")).toBeVisible();
  await page.getByRole("button", { name: /Opus/ }).click();

  await expect(page.locator(".composer")).toContainText("opus / 2 commands");
  await expect(composer).toHaveValue("");
});

const richActivityEvents = [
  events[0],
  events[1],
  {
    sequence: 3,
    id: "thinking-1",
    session_id: "session-1",
    created_at: now,
    type: "thinking",
    role: "assistant",
    text: "Checking the CI log before answering",
    data: {},
    raw: {},
  },
  {
    sequence: 4,
    id: "tool-start-1",
    session_id: "session-1",
    created_at: now,
    type: "tool_started",
    role: null,
    text: "Edit",
    data: { tool: { id: "tool-1", name: "Edit", input: { file_path: "test_flaky.py", old_string: "random.seed()", new_string: "random.seed(0)" } } },
    raw: {},
  },
  {
    sequence: 5,
    id: "tool-done-1",
    session_id: "session-1",
    created_at: now,
    type: "tool_completed",
    role: null,
    text: "done",
    data: { tool_result: { tool_use_id: "tool-1", content: "12 passed", is_error: false } },
    raw: {},
  },
  {
    sequence: 6,
    id: "subagent-start-1",
    session_id: "session-1",
    created_at: now,
    type: "subagent_started",
    role: null,
    text: "Investigate flaky test",
    data: { task_id: "task-1", tool_use_id: "tool-2" },
    raw: {},
  },
  {
    sequence: 7,
    id: "subagent-done-1",
    session_id: "session-1",
    created_at: now,
    type: "subagent_completed",
    role: null,
    text: "Root cause: unseeded RNG",
    data: { task_id: "task-1", status: "completed" },
    raw: {},
  },
  {
    sequence: 8,
    id: "plan-1",
    session_id: "session-1",
    created_at: now,
    type: "plan_updated",
    role: null,
    text: "turn/plan/updated",
    data: { plan: [{ step: "Seed the RNG in the fixture", status: "completed" }] },
    raw: {},
  },
  {
    sequence: 9,
    id: "assistant-final",
    session_id: "session-1",
    created_at: now,
    type: "assistant_message",
    role: "assistant",
    text: "Fixed the flaky test.",
    data: {},
    raw: {},
  },
];

test("thinking, tool calls, subagents and plan updates render inline in the conversation", async ({ page }) => {
  await mockGateway(page, richActivityEvents);
  await page.goto("/");

  const feed = page.locator(".message-feed");
  await expect(feed.locator(".timeline-thinking")).toContainText("Checking the CI log");
  await expect(feed.locator(".timeline-subagent")).toContainText("Root cause: unseeded RNG");
  await expect(feed.locator(".timeline-plan li.status-completed")).toContainText("Seed the RNG in the fixture");

  const tool = feed.locator(".timeline-tool");
  await expect(tool).toContainText("Edit");
  await tool.locator(".timeline-tool-head").click();
  await expect(tool.locator(".timeline-tool-body")).toContainText("12 passed");
  await expect(tool.locator(".diff-remove")).toContainText("random.seed()");
  await expect(tool.locator(".diff-add")).toContainText("random.seed(0)");

  await expect(feed.locator(".message.assistant").last()).toContainText("Fixed the flaky test.");
});

test("AskUserQuestion renders a structured picker instead of raw JSON", async ({ page }) => {
  const askUserQuestionApproval = {
    id: "approval-1",
    session_id: "session-1",
    status: "pending",
    action: "AskUserQuestion",
    details: {
      kind: "ask_user_question",
      questions: [
        {
          question: "Which motor should the sweep target?",
          header: "Motor",
          multiSelect: false,
          options: [
            { label: "F-class", description: "25.4mm minimum diameter" },
            { label: "G-class", description: "" },
          ],
        },
      ],
    },
  };
  await mockGateway(page, [events[0], events[1]], [askUserQuestionApproval]);
  await page.goto("/");

  const panel = page.locator(".ask-user-question");
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("Which motor should the sweep target?");
  const answerButton = panel.getByRole("button", { name: "Responder" });
  await expect(answerButton).toBeDisabled();

  await panel.getByText("F-class").click();
  await expect(answerButton).toBeEnabled();
  await answerButton.click();

  await expect(panel).not.toBeVisible();
});

test("an isolated workspace toggle creates a session on its own worktree branch", async ({ page }) => {
  await mockGateway(page);
  await page.goto("/");

  await page.locator(".session-panel header button").click();
  await page.getByLabel("Nombre de la tarea").fill("Isolated fix");
  await page.getByText("Área de trabajo aislada").click();
  await page.getByRole("button", { name: "Crear" }).click();

  await expect(page.getByRole("heading", { name: "Isolated fix" })).toBeVisible();
  await expect(page.locator(".workspace-scope")).toContainText("worktree aislado");
  await expect(page.locator(".workspace-scope")).toContainText("workstation/session-2");
});

test("a Bench capture timeout shows what was actually received on the wire", async ({ page }) => {
  await mockGateway(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Banco" }).click();
  await page.getByRole("button", { name: "Capturar bloque" }).click();

  const diagnostics = page.locator(".bench-diagnostics");
  await expect(diagnostics).toBeVisible();
  await expect(diagnostics).toContainText("96");
  await expect(diagnostics).toContainText("# BLOCK STEP R=220");
});

test("conversation deletion requires confirmation and clears the selected session", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: "Borrar conversación: Acceptance session" }).click();
  const dialog = page.getByRole("dialog", { name: "¿Borrar esta conversación?" });
  await expect(dialog).toContainText("Acceptance session");
  await dialog.getByRole("button", { name: "Borrar" }).click();

  await expect(page.getByText("Aún no hay sesiones")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Selecciona o crea una sesión" })).toBeVisible();
});

test("navigation rail resizes and engineering selects keep the dark instrument theme", async ({ page }) => {
  await page.goto("/");

  const separator = page.getByRole("separator", { name: "Cambiar tamaño de navegación" });
  await separator.focus();
  await separator.press("ArrowRight");
  await expect(separator).toHaveAttribute("aria-valuenow", "78");

  await page.getByRole("button", { name: "Vuelo" }).click();
  await expect(page.getByRole("heading", { name: "Vuelo" })).toBeVisible();
  const select = page.locator(".engineering-view select").first();
  await expect(select).toBeVisible();
  await expect(select).toHaveCSS("background-color", "rgb(11, 16, 22)");
  await expect(select).toHaveCSS("color", "rgb(237, 240, 244)");
});

test("usage view displays real provider limits and distinguishes local tokens", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Uso" }).click();

  await expect(page.getByRole("heading", { name: "Uso" })).toBeVisible();
  await expect(page.locator(".usage-provider").filter({ hasText: "Claude Code" })).toContainText("54%");
  await expect(page.locator(".usage-provider").filter({ hasText: "Codex" })).toContainText("78%");
  await expect(page.locator(".usage-provider").filter({ hasText: "Codex" })).toContainText(/480[,.]7/);
  await expect(page.locator(".usage-foot")).toContainText("aproximación local del CLI");
});
