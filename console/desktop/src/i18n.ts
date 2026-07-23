export type Language = "en" | "es";

const copy = {
  en: {
    sessions: "Sessions",
    newTask: "New task",
    noSessions: "No sessions yet",
    chooseProvider: "Choose the agent for this task",
    codexDescription: "Company Codex subscription",
    claudeDescription: "Personal Claude Code subscription",
    taskTitle: "Task name",
    create: "Create",
    cancel: "Cancel",
    conversation: "Conversation",
    results: "Results",
    activity: "Activity",
    runs: "Runs",
    artifacts: "Artifacts",
    noConversation: "Describe a test, simulation, or code problem to begin.",
    noRuns: "Saved measurements and simulations will appear here.",
    noActivity: "Agent tools and command output will appear as they run.",
    placeholder: "Ask the agent to measure, simulate, test, or explain...",
    send: "Send",
    stop: "Stop",
    approve: "Allow once",
    approveSession: "Allow for session",
    deny: "Deny",
    needsApproval: "Approval required",
    connected: "ESP32 connected",
    disconnected: "ESP32 disconnected",
    savedRuns: "saved runs",
    agentWorking: "Agent is working",
    agentReady: "Ready",
    reconnecting: "Reconnecting",
    gatewayError: "Could not connect to the local gateway.",
    retry: "Retry",
    selectSession: "Select or create a session",
    columns: "Columns",
    samples: "samples",
    download: "Open artifact",
    provider: "Provider",
    close: "Close",
  },
  es: {
    sessions: "Sesiones",
    newTask: "Nueva tarea",
    noSessions: "Aún no hay sesiones",
    chooseProvider: "Elige el agente para esta tarea",
    codexDescription: "Suscripción empresarial de Codex",
    claudeDescription: "Suscripción personal de Claude Code",
    taskTitle: "Nombre de la tarea",
    create: "Crear",
    cancel: "Cancelar",
    conversation: "Conversación",
    results: "Resultados",
    activity: "Actividad",
    runs: "Corridas",
    artifacts: "Artefactos",
    noConversation: "Describe una prueba, simulación o problema de código para comenzar.",
    noRuns: "Las mediciones y simulaciones guardadas aparecerán aquí.",
    noActivity: "Las herramientas y comandos del agente aparecerán mientras se ejecutan.",
    placeholder: "Pídele al agente medir, simular, probar o explicar...",
    send: "Enviar",
    stop: "Detener",
    approve: "Permitir una vez",
    approveSession: "Permitir en la sesión",
    deny: "Denegar",
    needsApproval: "Se requiere aprobación",
    connected: "ESP32 conectada",
    disconnected: "ESP32 desconectada",
    savedRuns: "corridas guardadas",
    agentWorking: "El agente está trabajando",
    agentReady: "Listo",
    reconnecting: "Reconectando",
    gatewayError: "No fue posible conectar con el gateway local.",
    retry: "Reintentar",
    selectSession: "Selecciona o crea una sesión",
    columns: "Columnas",
    samples: "muestras",
    download: "Abrir artefacto",
    provider: "Proveedor",
    close: "Cerrar",
  },
} as const;

export type CopyKey = keyof typeof copy.en;

export function translate(language: Language, key: CopyKey): string {
  return copy[language][key];
}

const statusCopy: Record<Language, Record<string, string>> = {
  en: {
    created: "created",
    ready: "ready",
    running: "running",
    waiting_approval: "waiting for approval",
    interrupting: "stopping",
    interrupted: "interrupted",
    completed: "completed",
    failed: "failed",
  },
  es: {
    created: "creada",
    ready: "lista",
    running: "ejecutando",
    waiting_approval: "esperando aprobación",
    interrupting: "deteniendo",
    interrupted: "interrumpida",
    completed: "completada",
    failed: "fallida",
  },
};

const eventCopy: Record<Language, Record<string, string>> = {
  en: {
    tool_started: "tool started",
    tool_progress: "tool progress",
    tool_completed: "tool completed",
    command_output: "command output",
    reasoning: "reasoning",
    error: "error",
  },
  es: {
    tool_started: "herramienta iniciada",
    tool_progress: "progreso",
    tool_completed: "herramienta completada",
    command_output: "salida del comando",
    reasoning: "razonamiento",
    error: "error",
  },
};

export function statusLabel(language: Language, status: string): string {
  return statusCopy[language][status] || status;
}

export function eventLabel(language: Language, event: string): string {
  return eventCopy[language][event] || event.replaceAll("_", " ");
}
