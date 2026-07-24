import { expect, test } from "@playwright/test";
import { baseSession, events, mockGateway, mockGatewayController, now } from "./gateway-fixture";

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

test("Codex accepts guidance while its current turn keeps running", async ({ page }) => {
  const gateway = mockGatewayController(page);
  gateway.session = { ...baseSession, provider: "codex", status: "running" };
  await page.goto("/");

  const composer = page.locator("textarea");
  await expect(composer).toHaveAttribute("placeholder", "Añade una indicación al turno activo de Codex...");
  await composer.fill("Mantén el motor y reduce la masa a 220 g.");
  await page.getByRole("button", { name: "Guiar turno" }).click();

  await expect.poll(() => gateway.lastSteer).toBe("Mantén el motor y reduce la masa a 220 g.");
  await expect(page.getByRole("button", { name: "Detener" })).toBeVisible();
});

test("a simulation completed by the agent opens and plots its new run automatically", async ({ page }) => {
  await page.goto("/");
  const gateway = mockGatewayController(page);
  await expect(page.locator(".agent-state")).toContainText("Listo");

  gateway.runs.unshift({
    id: 91,
    kind: "FLIGHT",
    note: "Agent flight simulation",
    created_at: now,
    columns: ["metric", "value"],
    rows: [
      ["apogee", 1503.4],
      ["mach", 0.826],
      ["vmax", 280.7],
      ["margin", 2.38],
    ],
    meta: { source: "OpenRocket", requested_by: "agent" },
  });
  gateway.emit({
    sequence: 4,
    id: "flight-tool-complete",
    session_id: "session-1",
    created_at: now,
    type: "tool_completed",
    role: null,
    text: "mcp__rocketry__run_flight",
    data: { tool_result: { content: JSON.stringify({ run_id: 91 }) } },
    raw: {},
  });

  await expect(page.getByText("Nuevo resultado del agente")).toBeVisible();
  await expect(page.locator(".run-dock-title")).toContainText("RUN #91");
  await expect(page.locator(".metric-field")).toContainText("1,503.4");
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
    data: {
      plan: [
        { step: "Seed the RNG in the fixture", status: "completed" },
        { step: "Re-run the flaky test", status: "inProgress" },
      ],
    },
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
  const inProgressStep = feed.locator(".timeline-plan li.status-inProgress");
  await expect(inProgressStep).toContainText("Re-run the flaky test");
  await expect(inProgressStep).toHaveCSS("color", "rgb(239, 68, 68)");

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

test("deleting an isolated session with pending work shows a diff and offers merge or discard", async ({ page }) => {
  await mockGateway(page, events, [], {
    "session-2": {
      base_branch: "main",
      uncommitted_files: 1,
      commits_ahead: 0,
      diff: "# Uncommitted changes in the worktree\ndiff --git a/fix.py b/fix.py\n@@ -1 +1 @@\n-broken()\n+fixed()\n",
    },
  });
  await page.goto("/");

  await page.locator(".session-panel header button").click();
  await page.getByLabel("Nombre de la tarea").fill("Isolated fix");
  await page.getByText("Área de trabajo aislada").click();
  await page.getByRole("button", { name: "Crear" }).click();
  await expect(page.getByRole("heading", { name: "Isolated fix" })).toBeVisible();

  await page.getByRole("button", { name: "Borrar conversación: Isolated fix" }).click();
  const dialog = page.getByRole("dialog", { name: "¿Borrar esta conversación?" });
  await expect(dialog).toContainText("1");
  await expect(dialog.locator(".diff-remove")).toContainText("broken()");
  await expect(dialog.locator(".diff-add")).toContainText("fixed()");
  await expect(dialog.getByRole("button", { name: /Fusionar en/ })).toBeVisible();

  await dialog.getByRole("button", { name: "Descartar y borrar" }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.locator(".session-row", { hasText: "Isolated fix" })).toHaveCount(0);
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

  await page.getByRole("button", { name: "Borrar conversación actual" }).click();
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
