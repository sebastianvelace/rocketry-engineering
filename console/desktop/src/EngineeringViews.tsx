import {
  ArrowRight,
  Check,
  CircleNotch,
  DownloadSimple,
  Play,
  Trash,
  Warning,
} from "@phosphor-icons/react";
import { motion } from "motion/react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { GatewayApiError, type GatewayApi } from "./api";
import type { Language } from "./i18n";
import { RunPlot } from "./RunPlot";
import type {
  EngineeringStatus,
  FlightConfig,
  RunComparison,
  RunRecord,
  RunSummary,
  WiringGuide,
} from "./types";

interface BaseProps {
  api: GatewayApi;
  language: Language;
  status: EngineeringStatus | null;
  onRunSaved: (runId: number) => Promise<RunRecord | null>;
}

const text = (language: Language, es: string, en: string) =>
  language === "es" ? es : en;

function SectionHead({
  eyebrow,
  title,
  description,
  aside,
}: {
  eyebrow: string;
  title: string;
  description: string;
  aside?: React.ReactNode;
}) {
  return (
    <header className="section-head">
      <div>
        <span>{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {aside}
    </header>
  );
}

function OperationButton({
  busy,
  disabled = false,
  children,
}: {
  busy: boolean;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <motion.button
      whileTap={{ scale: 0.985 }}
      className="action-button"
      disabled={busy || disabled}
    >
      {busy ? <CircleNotch className="spin" size={17} /> : <Play size={17} weight="fill" />}
      {children}
      {!busy && <ArrowRight size={16} />}
    </motion.button>
  );
}

function ErrorLine({ error }: { error: string }) {
  return error ? <div className="error-line"><Warning size={16} />{error}</div> : null;
}

interface BenchDiagnostics {
  bytes_received: number;
  lines_received: number;
  last_line: string;
  saw_block_start: boolean;
  rows_captured: number;
  elapsed_s: number;
}

function BenchDiagnosticsPanel({ diagnostics, language }: { diagnostics: BenchDiagnostics; language: Language }) {
  return (
    <div className="bench-diagnostics">
      <span>{text(language, "Qué se recibió realmente", "What was actually received")}</span>
      <dl>
        <div><dt>{text(language, "Bytes recibidos", "Bytes received")}</dt><dd>{diagnostics.bytes_received}</dd></div>
        <div><dt>{text(language, "Líneas recibidas", "Lines received")}</dt><dd>{diagnostics.lines_received}</dd></div>
        <div><dt>{text(language, "Bloque iniciado", "Block started")}</dt><dd>{diagnostics.saw_block_start ? text(language, "sí", "yes") : text(language, "no — nunca llegó '# BLOCK'", "no — '# BLOCK' never arrived")}</dd></div>
        <div><dt>{text(language, "Filas capturadas", "Rows captured")}</dt><dd>{diagnostics.rows_captured}</dd></div>
        <div><dt>{text(language, "Última línea vista", "Last line seen")}</dt><dd>{diagnostics.last_line || text(language, "(ninguna)", "(none)")}</dd></div>
      </dl>
    </div>
  );
}

function RunOutput({ run }: { run: RunRecord | null }) {
  if (!run) return null;
  return (
    <section className="operation-output">
      <header>
        <div><span>RUN #{run.id}</span><h2>{run.kind.replaceAll("_", " ")}</h2></div>
        <time>{new Date(run.created_at).toLocaleString()}</time>
      </header>
      <RunPlot run={run} />
      <div className="data-foot">
        <span>{run.row_count} samples</span>
        <span>{run.columns.length} columns</span>
        {Object.entries(run.meta).slice(0, 5).map(([key, value]) => (
          <span key={key}>{key}: {String(value)}</span>
        ))}
      </div>
    </section>
  );
}

export function BenchView({ api, language, status, onRunSaved }: BaseProps) {
  const [ports, setPorts] = useState(status?.ports || []);
  const [port, setPort] = useState(status?.ports[0] || "");
  const [baud, setBaud] = useState(115200);
  const [timeout, setTimeoutValue] = useState(15);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [diagnostics, setDiagnostics] = useState<BenchDiagnostics | null>(null);
  const [run, setRun] = useState<RunRecord | null>(null);

  useEffect(() => {
    setPorts(status?.ports || []);
    if (!port && status?.ports[0]) setPort(status.ports[0]);
  }, [port, status?.ports]);

  async function refreshPorts() {
    const next = await api.status();
    setPorts(next.ports);
    setPort((current) => next.ports.includes(current) ? current : next.ports[0] || "");
  }

  async function capture(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setDiagnostics(null);
    try {
      const result = await api.captureBench({
        port,
        baud,
        timeout_s: timeout,
        note,
      });
      setRun(await onRunSaved(result.run_id));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
      if (nextError instanceof GatewayApiError && nextError.code === "capture_timeout") {
        const reported = nextError.details.diagnostics as BenchDiagnostics | undefined;
        if (reported) setDiagnostics(reported);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="engineering-view">
      <SectionHead
        eyebrow="HARDWARE / SERIAL"
        title={text(language, "Banco de pruebas", "Bench")}
        description={text(
          language,
          "Captura un bloque completo de la ESP32. El tipo de medición se detecta automáticamente y la corrida queda guardada.",
          "Capture one complete ESP32 block. Measurement type is detected automatically and the run is saved.",
        )}
        aside={<button type="button" className={`live-badge ${ports.length ? "online" : ""}`} onClick={() => void refreshPorts()} title={text(language, "Actualizar puertos", "Refresh ports")}><i />{ports[0] || "ESP32 offline"}</button>}
      />
      <div className="workflow-line">
        <span className="active">01 {text(language, "Conectar", "Connect")}</span>
        <span>02 {text(language, "Capturar", "Capture")}</span>
        <span>03 {text(language, "Revisar", "Review")}</span>
      </div>
      <form className="instrument-form bench-form" onSubmit={capture}>
        <label>
          <span>{text(language, "Puerto serial", "Serial port")}</span>
          <select value={port} onChange={(event) => setPort(event.target.value)} disabled={!ports.length}>
            {ports.length
              ? ports.map((item) => <option key={item}>{item}</option>)
              : <option>{text(language, "Sin dispositivo", "No device")}</option>}
          </select>
        </label>
        <label>
          <span>{text(language, "Baudios", "Baud rate")}</span>
          <input type="number" min={1200} value={baud} onChange={(event) => setBaud(Number(event.target.value))} />
        </label>
        <label>
          <span>{text(language, "Espera máxima", "Timeout")} <small>s</small></span>
          <input type="number" min={2} max={120} value={timeout} onChange={(event) => setTimeoutValue(Number(event.target.value))} />
        </label>
        <label className="wide-field">
          <span>{text(language, "Nota de corrida", "Run note")}</span>
          <input value={note} onChange={(event) => setNote(event.target.value)} placeholder={text(language, "Filtro RC, primera corrida en frío", "RC filter, first cold run")} />
        </label>
        <OperationButton busy={busy} disabled={!port}>{text(language, "Capturar bloque", "Capture block")}</OperationButton>
      </form>
      <ErrorLine error={error} />
      {diagnostics && <BenchDiagnosticsPanel diagnostics={diagnostics} language={language} />}
      {!run && !busy && (
        <div className="waiting-line">
          <span># BLOCK</span>
          <p>{text(language, "Esperando una captura. Verifica primero el circuito en Cableado.", "Waiting for a capture. Verify the circuit in Wiring first.")}</p>
          <span># END</span>
        </div>
      )}
      <RunOutput run={run} />
    </div>
  );
}

export function WiringView({ api, language }: BaseProps) {
  const [guides, setGuides] = useState<WiringGuide[]>([]);
  const [selected, setSelected] = useState(0);
  const [phase, setPhase] = useState<"prepare" | "connect" | "verify">("prepare");
  const [checked, setChecked] = useState<Set<string>>(new Set());

  useEffect(() => {
    void api.wiring(language).then((items) => {
      setGuides(items);
      setSelected((current) => Math.min(current, Math.max(0, items.length - 1)));
    });
  }, [api, language]);

  const guide = guides[selected];
  if (!guide) return <div className="view-loading"><CircleNotch className="spin" /> Wiring</div>;

  const toggle = (key: string) => setChecked((current) => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  return (
    <div className="engineering-view wiring-view">
      <SectionHead
        eyebrow="BENCH / SETUP"
        title={text(language, "Cableado", "Wiring")}
        description={text(language, "Selecciona la medición, prepara las piezas y sigue la secuencia física antes de energizar.", "Select the measurement, prepare the parts and follow the physical sequence before applying power.")}
      />
      <nav className="choice-rail" aria-label="Circuit">
        {guides.map((item, index) => (
          <button key={item.circuit} className={selected === index ? "active" : ""} onClick={() => { setSelected(index); setPhase("prepare"); setChecked(new Set()); }}>
            <span>0{index + 1}</span><strong>{item.short}</strong><small>{item.use_for}</small>
          </button>
        ))}
      </nav>
      <div className="safety-line"><Warning size={18} weight="fill" /><strong>{guide.before}</strong><span>{guide.purpose}</span></div>
      <nav className="phase-tabs">
        {(["prepare", "connect", "verify"] as const).map((item, index) => (
          <button className={phase === item ? "active" : ""} onClick={() => setPhase(item)} key={item}>
            <span>0{index + 1}</span>{text(language, { prepare: "Preparar", connect: "Conectar", verify: "Verificar" }[item], { prepare: "Prepare", connect: "Connect", verify: "Verify" }[item])}
          </button>
        ))}
      </nav>
      {phase === "prepare" && (
        <section className="checklist-layout">
          <div>
            <h2>{text(language, "Componentes", "Parts")}</h2>
            {guide.parts.map((part, index) => (
              <button className={`check-row ${checked.has(`part-${index}`) ? "done" : ""}`} onClick={() => toggle(`part-${index}`)} key={part}>
                <i>{checked.has(`part-${index}`) && <Check size={13} />}</i><span>{part}</span>
              </button>
            ))}
          </div>
          <aside><span>{text(language, "MEDICIÓN", "MEASUREMENT")}</span><p>{guide.use_for}</p></aside>
        </section>
      )}
      {phase === "connect" && (
        <section className="wiring-connect">
          <div className="schematic">
            <span>{text(language, "TOPOLOGÍA DEL CIRCUITO", "CIRCUIT TOPOLOGY")}</span>
            <div dangerouslySetInnerHTML={{ __html: guide.svg }} />
          </div>
          <div className="pin-sequence">
            <span>{text(language, "SECUENCIA PIN A PIN", "PIN-BY-PIN SEQUENCE")}</span>
            {guide.pins.map((pin, index) => (
              <article key={`${pin.from}-${pin.to}`}>
                <b>{index + 1}</b><div><code>{pin.from} → {pin.to}</code><p>{pin.how}</p></div>
              </article>
            ))}
          </div>
        </section>
      )}
      {phase === "verify" && (
        <section className="verify-list">
          <h2>{text(language, "Inspección antes de energizar", "Pre-power inspection")}</h2>
          {guide.verify.map((item, index) => (
            <button className={`check-row ${checked.has(`verify-${index}`) ? "done" : ""}`} onClick={() => toggle(`verify-${index}`)} key={item}>
              <i>{checked.has(`verify-${index}`) && <Check size={13} />}</i><span>{item}</span>
            </button>
          ))}
        </section>
      )}
    </div>
  );
}

export function MotorView({ api, language, status, onRunSaved }: BaseProps) {
  const [form, setForm] = useState({
    coreMin: 12, coreMax: 14, lengthMin: 45, lengthMax: 55,
    lengthStep: 5, maximumStack: 320, targetKn: 280, note: "",
  });
  const [segments, setSegments] = useState([4, 5]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [run, setRun] = useState<RunRecord | null>(null);
  const combinations = (form.coreMax - form.coreMin + 1)
    * segments.length
    * (Math.floor((form.lengthMax - form.lengthMin) / form.lengthStep) + 1);
  const setNumber = (key: keyof typeof form, value: string) => setForm({ ...form, [key]: Number(value) });

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api.motorSweep({
        core_min_mm: form.coreMin,
        core_max_mm: form.coreMax,
        segment_counts: segments,
        segment_length_min_mm: form.lengthMin,
        segment_length_max_mm: form.lengthMax,
        segment_length_step_mm: form.lengthStep,
        maximum_stack_mm: form.maximumStack,
        target_peak_kn: form.targetKn,
        note: form.note,
      });
      setRun(await onRunSaved(result.run_id));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="engineering-view">
      <SectionHead
        eyebrow="OPENMOTOR / BATES"
        title={text(language, "Motor", "Motor")}
        description={text(language, "Explora un espacio acotado de geometrías y conserva únicamente configuraciones que superan los límites codificados.", "Explore a bounded geometry space and retain only configurations that pass the encoded gates.")}
        aside={<div className={`live-badge ${status?.openmotor_ready ? "online" : ""}`}><i />openMotor {status?.openmotor_ready ? "ready" : "offline"}</div>}
      />
      <form className="instrument-form motor-form" onSubmit={submit}>
        <fieldset>
          <legend>{text(language, "Diámetro de núcleo", "Core diameter")} <small>mm</small></legend>
          <label><span>MIN</span><input type="number" min={8} max={20} value={form.coreMin} onChange={(event) => setNumber("coreMin", event.target.value)} /></label>
          <label><span>MAX</span><input type="number" min={8} max={20} value={form.coreMax} onChange={(event) => setNumber("coreMax", event.target.value)} /></label>
        </fieldset>
        <fieldset>
          <legend>{text(language, "Longitud de segmento", "Segment length")} <small>mm</small></legend>
          <label><span>MIN</span><input type="number" min={20} max={70} value={form.lengthMin} onChange={(event) => setNumber("lengthMin", event.target.value)} /></label>
          <label><span>MAX</span><input type="number" min={20} max={70} value={form.lengthMax} onChange={(event) => setNumber("lengthMax", event.target.value)} /></label>
        </fieldset>
        <fieldset className="segment-field">
          <legend>{text(language, "Cantidad de segmentos", "Segment count")}</legend>
          <div>{[2, 3, 4, 5, 6].map((item) => <button type="button" className={segments.includes(item) ? "active" : ""} onClick={() => setSegments((current) => current.includes(item) ? current.filter((value) => value !== item) : [...current, item].sort())} key={item}>{item}</button>)}</div>
        </fieldset>
        <details>
          <summary>{text(language, "Restricciones avanzadas", "Advanced constraints")}</summary>
          <div>
            <label><span>{text(language, "Paso", "Step")} mm</span><input type="number" value={form.lengthStep} onChange={(event) => setNumber("lengthStep", event.target.value)} /></label>
            <label><span>{text(language, "Longitud máxima", "Max stack")} mm</span><input type="number" value={form.maximumStack} onChange={(event) => setNumber("maximumStack", event.target.value)} /></label>
            <label><span>Peak Kn</span><input type="number" value={form.targetKn} onChange={(event) => setNumber("targetKn", event.target.value)} /></label>
          </div>
        </details>
        <label className="wide-field"><span>{text(language, "Nota", "Note")}</span><input value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} /></label>
        <div className="estimate"><strong>{combinations}</strong><span>{text(language, "combinaciones", "combinations")}<small>≈ {Math.max(1, Math.round(combinations * 0.4))} s</small></span></div>
        <OperationButton busy={busy}>{text(language, "Ejecutar barrido", "Run sweep")}</OperationButton>
      </form>
      <ErrorLine error={error} />
      <RunOutput run={run} />
    </div>
  );
}

export function FlightView({ api, language, status, onRunSaved }: BaseProps) {
  const [config, setConfig] = useState<FlightConfig | null>(null);
  const [form, setForm] = useState({
    motorCurve: "E_sintubo.eng", architecture: "mindia", wind: 2,
    root: 55, tip: 25, height: 30, sweep: 30, thickness: 1.6, note: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [run, setRun] = useState<RunRecord | null>(null);
  useEffect(() => { void api.flightConfig().then((next) => {
    setConfig(next);
    setForm((current) => ({ ...current, motorCurve: next.motor_curves.includes(current.motorCurve) ? current.motorCurve : next.motor_curves[0] || "" }));
  }); }, [api]);
  const compatible = useMemo(() => config?.motor_curves.filter((name) => form.architecture !== "mindia" || name.includes("sintubo")) || [], [config, form.architecture]);
  useEffect(() => {
    if (!compatible.includes(form.motorCurve) && compatible[0]) setForm((current) => ({ ...current, motorCurve: compatible[0] }));
  }, [compatible, form.motorCurve]);
  const setNumber = (key: keyof typeof form, value: string) => setForm({ ...form, [key]: Number(value) });

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api.runFlight({
        motor_curve: form.motorCurve,
        architecture: form.architecture,
        wind_m_s: form.wind,
        note: form.note,
        fin: { root_mm: form.root, tip_mm: form.tip, height_mm: form.height, sweep_mm: form.sweep, thickness_mm: form.thickness },
      });
      setRun(await onRunSaved(result.run_id));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="engineering-view">
      <SectionHead
        eyebrow="OPENROCKET / 6DOF"
        title={text(language, "Vuelo", "Flight")}
        description={text(language, "Combina una curva de motor, la arquitectura real y la geometría de aletas para evaluar la trayectoria completa.", "Combine a motor curve, real architecture and fin geometry to evaluate the complete trajectory.")}
        aside={<div className={`live-badge ${status?.openrocket_ready ? "online" : ""}`}><i />OpenRocket {status?.openrocket_ready ? "ready" : "offline"}</div>}
      />
      <form className="instrument-form flight-form" onSubmit={submit}>
        <section>
          <span className="form-section-label">01 / {text(language, "VEHÍCULO", "VEHICLE")}</span>
          <label><span>{text(language, "Arquitectura", "Architecture")}</span><select value={form.architecture} onChange={(event) => setForm({ ...form, architecture: event.target.value })}><option value="mindia">{text(language, "Diámetro mínimo", "Minimum diameter")}</option><option value="separate">{text(language, "Fuselaje separado", "Separate airframe")}</option></select></label>
          <label><span>{text(language, "Curva de motor", "Motor curve")}</span><select value={form.motorCurve} onChange={(event) => setForm({ ...form, motorCurve: event.target.value })}>{compatible.map((item) => <option key={item}>{item}</option>)}</select></label>
          <label><span>{text(language, "Viento", "Wind")} <small>m/s</small></span><input type="number" min={0} max={15} step={0.5} value={form.wind} onChange={(event) => setNumber("wind", event.target.value)} /></label>
        </section>
        <section>
          <span className="form-section-label">02 / {text(language, "ALETAS TRAPEZOIDALES", "TRAPEZOIDAL FINS")}</span>
          {([["root", "Root"], ["tip", "Tip"], ["height", "Span"], ["sweep", "Sweep"], ["thickness", "Thickness"]] as [keyof typeof form, string][]).map(([key, label]) => (
            <label key={key}><span>{label} <small>mm</small></span><input type="number" min={key === "sweep" ? 0 : 0.1} step={0.1} value={String(form[key])} onChange={(event) => setNumber(key, event.target.value)} /></label>
          ))}
        </section>
        <label className="wide-field"><span>{text(language, "Nota", "Note")}</span><input value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} /></label>
        <OperationButton busy={busy}>{text(language, "Simular vuelo", "Simulate flight")}</OperationButton>
      </form>
      <ErrorLine error={error} />
      <RunOutput run={run} />
    </div>
  );
}

function ComparisonPlot({ comparison }: { comparison: RunComparison }) {
  const all = comparison.series.flatMap((series) => series.points);
  if (!all.length) return null;
  const minX = Math.min(...all.map((point) => point.x));
  const maxX = Math.max(...all.map((point) => point.x));
  const minY = Math.min(...all.map((point) => point.y));
  const maxY = Math.max(...all.map((point) => point.y));
  const x = (value: number) => 30 + ((value - minX) / Math.max(1e-9, maxX - minX)) * 740;
  const y = (value: number) => 250 - ((value - minY) / Math.max(1e-9, maxY - minY)) * 220;
  const colors = ["#ef4444", "#9fb1c7", "#f0b15d", "#7fc99a", "#b99bda", "#d9dce2"];
  return (
    <div className="comparison-plot">
      <svg viewBox="0 0 800 280" role="img">
        <path className="axis" d="M30 20V250H780" />
        {comparison.series.map((series, index) => (
          <polyline key={series.run_id} fill="none" stroke={colors[index]} strokeWidth="2" points={series.points.map((point) => `${x(point.x)},${y(point.y)}`).join(" ")} />
        ))}
      </svg>
      <div>{comparison.series.map((series, index) => <span key={series.run_id}><i style={{ background: colors[index] }} />#{series.run_id} {series.note}</span>)}</div>
    </div>
  );
}

export function HistoryView({
  api,
  language,
  runs,
  selectedRun,
  setSelectedRun,
  refresh,
}: BaseProps & {
  runs: RunSummary[];
  selectedRun: RunRecord | null;
  setSelectedRun: (run: RunRecord | null) => void;
  refresh: () => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<number[]>([]);
  const [comparison, setComparison] = useState<RunComparison | null>(null);
  const [error, setError] = useState("");
  const filtered = runs.filter((run) => `${run.kind} ${run.note}`.toLowerCase().includes(query.toLowerCase()));

  async function compare() {
    setError("");
    try { setComparison(await api.compareRuns(picked)); }
    catch (nextError) { setError(nextError instanceof Error ? nextError.message : String(nextError)); }
  }

  return (
    <div className="engineering-view history-view">
      <SectionHead eyebrow="TRACE / ARCHIVE" title={text(language, "Historial", "History")} description={text(language, "Reabre, superpone y exporta la evidencia producida por el banco y las simulaciones.", "Reopen, overlay and export evidence produced by the bench and simulations.")} />
      <div className="history-toolbar">
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={text(language, "Buscar tipo o nota", "Search type or note")} />
        <span>{filtered.length} / {runs.length}</span>
        <button disabled={picked.length < 2} onClick={() => void compare()}>{text(language, "Comparar selección", "Compare selection")}</button>
      </div>
      <ErrorLine error={error} />
      <div className="history-layout">
        <div className="run-index">
          {filtered.map((run) => (
            <article className={selectedRun?.id === run.id ? "active" : ""} key={run.id}>
              <button className="compare-check" onClick={() => setPicked((current) => current.includes(run.id) ? current.filter((id) => id !== run.id) : current.length < 6 ? [...current, run.id] : current)}><i>{picked.includes(run.id) && <Check size={12} />}</i></button>
              <button className="run-open" onClick={() => void api.run(run.id).then(setSelectedRun)}>
                <span>#{run.id}</span><strong>{run.kind.replaceAll("_", " ")}</strong><small>{run.note || new Date(run.created_at).toLocaleString(language)}</small>
              </button>
            </article>
          ))}
        </div>
        <div className="history-detail">
          {comparison ? (
            <section>
              <header className="detail-title"><div><span>OVERLAY</span><h2>{comparison.kind}</h2></div><button onClick={() => setComparison(null)}>×</button></header>
              <ComparisonPlot comparison={comparison} />
            </section>
          ) : selectedRun ? (
            <>
              <header className="detail-title">
                <div><span>RUN #{selectedRun.id}</span><h2>{selectedRun.kind.replaceAll("_", " ")}</h2></div>
                <div>
                  <button title="CSV" onClick={() => void api.exportRun(selectedRun.id).then((artifact) => api.openArtifact(artifact))}><DownloadSimple size={17} /></button>
                  <button title="Delete" onClick={() => { if (window.confirm(text(language, "¿Eliminar esta corrida?", "Delete this run?"))) void api.deleteRun(selectedRun.id).then(async () => { setSelectedRun(null); await refresh(); }); }}><Trash size={17} /></button>
                </div>
              </header>
              <RunPlot run={selectedRun} />
              <div className="data-table"><table><thead><tr>{selectedRun.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{selectedRun.rows.slice(0, 12).map((row, index) => <tr key={index}>{row.map((value, column) => <td key={column}>{String(value)}</td>)}</tr>)}</tbody></table></div>
            </>
          ) : <div className="waiting-line"><p>{text(language, "Selecciona una corrida para inspeccionarla.", "Select a run to inspect it.")}</p></div>}
        </div>
      </div>
    </div>
  );
}
