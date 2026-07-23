"""Wiring page: pick a bench circuit, see its schematic and an explicit
pin-to-pin table. The table is what actually prevents mis-wiring; the
schematic gives the overall shape at a glance."""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
import diagrams  # noqa: E402

st.set_page_config(page_title="Wiring — Rocketry Console", layout="wide")
st.title("Wiring diagrams")
st.caption("Generated from code (schemdraw), so they stay reproducible instead of a one-off photo.")

circuit_name = st.selectbox("Circuit", list(diagrams.CIRCUITS.keys()))
fn = diagrams.CIRCUITS[circuit_name]

svg, pins = fn()

col_diagram, col_table = st.columns([2, 1])

with col_diagram:
    st.image(svg, use_container_width=True)

with col_table:
    st.markdown("**Pin-to-pin connections**")
    for i, p in enumerate(pins, start=1):
        st.markdown(f"**{i}.** `{p['from']}` → `{p['to']}`")
        st.caption(p["how"])

st.divider()
st.caption(
    "Source: console/core/diagrams.py. Matches the wiring comments in the "
    "corresponding avionics/daq-fase1 firmware files exactly."
)
