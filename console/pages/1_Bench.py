"""Bench page: capture one block from the ESP32, auto-detect its kind, plot it,
and optionally save it to the run history."""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
import blocks  # noqa: E402
import plots  # noqa: E402
import store  # noqa: E402

st.set_page_config(page_title="Bench — Rocketry Console", layout="wide")
st.title("Bench capture")
st.caption("Capture one block from the ESP32 over serial, auto-detect what it is, plot it.")

col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    ports = blocks.find_ports()
    if not ports:
        st.warning("No serial port found. Plug in the ESP32 (check `dialout` group / cable).")
    port = st.selectbox("Serial port", ports or ["(none found)"], disabled=not ports)

with col2:
    baud = st.number_input("Baud", value=blocks.DEFAULT_BAUD, step=9600)

with col3:
    timeout_s = st.number_input("Timeout (s)", value=15, min_value=2, max_value=120)

if "block" not in st.session_state:
    st.session_state.block = None

capture_clicked = st.button("Capture one block", type="primary", disabled=not ports)

if capture_clicked:
    with st.spinner(f"Reading from {port} ..."):
        try:
            block = blocks.open_and_read(port, baud=int(baud), timeout_s=float(timeout_s))
        except Exception as e:
            st.error(f"Failed to read from {port}: {e}")
            block = None
    if block is None:
        st.error("No complete block arrived before the timeout. Is the right firmware flashed?")
    else:
        st.session_state.block = block
        st.success(f"Captured {len(block.rows)} rows, kind={plots.detect_kind(block)}")

block = st.session_state.block

if block is not None:
    kind = plots.detect_kind(block)
    st.subheader(f"Result — detected kind: `{kind}`")

    left, right = st.columns([3, 1])
    with right:
        st.markdown("**Meta**")
        st.json(block.meta)
        if block.columns:
            st.markdown("**Columns**")
            st.write(block.columns)

    try:
        fig, stats = plots.plot_block(block)
    except Exception as e:
        st.error(f"Could not render this block kind ({kind}): {e}")
        fig, stats = None, {}

    with left:
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)

    if stats:
        st.markdown("**Derived numbers**")
        st.table({"value": stats})

    st.divider()
    note = st.text_input("Note for this run (optional)", key="note_input")
    if st.button("Save this run to history"):
        rid = store.save_run(kind, block.meta, block.columns, block.rows, note=note)
        st.success(f"Saved as run #{rid}.")
else:
    st.info("No capture yet. Select a port and click **Capture one block**.")
