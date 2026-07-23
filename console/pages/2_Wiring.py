"""Guided, pin-by-pin setup for every supported bench circuit."""
import sys
from html import escape
from pathlib import Path

import streamlit as st

CORE = Path(__file__).resolve().parent.parent / "core"
sys.path.insert(0, str(CORE))

import diagrams  # noqa: E402
import ui  # noqa: E402
import wiring_guides  # noqa: E402

st.set_page_config(
    page_title="Wiring | Rocketry Console",
    page_icon=":material/electrical_services:",
    layout="wide",
    initial_sidebar_state="auto",
)
ui.setup_page("Wiring")
T = ui.tr
ui.page_header(
    T("Bench setup", "Montaje del banco"),
    T("Wiring", "Cableado"),
    T(
        "Choose what you want to measure, assemble it in order and verify the circuit before applying power.",
        "Elige qué quieres medir, arma el circuito en orden y verifícalo antes de aplicar alimentación.",
    ),
)

def guide_text(guide: dict, field: str):
    return guide.get(f"{field}_es", guide[field]) if ui.is_spanish() else guide[field]


friendly_to_key = {guide_text(guide, "short"): key for key, guide in wiring_guides.GUIDES.items()}
selected_short = st.radio(
    T("What are you connecting?", "¿Qué vas a conectar?"),
    list(friendly_to_key),
    horizontal=True,
    captions=[guide_text(wiring_guides.GUIDES[key], "use_for") for key in friendly_to_key.values()],
)
circuit_name = friendly_to_key[selected_short]
guide = wiring_guides.GUIDES[circuit_name]
svg, pins = diagrams.CIRCUITS[circuit_name]()

st.html(
    f"""
    <div class="rc-step-strip">
      <div class="rc-step-card"><span class="rc-flow-index">01</span><strong>{T("Prepare", "Prepara")}</strong><p>{escape(guide_text(guide, "before"))}</p></div>
      <div class="rc-step-card"><span class="rc-flow-index">02</span><strong>{T("Connect", "Conecta")}</strong><p>{T("Follow each numbered connection from source to destination.", "Sigue cada conexión numerada desde el origen hasta el destino.")}</p></div>
      <div class="rc-step-card"><span class="rc-flow-index">03</span><strong>{T("Verify", "Verifica")}</strong><p>{T("Complete the inspection checklist before reconnecting USB power.", "Completa la inspección antes de volver a conectar la alimentación USB.")}</p></div>
    </div>
    """
)

st.html(
    f"""
    <div class="rc-safety">
      <strong>{T("Power off before rewiring.", "Desconecta la alimentación antes de recablear.")}</strong>
      {escape(guide_text(guide, "purpose"))} {T("The diagram shows topology; the numbered list is the source of truth for each physical connection.", "El diagrama muestra la topología; la lista numerada es la referencia para cada conexión física.")}
    </div>
    """
)

tab_prepare, tab_connect, tab_verify = st.tabs(
    [
        T(":material/inventory_2: Prepare", ":material/inventory_2: Preparar"),
        T(":material/cable: Connect", ":material/cable: Conectar"),
        T(":material/fact_check: Verify", ":material/fact_check: Verificar"),
    ]
)

with tab_prepare:
    left, right = st.columns([1.1, 1])
    with left:
        st.subheader(T("Parts checklist", "Lista de componentes"))
        ready_parts = []
        for idx, part in enumerate(guide_text(guide, "parts")):
            ready_parts.append(st.checkbox(part, key=f"{circuit_name}-part-{idx}"))
    with right:
        st.subheader(T("Measurement", "Medición"))
        st.write(guide_text(guide, "use_for"))
        if all(ready_parts):
            st.success(T("All parts are ready. Continue to Connect.", "Todos los componentes están listos. Continúa a Conectar."), icon=":material/check_circle:")
        else:
            st.info(T("Collect the listed parts before building the circuit.", "Reúne los componentes indicados antes de armar el circuito."), icon=":material/inventory_2:")

with tab_connect:
    diagram_col, connections_col = st.columns([1.55, 1])
    with diagram_col:
        st.subheader(T("Circuit topology", "Topología del circuito"))
        svg_text = ui.themed_schematic(svg)
        st.html(f'<div class="rc-schematic">{svg_text}</div>')
        st.caption(T("Signal flows from left to right. Ground and shared nodes branch vertically.", "La señal fluye de izquierda a derecha. Tierra y nodos compartidos se ramifican verticalmente."))

    with connections_col:
        st.subheader(T("Pin-by-pin sequence", "Secuencia pin a pin"))
        pin_html = []
        for idx, pin in enumerate(pins, start=1):
            pin_from = pin.get("from_es", pin["from"]) if ui.is_spanish() else pin["from"]
            pin_to = pin.get("to_es", pin["to"]) if ui.is_spanish() else pin["to"]
            pin_how = pin.get("how_es", pin["how"]) if ui.is_spanish() else pin["how"]
            pin_html.append(
                f"""
                <div class="rc-pin">
                  <span class="rc-pin-num">{idx}</span>
                  <div><code>{escape(pin_from)} → {escape(pin_to)}</code><p>{escape(pin_how)}</p></div>
                </div>
                """
            )
        st.html('<div class="rc-card">' + "".join(pin_html) + "</div>")

with tab_verify:
    st.subheader(T("Pre-power inspection", "Inspección antes de energizar"))
    checks = []
    for idx, check in enumerate(guide_text(guide, "verify")):
        checks.append(st.checkbox(check, key=f"{circuit_name}-verify-{idx}"))

    if all(checks):
        st.success(
            T(
                "Visual inspection complete. Reconnect USB power, then open Bench and capture the matching firmware output.",
                "Inspección visual completa. Reconecta la alimentación USB, abre Banco de pruebas y captura la salida del firmware.",
            ),
            icon=":material/power:",
        )
        st.page_link("pages/1_Bench.py", label=T("Continue to Bench", "Continuar al banco"), icon=":material/monitor_heart:")
    else:
        st.warning(T("Keep the ESP32 unpowered until every inspection item is confirmed.", "Mantén la ESP32 sin alimentación hasta confirmar toda la inspección."), icon=":material/warning:")

with st.expander(T("Why this wiring is versioned", "Por qué este cableado está versionado")):
    st.write(T(
        "The schematic and connection sequence are generated from `core/diagrams.py`. "
        "Changes can be reviewed with the firmware instead of relying on an untraceable photo.",
        "El esquema y la secuencia de conexión se generan desde `core/diagrams.py`. "
        "Los cambios pueden revisarse junto al firmware sin depender de una foto sin trazabilidad.",
    ))
