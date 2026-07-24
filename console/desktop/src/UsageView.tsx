import { ArrowClockwise, CircleNotch, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import type { GatewayApi } from "./api";
import type { Language } from "./i18n";
import type { ProviderUsage, UsageSnapshot, UsageWindow } from "./types";

const copy = (language: Language, es: string, en: string) =>
  language === "es" ? es : en;

const formatTokens = (value: number | null | undefined) => {
  if (!value) return "0";
  return new Intl.NumberFormat(undefined, {
    notation: value >= 100_000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value);
};

function resetLabel(window: UsageWindow, language: Language) {
  if (window.resets_at_label) return window.resets_at_label;
  if (window.resetsAt) {
    return new Date(window.resetsAt * 1000).toLocaleString(language, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  }
  return copy(language, "Sin fecha reportada", "No reset reported");
}

function UsageBar({
  label,
  window,
  language,
}: {
  label: string;
  window: UsageWindow;
  language: Language;
}) {
  const used = Math.max(0, Math.min(100, window.used_percent ?? window.usedPercent ?? 0));
  return (
    <div className="usage-window">
      <div><strong>{label}</strong><span>{used}%</span></div>
      <div className="usage-track"><i style={{ width: `${used}%` }} /></div>
      <small>{copy(language, "Reinicia", "Resets")} {resetLabel(window, language)}</small>
    </div>
  );
}

function ProviderPanel({
  provider,
  usage,
  snapshot,
  language,
}: {
  provider: "claude" | "codex";
  usage: ProviderUsage;
  snapshot: UsageSnapshot;
  language: Language;
}) {
  const local = snapshot.local[provider];
  if (!usage.available) {
    return (
      <section className="usage-provider">
        <header><span>{provider.toUpperCase()}</span><h2>{provider === "claude" ? "Claude Code" : "Codex"}</h2></header>
        <div className="usage-unavailable"><WarningCircle /><p>{usage.error || copy(language, "Uso no disponible.", "Usage unavailable.")}</p></div>
      </section>
    );
  }

  const codexLimits = usage.rate_limits?.rateLimits;
  const windows = provider === "claude"
    ? usage.windows || []
    : [codexLimits?.primary, codexLimits?.secondary].filter(Boolean) as UsageWindow[];
  const summary = usage.token_usage?.summary;
  const daily = usage.token_usage?.dailyUsageBuckets || [];
  const peak = Math.max(1, ...daily.map((item) => item.tokens));

  return (
    <section className="usage-provider">
      <header>
        <div><span>{provider.toUpperCase()} / LIVE</span><h2>{provider === "claude" ? "Claude Code" : "Codex"}</h2></div>
        <small>{usage.source}</small>
      </header>

      <div className="usage-windows">
        {windows.map((window, index) => (
          <UsageBar
            key={window.id || index}
            label={provider === "claude"
              ? window.id === "week"
                ? copy(language, "Semana", "Week")
                : copy(language, "Sesión", "Session")
              : index === 0
                ? copy(language, "Ventana principal", "Primary window")
                : copy(language, "Ventana secundaria", "Secondary window")}
            window={window}
            language={language}
          />
        ))}
      </div>

      {provider === "claude" ? (
        <div className="usage-facts">
          <div><span>{copy(language, "Solicitudes · 24 h", "Requests · 24h")}</span><strong>{usage.activity?.day?.requests ?? "—"}</strong></div>
          <div><span>{copy(language, "Sesiones · 24 h", "Sessions · 24h")}</span><strong>{usage.activity?.day?.sessions ?? "—"}</strong></div>
          <div><span>{copy(language, "Solicitudes · 7 d", "Requests · 7d")}</span><strong>{usage.activity?.week?.requests ?? "—"}</strong></div>
          <div><span>{copy(language, "Tokens locales", "Local tokens")}</span><strong>{formatTokens((local.input_tokens || 0) + (local.output_tokens || 0))}</strong></div>
        </div>
      ) : (
        <>
          <div className="usage-facts">
            <div><span>{copy(language, "Plan reportado", "Reported plan")}</span><strong>{codexLimits?.planType || "—"}</strong></div>
            <div><span>{copy(language, "Tokens históricos", "Lifetime tokens")}</span><strong>{formatTokens(summary?.lifetimeTokens)}</strong></div>
            <div><span>{copy(language, "Pico diario", "Peak daily")}</span><strong>{formatTokens(summary?.peakDailyTokens)}</strong></div>
            <div><span>{copy(language, "Tokens locales", "Local tokens")}</span><strong>{formatTokens(local.total_tokens)}</strong></div>
          </div>
          {daily.length > 0 && (
            <div className="usage-daily" aria-label={copy(language, "Uso diario de Codex", "Daily Codex usage")}>
              {daily.map((item) => (
                <i
                  key={item.startDate}
                  title={`${item.startDate}: ${item.tokens.toLocaleString()} tokens`}
                  style={{ height: `${Math.max(4, (item.tokens / peak) * 100)}%` }}
                />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}

export function UsageView({ api, language }: { api: GatewayApi; language: Language }) {
  const [snapshot, setSnapshot] = useState<UsageSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load(force = false) {
    setBusy(true);
    setError("");
    try {
      setSnapshot(await api.usage(force));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { void load(); }, [api]);

  return (
    <div className="engineering-view usage-view">
      <header className="section-head usage-head">
        <div>
          <span>{copy(language, "PROVEEDORES / USO", "PROVIDERS / USAGE")}</span>
          <h1>{copy(language, "Uso", "Usage")}</h1>
          <p>{copy(language, "Límites reales del proveedor y consumo observado por esta estación.", "Real provider limits and usage observed by this workstation.")}</p>
        </div>
        <button className="live-badge" onClick={() => void load(true)} disabled={busy}>
          {busy ? <CircleNotch className="spin" /> : <ArrowClockwise />}
          {copy(language, "Actualizar", "Refresh")}
        </button>
      </header>

      {error && <div className="error-line"><WarningCircle />{error}</div>}
      {!snapshot ? (
        <div className="view-loading"><CircleNotch className="spin" /> {copy(language, "Uso", "Usage")}</div>
      ) : (
        <>
          <div className="usage-grid">
            <ProviderPanel provider="claude" usage={snapshot.providers.claude} snapshot={snapshot} language={language} />
            <ProviderPanel provider="codex" usage={snapshot.providers.codex} snapshot={snapshot} language={language} />
          </div>
          <footer className="usage-foot">
            <span>{copy(language, "Actualizado", "Updated")} {new Date(snapshot.refreshed_at).toLocaleString(language)}</span>
            <p>{copy(
              language,
              "Claude obtiene sus porcentajes desde /usage y Codex desde account/rateLimits/read. La actividad de Claude es una aproximación local del CLI; los tokens locales sólo incluyen sesiones vistas por esta aplicación. Ninguno sustituye la facturación del proveedor.",
              "Claude percentages come from /usage and Codex comes from account/rateLimits/read. Claude activity is the CLI's local approximation; local tokens include only sessions observed by this app. Neither replaces provider billing.",
            )}</p>
          </footer>
        </>
      )}
    </div>
  );
}
