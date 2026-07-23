"""Read-only live view of agent activity mirrored from the terminal."""
import sys
from html import escape
from pathlib import Path

import streamlit as st

CORE = Path(__file__).resolve().parent.parent / "core"
sys.path.insert(0, str(CORE))

import agent_feed  # noqa: E402
import store  # noqa: E402
import ui  # noqa: E402

st.set_page_config(
    page_title="Agent | Rocketry Console",
    page_icon=":material/terminal:",
    layout="wide",
    initial_sidebar_state="auto",
)
ui.setup_page("Agent")
T = ui.tr
ui.page_header(
    T("Local activity bridge", "Puente local de actividad"),
    T("Agent", "Agente"),
    T(
        "Keep the agent in your terminal and inspect its progress here without giving the browser shell access.",
        "Mantén el agente en tu terminal y revisa su progreso aquí sin dar acceso de shell al navegador.",
    ),
)

st.caption(T(
    "Start a mirrored session from the repository root:",
    "Inicia una sesión reflejada desde la raíz del repositorio:",
))
st.code(
    'python console/tools/agent_relay.py --provider codex "Run the console checks"\n'
    'python console/tools/agent_relay.py --provider claude "Run the console checks"',
    language="bash",
)


@st.fragment(run_every=2.0)
def live_activity() -> None:
    events = agent_feed.read_events(80)
    latest_run = store.latest_run()

    status_col, run_col = st.columns(2)
    if events:
        latest = events[-1]
        status_col.metric(
            T("Latest agent event", "Último evento del agente"),
            latest.get("event", "update"),
        )
        status_col.caption(latest.get("provider", "agent"))
    else:
        status_col.metric(T("Agent bridge", "Puente del agente"), T("Waiting", "Esperando"))

    if latest_run:
        run_col.metric(
            T("Latest saved result", "Último resultado guardado"),
            f"#{latest_run.id} · {latest_run.kind}",
        )
        run_col.caption(latest_run.created_at)
    else:
        run_col.metric(T("Latest saved result", "Último resultado guardado"), T("None", "Ninguno"))

    ui.section_title(T("Live activity", "Actividad en vivo"))
    if not events:
        st.info(T(
            "No mirrored agent has emitted an event yet. Existing Codex or Claude sessions are not intercepted.",
            "Ningún agente reflejado ha emitido eventos. Las sesiones existentes de Codex o Claude no se interceptan.",
        ))
        return

    rows = []
    for item in reversed(events[-30:]):
        rows.append(
            '<div class="rc-event">'
            f'<time>{escape(str(item.get("time", ""))[11:19])}</time>'
            f'<strong>{escape(str(item.get("provider", "agent")))} · {escape(str(item.get("event", "update")))}</strong>'
            f'<p>{escape(str(item.get("message", "")))}</p>'
            "</div>"
        )
    st.html('<div class="rc-events">' + "".join(rows) + "</div>")


live_activity()

st.caption(T(
    "This page reads a bounded local JSONL feed. It cannot approve commands or execute shell operations.",
    "Esta página lee un registro JSONL local y acotado. No puede aprobar comandos ni ejecutar operaciones de shell.",
))
