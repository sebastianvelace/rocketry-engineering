"""Rocketry Console — home page.

Local Streamlit app that centralizes bench captures (ESP32 DAQ), and later
motor/flight simulations, in one place with a persistent run history.

Run with:
    console/.venv/bin/streamlit run console/app.py
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "core"))
import blocks  # noqa: E402
import store  # noqa: E402

st.set_page_config(page_title="Rocketry Console", page_icon="🚀", layout="wide")

st.title("Rocketry Console")
st.caption("Local dashboard for the solid-propellant rocket engineering project.")

col1, col2, col3 = st.columns(3)

with col1:
    ports = blocks.find_ports()
    if ports:
        st.metric("ESP32", "connected", help=", ".join(ports))
    else:
        st.metric("ESP32", "not detected")

with col2:
    st.metric("Saved runs", store.count_runs())

with col3:
    st.metric("Stage", "measure", help="measure -> estimate -> control")

st.divider()
st.markdown(
    """
    **Pages** (left sidebar):
    - **Bench** — capture a block from the ESP32, auto-detect its kind, plot it, save it.
    - More pages (wiring diagrams, motor sweeps, flight sims, history) land here as
      they're built — see `CLAUDE.md` and the plan for the roadmap.
    """
)
