"""Shared presentation layer for the Rocketry Console.

The app remains a local Streamlit tool, but every page uses the same visual
tokens, navigation, status language, Plotly theme, and empty/error patterns.
"""
from __future__ import annotations

import base64
from html import escape
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

ACCENT = "#ef4444"
PLOT_COLORS = ["#ef4444", "#5bc0eb", "#9ee493", "#ffd166", "#c7a0ff", "#f28fad"]

_GLOBAL_CSS = """
<style>
:root {
  --rc-bg: #080b10;
  --rc-panel: #10151d;
  --rc-panel-2: #151c26;
  --rc-line: #29313d;
  --rc-line-strong: #3a4656;
  --rc-text: #eef2f7;
  --rc-muted: #8d99a8;
  --rc-faint: #626d7b;
  --rc-accent: #ef4444;
  --rc-accent-soft: rgba(239, 68, 68, 0.12);
  --rc-ok: #68d391;
  --rc-warn: #f6c85f;
  --rc-danger: #ff6b6b;
  --rc-radius: 9px;
}

html { scroll-behavior: smooth; }
body { color-scheme: dark; }

[data-testid="stAppViewContainer"] {
  background: #080b10;
}

[data-testid="stMainBlockContainer"] {
  max-width: 1280px;
  padding-top: 2rem;
  padding-bottom: 5rem;
}

[data-testid="stSidebar"] {
  background: #0b0f15;
}

[data-testid="stSidebarContent"] {
  padding: 1.35rem 1rem 2rem;
}

[data-testid="stLogo"] {
  margin: 0 0 .65rem;
  max-width: 210px;
}

[data-testid="stSidebar"] [data-testid="stSegmentedControl"] {
  margin: .15rem 0 .85rem;
}
[data-testid="stSidebar"] [data-testid="stSegmentedControl"] [role="radiogroup"] {
  width: fit-content;
  min-height: 1.9rem;
  padding: 2px;
  border: 1px solid var(--rc-line);
  border-radius: 5px;
  background: transparent;
}
[data-testid="stSidebar"] [data-testid="stSegmentedControl"] label {
  min-height: 1.55rem;
  padding: 0 .6rem;
  border-radius: 3px;
  font: 650 .69rem/1 "IBM Plex Mono", "Cascadia Code", monospace;
}

h1, h2, h3 {
  letter-spacing: -0.025em;
}

h1 {
  font-stretch: condensed;
}

p, label, [data-testid="stCaptionContainer"] {
  line-height: 1.55;
}

a:focus-visible, button:focus-visible, input:focus-visible,
[role="button"]:focus-visible, [role="tab"]:focus-visible {
  outline: 2px solid var(--rc-accent) !important;
  outline-offset: 3px;
}

[data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button,
[data-testid="stDownloadButton"] button, [data-testid="stPageLink"] a {
  min-height: 2.65rem;
  font-weight: 650;
  letter-spacing: .005em;
  background-image: linear-gradient(90deg, var(--rc-accent-soft), var(--rc-accent-soft));
  background-position: left center;
  background-repeat: no-repeat;
  background-size: 0 100%;
  transition: transform 160ms ease, border-color 160ms ease, background-size 240ms cubic-bezier(.2,.8,.2,1);
}

[data-testid="stButton"] button:hover, [data-testid="stFormSubmitButton"] button:hover,
[data-testid="stDownloadButton"] button:hover, [data-testid="stPageLink"] a:hover {
  border-color: var(--rc-accent);
  transform: translateY(-1px);
  background-size: 100% 100%;
}

[data-testid="stButton"] button:active, [data-testid="stFormSubmitButton"] button:active,
[data-testid="stDownloadButton"] button:active, [data-testid="stPageLink"] a:active {
  transform: translateY(1px) scale(.99);
}

[data-testid="stMetric"] {
  background: transparent;
  border: 0;
  border-top: 1px solid var(--rc-line-strong);
  border-radius: 0;
  padding: .85rem 0 1rem;
  min-height: 92px;
}

[data-testid="stMetricLabel"] {
  color: var(--rc-muted);
  font-family: "IBM Plex Mono", "Cascadia Code", monospace;
  text-transform: uppercase;
  letter-spacing: .09em;
  font-size: .72rem;
}

[data-testid="stMetricValue"] {
  letter-spacing: -.035em;
}

[data-testid="stTabs"] [data-baseweb="tab-list"] {
  gap: .25rem;
  border-bottom: 1px solid var(--rc-line);
}

[data-testid="stTabs"] [data-baseweb="tab"] {
  min-width: 7rem;
  padding-inline: 1rem;
}

[data-testid="stForm"] {
  border: 0;
  border-top: 1px solid var(--rc-line);
  border-radius: 0;
  background: transparent;
  padding: 1rem 0 0;
}

[data-testid="stExpander"] {
  border-color: var(--rc-line);
  background: transparent;
}

[data-testid="stDataFrame"], [data-testid="stTable"] {
  border: 1px solid var(--rc-line);
  border-radius: var(--rc-radius);
  overflow: hidden;
}

[data-testid="stAlert"] {
  border-radius: var(--rc-radius);
  border-left-width: 3px;
}

[data-testid="stPlotlyChart"] {
  border: 1px solid var(--rc-line);
  border-radius: var(--rc-radius);
  overflow: hidden;
  background: rgba(11,15,21,.8);
}

.rc-page-head {
  margin: .2rem 0 1.65rem;
  padding: 0 0 1.2rem;
  border-bottom: 1px solid var(--rc-line);
  animation: rc-enter 420ms cubic-bezier(.2,.8,.2,1) both;
}

.rc-page-kicker {
  color: var(--rc-accent);
  font: 650 .71rem/1.2 "IBM Plex Mono", "Cascadia Code", monospace;
  letter-spacing: .12em;
  text-transform: uppercase;
  margin-bottom: .65rem;
}

.rc-page-head h1 {
  color: var(--rc-text);
  font-size: clamp(2.2rem, 4.6vw, 4.7rem);
  line-height: .95;
  margin: 0;
  max-width: 900px;
}

.rc-page-head p {
  color: var(--rc-muted);
  font-size: 1.02rem;
  max-width: 680px;
  margin: .85rem 0 0;
}

.rc-hero {
  position: relative;
  min-height: 315px;
  padding: clamp(1.2rem, 3vw, 2.7rem) 0;
  border: 0;
  border-top: 1px solid var(--rc-line-strong);
  border-bottom: 1px solid var(--rc-line);
  background: transparent;
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(220px, .45fr);
  align-items: end;
  gap: 3rem;
  animation: rc-enter 480ms cubic-bezier(.2,.8,.2,1) both;
}

.rc-hero-copy { position: relative; z-index: 2; }
.rc-hero h1 {
  margin: .5rem 0 .9rem;
  max-width: 760px;
  font-size: clamp(3rem, 5.6vw, 5.7rem);
  line-height: .9;
  letter-spacing: -.06em;
}
.rc-hero p {
  max-width: 560px;
  color: #a8b1be;
  font-size: 1.02rem;
}

.rc-mission-line {
  align-self: stretch;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: .7rem;
  border-left: 1px solid var(--rc-line);
  padding-left: 1.25rem;
}
.rc-mission-line strong {
  font: 600 .76rem/1.4 "IBM Plex Mono", "Cascadia Code", monospace;
  color: var(--rc-text);
}
.rc-mission-line span {
  color: var(--rc-muted);
  font-size: .8rem;
}
.rc-signal {
  height: 2px;
  background: var(--rc-line);
  overflow: hidden;
}
.rc-signal::after {
  content: "";
  display: block;
  width: 28%;
  height: 100%;
  background: var(--rc-accent);
  animation: rc-signal 2.8s ease-in-out infinite;
}

.rc-status {
  display: inline-flex;
  align-items: center;
  gap: .55rem;
  color: var(--rc-muted);
  font: 600 .75rem/1.2 "IBM Plex Mono", "Cascadia Code", monospace;
}
.rc-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--rc-muted);
}
.rc-status[data-state="ok"] .rc-status-dot { background: var(--rc-ok); box-shadow: 0 0 0 4px rgba(104,211,145,.1); }
.rc-status[data-state="warn"] .rc-status-dot { background: var(--rc-warn); }
.rc-status[data-state="off"] .rc-status-dot { background: var(--rc-danger); }

.rc-section-title {
  margin: 2.5rem 0 1rem;
  font-size: clamp(1.4rem, 2vw, 2rem);
  letter-spacing: -.025em;
}

.rc-flow {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1.5rem;
  background: transparent;
  border: 0;
  border-top: 1px solid var(--rc-line);
  margin: .5rem 0 1.5rem;
}
.rc-flow-step { background: transparent; padding: 1rem 0; min-height: 110px; }
.rc-flow-step b { display: block; color: var(--rc-text); margin: .45rem 0 .3rem; }
.rc-flow-step span { color: var(--rc-muted); font-size: .86rem; }
.rc-flow-index { color: var(--rc-accent) !important; font: 650 .68rem/1 "IBM Plex Mono", monospace; }

.rc-action {
  min-height: 132px;
  padding: 1rem 0 .8rem;
  border-top: 1px solid var(--rc-line-strong);
}
.rc-action small {
  color: var(--rc-accent);
  font: 650 .68rem/1.2 "IBM Plex Mono", monospace;
}
.rc-action h3 { margin: .55rem 0 .35rem; font-size: 1.05rem; }
.rc-action p { margin: 0; color: var(--rc-muted); font-size: .87rem; }

.rc-step-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(240px, 1fr));
  gap: 1.5rem;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  padding: .1rem 0 .65rem;
  scrollbar-color: var(--rc-accent) var(--rc-panel);
}
.rc-step-card {
  scroll-snap-align: start;
  display: grid;
  grid-template-columns: 2rem minmax(0, 1fr);
  column-gap: .25rem;
  align-content: start;
  border: 0;
  border-top: 1px solid var(--rc-line-strong);
  border-radius: 0;
  background: transparent;
  padding: .9rem 0;
  min-height: 120px;
}
.rc-step-card .rc-flow-index { grid-row: 1 / span 2; padding-top: .2rem; }
.rc-step-card strong { display: block; margin: 0 0 .4rem; }
.rc-step-card p { grid-column: 2; margin: 0; color: var(--rc-muted); font-size: .88rem; }

.rc-pin {
  display: grid;
  grid-template-columns: 2rem minmax(0, 1fr);
  gap: .75rem;
  align-items: start;
  padding: .8rem 0;
  border-bottom: 1px solid var(--rc-line);
}
.rc-pin:last-child { border-bottom: 0; }
.rc-pin-num {
  display: grid;
  place-items: center;
  width: 1.8rem; height: 1.8rem;
  border-radius: 50%;
  background: var(--rc-accent-soft);
  color: var(--rc-accent);
  font: 700 .75rem/1 "IBM Plex Mono", monospace;
}
.rc-pin code { color: var(--rc-text); font-size: .78rem; }
.rc-pin p { color: var(--rc-muted); font-size: .82rem; margin: .25rem 0 0; }

.rc-schematic {
  min-height: 240px;
  display: grid;
  place-items: center;
  padding: 1.4rem 0;
  border: 0;
  border-top: 1px solid var(--rc-line);
  border-bottom: 1px solid var(--rc-line);
  background: transparent;
  overflow-x: auto;
}
.rc-schematic img { width: min(100%, 760px); min-height: 120px; object-fit: contain; }

.rc-safety {
  border-left: 3px solid var(--rc-warn);
  background: rgba(246,200,95,.07);
  padding: .9rem 1rem;
  color: #d9d2bd;
  border-radius: 0 var(--rc-radius) var(--rc-radius) 0;
  margin: .75rem 0 1.2rem;
}
.rc-safety strong { color: var(--rc-warn); }

.rc-mono {
  font-family: "IBM Plex Mono", "Cascadia Code", monospace;
  font-size: .78rem;
  color: var(--rc-muted);
}

.rc-sidebar-meta {
  border-top: 1px solid var(--rc-line);
  margin-top: 1rem;
  padding-top: .9rem;
}
.rc-brand { width: 215px; margin: .15rem 0 .85rem; }
.rc-brand svg, .rc-brand img { display: block; width: 100%; height: auto; }
.rc-sidebar-meta p { margin: .25rem 0; color: var(--rc-muted); font-size: .76rem; }

.rc-events { border-top: 1px solid var(--rc-line); }
.rc-event {
  display: grid;
  grid-template-columns: 5rem minmax(150px, .35fr) minmax(0, 1fr);
  gap: 1rem;
  padding: .75rem 0;
  border-bottom: 1px solid var(--rc-line);
}
.rc-event time {
  color: var(--rc-faint);
  font: 600 .7rem/1.5 "IBM Plex Mono", monospace;
}
.rc-event strong {
  color: var(--rc-text);
  font: 600 .75rem/1.5 "IBM Plex Mono", monospace;
}
.rc-event p { margin: 0; color: var(--rc-muted); font-size: .82rem; overflow-wrap: anywhere; }

/* Native motion keeps the console dependency-free and survives Streamlit reruns. */
@keyframes rc-enter {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes rc-signal {
  0%, 100% { transform: translateX(-110%); opacity: .25; }
  50% { transform: translateX(360%); opacity: 1; }
}

@media (max-width: 900px) {
  [data-testid="stMainBlockContainer"] { padding-inline: 1rem; padding-top: 1.2rem; }
  .rc-hero { grid-template-columns: 1fr; min-height: auto; }
  .rc-mission-line { border-left: 0; border-top: 1px solid var(--rc-line); padding: 1rem 0 0; }
  .rc-flow { grid-template-columns: 1fr 1fr; }
  .rc-event { grid-template-columns: 4rem 1fr; }
  .rc-event p { grid-column: 2; }
  .rc-page-head h1 { font-size: clamp(2.2rem, 12vw, 4rem); }
}

@media (max-width: 560px) {
  .rc-hero { padding: 1.25rem; }
  .rc-flow { grid-template-columns: 1fr; }
  .rc-step-strip { grid-template-columns: repeat(3, 84vw); }
}

@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after {
    animation-duration: .001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .001ms !important;
  }
}
</style>
"""


NAV_ITEMS = (
    ("Home", "Inicio", "app.py", ":material/home:"),
    ("Bench", "Banco de pruebas", "pages/1_Bench.py", ":material/monitor_heart:"),
    ("Wiring", "Cableado", "pages/2_Wiring.py", ":material/electrical_services:"),
    ("Motor", "Motor", "pages/3_Motor.py", ":material/local_fire_department:"),
    ("Flight", "Vuelo", "pages/4_Flight.py", ":material/rocket_launch:"),
    ("History", "Historial", "pages/5_History.py", ":material/history:"),
    ("Agent", "Agente", "pages/6_Agent.py", ":material/terminal:"),
)


def is_spanish() -> bool:
    return st.session_state.get("rc_language", "English") == "Español"


def tr(english: str, spanish: str) -> str:
    """Return copy in the language selected for the current session."""
    return spanish if is_spanish() else english


def _persist_language(widget_key: str) -> None:
    """Copy the page-scoped widget value to a key Streamlit will not clean up."""
    st.session_state["rc_language"] = (
        "Español" if st.session_state.get(widget_key) == "ES" else "English"
    )


_PLOT_TRANSLATIONS = {
    "FFT -- real signal": "FFT: señal real",
    "ADC sees": "el ADC detecta",
    "Sampling intervals -- method:": "Intervalos de muestreo: método:",
    "jitter (std)": "jitter (desv. est.)",
    "Capacitor charging curve -> R from RC time constant": "Carga del capacitor: R a partir de la constante de tiempo RC",
    "ADC transfer curve": "Curva de transferencia del ADC",
    "RC filter frequency response": "Respuesta en frecuencia del filtro RC",
    "Thrust replay (relative units) -- impulse proportional to": "Replay de empuje (unidades relativas): impulso proporcional a",
    "time (ms)": "tiempo (ms)",
    "voltage (V)": "voltaje (V)",
    "frequency (Hz)": "frecuencia (Hz)",
    "magnitude": "magnitud",
    "sample number": "número de muestra",
    "interval to previous sample (us)": "intervalo desde la muestra anterior (us)",
    "ADC counts": "cuentas del ADC",
    "DAC input (mV)": "entrada DAC (mV)",
    "ADC reads (mV)": "lectura ADC (mV)",
    "gain (dB)": "ganancia (dB)",
    "thrust (arb. units)": "empuje (unidades arbitrarias)",
    "peak seen:": "pico detectado:",
    "ideal": "ideal",
    "raw ADC (naive)": "ADC crudo (simple)",
    "factory calibrated": "calibrado de fábrica",
}

_STAT_TRANSLATIONS = {
    "F_signal (Hz)": "F_señal (Hz)",
    "F_sample (Hz)": "F_muestreo (Hz)",
    "Nyquist (Hz)": "Nyquist (Hz)",
    "Aliasing?": "¿Aliasing?",
    "Real signal (Hz)": "Señal real (Hz)",
    "ADC sees (Hz)": "Lectura del ADC (Hz)",
    "Method": "Método",
    "Target (us)": "Objetivo (us)",
    "Jitter std (us)": "Desv. est. del jitter (us)",
    "Worst-case late (us)": "Retraso máximo (us)",
    "tau (ms)": "tau (ms)",
    "C assumed (uF)": "C asumida (uF)",
    "Implied R (ohm)": "R inferida (ohm)",
    "Noise (counts)": "Ruido (cuentas)",
    "Max error raw (mV)": "Error crudo máximo (mV)",
    "Max error factory-cal (mV)": "Error calibrado máximo (mV)",
    "Measured cutoff -3dB (Hz)": "Corte medido -3 dB (Hz)",
    "Burn time (ms)": "Tiempo de quemado (ms)",
}


def _translate_plot_text(value):
    if not is_spanish() or not isinstance(value, str):
        return value
    for english, spanish in _PLOT_TRANSLATIONS.items():
        value = value.replace(english, spanish)
    return value


def stat_label(label: str) -> str:
    """Localize labels returned by the hardware-analysis layer."""
    return _STAT_TRANSLATIONS.get(label, label) if is_spanish() else label


def stat_value(value):
    """Localize categorical metric values without changing numeric values."""
    if not is_spanish():
        return value
    return {"YES": "SÍ", "no": "no"}.get(value, value)


def setup_page(active: str) -> None:
    """Apply shared CSS and render the consistent sidebar."""
    st.html(_GLOBAL_CSS)

    with st.sidebar:
        logo_data = base64.b64encode((ASSETS / "rocket-console-logo.svg").read_bytes()).decode()
        st.html(
            f'<div class="rc-brand"><img src="data:image/svg+xml;base64,{logo_data}" '
            'alt="Rocketry Console"></div>'
        )
        if "rc_language" not in st.session_state:
            st.session_state["rc_language"] = "English"
        language_key = f"_rc_language_input_{active.lower()}"
        if st.session_state.get(language_key) not in {"EN", "ES"}:
            st.session_state[language_key] = "ES" if is_spanish() else "EN"
        st.caption("LANGUAGE / IDIOMA")
        st.segmented_control(
            "Language / Idioma",
            ("EN", "ES"),
            key=language_key,
            on_change=_persist_language,
            args=(language_key,),
            label_visibility="collapsed",
        )
        st.caption(tr("ENGINEERING WORKSTATION", "ESTACIÓN DE INGENIERÍA"))
        for english, spanish, path, icon in NAV_ITEMS:
            st.page_link(path, label=tr(english, spanish), icon=icon)

        from blocks import find_ports
        from store import count_runs

        ports = find_ports()
        state = "ok" if ports else "off"
        port_text = escape(ports[0]) if ports else tr("ESP32 not detected", "ESP32 no detectada")
        active_labels = {english: tr(english, spanish) for english, spanish, _, _ in NAV_ITEMS}
        st.html(
            f"""
            <div class="rc-sidebar-meta">
              <div class="rc-status" data-state="{state}">
                <span class="rc-status-dot"></span><span>{port_text}</span>
              </div>
              <p>{count_runs()} {tr("saved runs", "corridas guardadas")}</p>
              <p>{tr("Active module", "Módulo activo")}: {escape(active_labels.get(active, active))}</p>
            </div>
            """
        )


def page_header(kicker: str, title: str, description: str) -> None:
    st.html(
        f"""
        <header class="rc-page-head">
          <div class="rc-page-kicker">{escape(kicker)}</div>
          <h1>{escape(title)}</h1>
          <p>{escape(description)}</p>
        </header>
        """
    )


def section_title(title: str) -> None:
    st.html(f'<h2 class="rc-section-title">{escape(title)}</h2>')


def style_plotly(fig, *, height: int | None = None):
    """Apply a console-native chart theme without changing the plotted data."""
    if is_spanish():
        if fig.layout.title and fig.layout.title.text:
            fig.layout.title.text = _translate_plot_text(fig.layout.title.text)
        for axis_name in ("xaxis", "yaxis"):
            axis = getattr(fig.layout, axis_name, None)
            if axis and axis.title and axis.title.text:
                axis.title.text = _translate_plot_text(axis.title.text)
        for annotation in fig.layout.annotations or ():
            annotation.text = _translate_plot_text(annotation.text)
        for trace in fig.data:
            if trace.name:
                trace.name = _translate_plot_text(trace.name)
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0d1219",
        font=dict(color="#aeb7c3", family="Aptos, Segoe UI, sans-serif", size=13),
        title=dict(font=dict(color="#eef2f7", size=17), x=0.02, xanchor="left"),
        colorway=PLOT_COLORS,
        hoverlabel=dict(bgcolor="#151c26", bordercolor="#3a4656", font_color="#eef2f7"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=55, r=25, t=65, b=50),
        height=height,
    )
    fig.update_xaxes(gridcolor="#222b37", zerolinecolor="#3a4656")
    fig.update_yaxes(gridcolor="#222b37", zerolinecolor="#3a4656")
    return fig


def themed_schematic(svg: bytes | str) -> str:
    """Recolor schemdraw SVG output for the dark console surface."""
    text = svg.decode() if isinstance(svg, (bytes, bytearray)) else svg
    return (
        text.replace("stroke:black", "stroke:#d7dee8")
        .replace('fill="black"', 'fill="#d7dee8"')
        .replace("fill:black", "fill:#d7dee8")
        .replace('font-family="sans"', 'font-family="Aptos, Segoe UI, sans-serif"')
    )


def schematic_data_uri(svg: bytes | str) -> str:
    """Return a sanitized data URI so Streamlit cannot strip inline SVG nodes."""
    themed = themed_schematic(svg).encode()
    return "data:image/svg+xml;base64," + base64.b64encode(themed).decode()
