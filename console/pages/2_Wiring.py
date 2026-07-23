"""Guided, pin-by-pin setup for every supported bench circuit."""
import sys
from html import escape
from pathlib import Path

import streamlit as st

CORE = Path(__file__).resolve().parent.parent / "core"
sys.path.insert(0, str(CORE))

import diagrams  # noqa: E402
import ui  # noqa: E402

st.set_page_config(
    page_title="Wiring | Rocketry Console",
    page_icon=":material/electrical_services:",
    layout="wide",
    initial_sidebar_state="auto",
)
ui.setup_page("Wiring")
ui.page_header(
    "Bench setup",
    "Wiring",
    "Choose what you want to measure, assemble it in order and verify the circuit before applying power.",
)

friendly_to_key = {guide["short"]: key for key, guide in diagrams.CIRCUIT_GUIDES.items()}
selected_short = st.radio(
    "What are you connecting?",
    list(friendly_to_key),
    horizontal=True,
    captions=[diagrams.CIRCUIT_GUIDES[key]["use_for"] for key in friendly_to_key.values()],
)
circuit_name = friendly_to_key[selected_short]
guide = diagrams.CIRCUIT_GUIDES[circuit_name]
svg, pins = diagrams.CIRCUITS[circuit_name]()

st.html(
    f"""
    <div class="rc-step-strip">
      <div class="rc-step-card"><span class="rc-flow-index">01</span><strong>Prepare</strong><p>{escape(guide["before"])}</p></div>
      <div class="rc-step-card"><span class="rc-flow-index">02</span><strong>Connect</strong><p>Follow each numbered connection from source to destination.</p></div>
      <div class="rc-step-card"><span class="rc-flow-index">03</span><strong>Verify</strong><p>Complete the inspection checklist before reconnecting USB power.</p></div>
    </div>
    """
)

st.html(
    f"""
    <div class="rc-safety">
      <strong>Power off before rewiring.</strong>
      {escape(guide["purpose"])} The diagram shows topology; the numbered list is the source of truth for each physical connection.
    </div>
    """
)

tab_prepare, tab_connect, tab_verify = st.tabs(
    [":material/inventory_2: Prepare", ":material/cable: Connect", ":material/fact_check: Verify"]
)

with tab_prepare:
    left, right = st.columns([1.1, 1])
    with left:
        st.subheader("Parts checklist")
        ready_parts = []
        for idx, part in enumerate(guide["parts"]):
            ready_parts.append(st.checkbox(part, key=f"{circuit_name}-part-{idx}"))
    with right:
        st.subheader("Measurement")
        st.write(guide["use_for"])
        if all(ready_parts):
            st.success("All parts are ready. Continue to Connect.", icon=":material/check_circle:")
        else:
            st.info("Collect the listed parts before building the circuit.", icon=":material/inventory_2:")

with tab_connect:
    diagram_col, connections_col = st.columns([1.55, 1])
    with diagram_col:
        st.subheader("Circuit topology")
        svg_text = ui.themed_schematic(svg)
        st.html(f'<div class="rc-schematic">{svg_text}</div>')
        st.caption("Signal flows from left to right. Ground and shared nodes branch vertically.")

    with connections_col:
        st.subheader("Pin-by-pin sequence")
        pin_html = []
        for idx, pin in enumerate(pins, start=1):
            pin_html.append(
                f"""
                <div class="rc-pin">
                  <span class="rc-pin-num">{idx}</span>
                  <div><code>{escape(pin["from"])} → {escape(pin["to"])}</code><p>{escape(pin["how"])}</p></div>
                </div>
                """
            )
        st.html('<div class="rc-card">' + "".join(pin_html) + "</div>")

with tab_verify:
    st.subheader("Pre-power inspection")
    checks = []
    for idx, check in enumerate(guide["verify"]):
        checks.append(st.checkbox(check, key=f"{circuit_name}-verify-{idx}"))

    if all(checks):
        st.success(
            "Visual inspection complete. Reconnect USB power, then open Bench and capture the matching firmware output.",
            icon=":material/power:",
        )
        st.page_link("pages/1_Bench.py", label="Continue to Bench", icon=":material/monitor_heart:")
    else:
        st.warning("Keep the ESP32 unpowered until every inspection item is confirmed.", icon=":material/warning:")

with st.expander("Why this wiring is versioned"):
    st.write(
        "The schematic and connection sequence are generated from `core/diagrams.py`. "
        "Changes can be reviewed with the firmware instead of relying on an untraceable photo."
    )
