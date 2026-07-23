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

ACCENT = "#ff6b2c"
PLOT_COLORS = ["#ff6b2c", "#5bc0eb", "#9ee493", "#ffd166", "#c7a0ff", "#f28fad"]

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
  --rc-accent: #ff6b2c;
  --rc-accent-soft: rgba(255, 107, 44, 0.12);
  --rc-ok: #68d391;
  --rc-warn: #f6c85f;
  --rc-danger: #ff6b6b;
  --rc-radius: 9px;
}

html { scroll-behavior: smooth; }
body { color-scheme: dark; }

[data-testid="stAppViewContainer"] {
  background:
    linear-gradient(rgba(255,255,255,.018) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.018) 1px, transparent 1px),
    #080b10;
  background-size: 32px 32px;
}

[data-testid="stMainBlockContainer"] {
  max-width: 1440px;
  padding-top: 2.25rem;
  padding-bottom: 5rem;
}

[data-testid="stSidebar"] {
  background: #0b0f15;
}

[data-testid="stSidebarContent"] {
  padding: 1.2rem 1rem 2rem;
}

[data-testid="stLogo"] {
  margin: 0 0 .65rem;
  max-width: 210px;
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
  transition: transform 150ms ease, border-color 150ms ease, background 150ms ease;
}

[data-testid="stButton"] button:hover, [data-testid="stFormSubmitButton"] button:hover,
[data-testid="stDownloadButton"] button:hover, [data-testid="stPageLink"] a:hover {
  border-color: var(--rc-accent);
  transform: translateY(-1px);
}

[data-testid="stButton"] button:active, [data-testid="stFormSubmitButton"] button:active,
[data-testid="stDownloadButton"] button:active, [data-testid="stPageLink"] a:active {
  transform: translateY(1px) scale(.99);
}

[data-testid="stMetric"] {
  background: linear-gradient(145deg, rgba(21,28,38,.96), rgba(12,16,23,.96));
  border: 1px solid var(--rc-line);
  border-radius: var(--rc-radius);
  padding: 1rem 1.1rem;
  min-height: 112px;
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

[data-testid="stExpander"], [data-testid="stForm"] {
  border-color: var(--rc-line);
  background: rgba(16,21,29,.72);
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
  overflow: hidden;
  min-height: 390px;
  padding: clamp(1.5rem, 4vw, 3.6rem);
  border: 1px solid var(--rc-line);
  border-radius: var(--rc-radius);
  background:
    radial-gradient(circle at 82% 48%, rgba(255,107,44,.12), transparent 25%),
    linear-gradient(120deg, rgba(21,28,38,.98), rgba(8,11,16,.96));
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(280px, .8fr);
  align-items: center;
  gap: 2rem;
}

.rc-hero-copy { position: relative; z-index: 2; }
.rc-hero h1 {
  margin: .5rem 0 .9rem;
  max-width: 760px;
  font-size: clamp(2.8rem, 6vw, 6rem);
  line-height: .88;
  letter-spacing: -.055em;
}
.rc-hero p {
  max-width: 560px;
  color: #a8b1be;
  font-size: 1.02rem;
}

.rc-orbit {
  position: relative;
  width: min(32vw, 330px);
  aspect-ratio: 1;
  justify-self: center;
}
.rc-orbit-ring, .rc-orbit-core, .rc-orbit-scan, .rc-orbit-node {
  position: absolute;
  border-radius: 50%;
}
.rc-orbit-ring { inset: 4%; border: 1px solid #354151; }
.rc-orbit-ring::before, .rc-orbit-ring::after {
  content: "";
  position: absolute;
  border: 1px solid #222b37;
  border-radius: inherit;
}
.rc-orbit-ring::before { inset: 18%; }
.rc-orbit-ring::after { inset: 36%; border-style: dashed; }
.rc-orbit-core {
  inset: 43%;
  background: var(--rc-accent);
  box-shadow: 0 0 30px rgba(255,107,44,.42);
}
.rc-orbit-scan {
  inset: 4%;
  background: conic-gradient(from 30deg, transparent 0 78%, rgba(255,107,44,.18), transparent 96%);
  animation: rc-scan 8s linear infinite;
}
.rc-orbit-node {
  width: 12px; height: 12px; left: 14%; top: 32%;
  background: var(--rc-text);
  border: 3px solid var(--rc-accent);
  box-shadow: 0 0 0 6px rgba(255,107,44,.1);
  animation: rc-pulse 2.5s ease-in-out infinite;
}
.rc-crosshair::before, .rc-crosshair::after {
  content: "";
  position: absolute;
  background: #29313d;
}
.rc-crosshair::before { width: 100%; height: 1px; left: 0; top: 50%; }
.rc-crosshair::after { width: 1px; height: 100%; top: 0; left: 50%; }

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
  gap: 1px;
  background: var(--rc-line);
  border: 1px solid var(--rc-line);
  border-radius: var(--rc-radius);
  overflow: hidden;
  margin: .5rem 0 1.5rem;
}
.rc-flow-step { background: #0d1219; padding: 1rem; min-height: 120px; }
.rc-flow-step b { display: block; color: var(--rc-text); margin: .45rem 0 .3rem; }
.rc-flow-step span { color: var(--rc-muted); font-size: .86rem; }
.rc-flow-index { color: var(--rc-accent) !important; font: 650 .68rem/1 "IBM Plex Mono", monospace; }

.rc-card {
  border: 1px solid var(--rc-line);
  border-radius: var(--rc-radius);
  background: rgba(16,21,29,.84);
  padding: 1rem 1.05rem;
  height: 100%;
}
.rc-card h3 { font-size: 1rem; margin: 0 0 .35rem; }
.rc-card p { color: var(--rc-muted); font-size: .88rem; margin: 0; }
.rc-card .rc-card-tag {
  color: var(--rc-accent);
  font: 650 .68rem/1.2 "IBM Plex Mono", monospace;
  text-transform: uppercase;
  letter-spacing: .1em;
  margin-bottom: .7rem;
}

.rc-step-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(240px, 1fr));
  gap: .75rem;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  padding: .1rem .1rem .65rem;
  scrollbar-color: var(--rc-accent) var(--rc-panel);
}
.rc-step-card {
  scroll-snap-align: start;
  border: 1px solid var(--rc-line);
  border-radius: var(--rc-radius);
  background: #0d1219;
  padding: 1rem;
  min-height: 138px;
}
.rc-step-card strong { display: block; margin: .45rem 0; }
.rc-step-card p { margin: 0; color: var(--rc-muted); font-size: .88rem; }

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
  min-height: 330px;
  display: grid;
  place-items: center;
  padding: 1.4rem;
  border: 1px solid var(--rc-line);
  border-radius: var(--rc-radius);
  background: #0d1219;
  overflow-x: auto;
}
.rc-schematic svg { width: 100%; max-height: 430px; }

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

@keyframes rc-scan { to { transform: rotate(360deg); } }
@keyframes rc-pulse { 50% { transform: scale(.76); opacity: .7; } }

@media (max-width: 900px) {
  [data-testid="stMainBlockContainer"] { padding-inline: 1rem; padding-top: 1.2rem; }
  .rc-hero { grid-template-columns: 1fr; min-height: auto; }
  .rc-orbit { width: min(74vw, 290px); }
  .rc-flow { grid-template-columns: 1fr 1fr; }
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
    ("Home", "app.py", ":material/home:"),
    ("Bench", "pages/1_Bench.py", ":material/monitor_heart:"),
    ("Wiring", "pages/2_Wiring.py", ":material/electrical_services:"),
    ("Motor", "pages/3_Motor.py", ":material/local_fire_department:"),
    ("Flight", "pages/4_Flight.py", ":material/rocket_launch:"),
    ("History", "pages/5_History.py", ":material/history:"),
)


def setup_page(active: str) -> None:
    """Apply shared CSS and render the consistent sidebar."""
    st.html(_GLOBAL_CSS)

    with st.sidebar:
        logo_data = base64.b64encode((ASSETS / "rocket-console-logo.svg").read_bytes()).decode()
        st.html(
            f'<div class="rc-brand"><img src="data:image/svg+xml;base64,{logo_data}" '
            'alt="Rocketry Console"></div>'
        )
        st.caption("ENGINEERING WORKSTATION")
        for label, path, icon in NAV_ITEMS:
            st.page_link(path, label=label, icon=icon)

        from blocks import find_ports
        from store import count_runs

        ports = find_ports()
        state = "ok" if ports else "off"
        port_text = escape(ports[0]) if ports else "ESP32 not detected"
        st.html(
            f"""
            <div class="rc-sidebar-meta">
              <div class="rc-status" data-state="{state}">
                <span class="rc-status-dot"></span><span>{port_text}</span>
              </div>
              <p>{count_runs()} saved runs</p>
              <p>Active module: {escape(active)}</p>
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


def card(tag: str, title: str, body: str) -> str:
    return (
        '<div class="rc-card">'
        f'<div class="rc-card-tag">{escape(tag)}</div>'
        f"<h3>{escape(title)}</h3><p>{escape(body)}</p></div>"
    )


def style_plotly(fig, *, height: int | None = None):
    """Apply a console-native chart theme without changing the plotted data."""
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
