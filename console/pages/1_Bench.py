"""Capture and inspect one complete ESP32 data block."""
import sys
from pathlib import Path

import streamlit as st

CORE = Path(__file__).resolve().parent.parent / "core"
sys.path.insert(0, str(CORE))

import blocks  # noqa: E402
import plots  # noqa: E402
import store  # noqa: E402
import ui  # noqa: E402

st.set_page_config(
    page_title="Bench | Rocketry Console",
    page_icon=":material/monitor_heart:",
    layout="wide",
    initial_sidebar_state="auto",
)
ui.setup_page("Bench")
ui.page_header(
    "Hardware capture",
    "Bench",
    "Connect the ESP32, capture one complete measurement block and inspect the signal before saving it.",
)

if "block" not in st.session_state:
    st.session_state.block = None

ports = blocks.find_ports()

st.html(
    """
    <div class="rc-step-strip">
      <div class="rc-step-card"><span class="rc-flow-index">01</span><strong>Connect</strong><p>Use Wiring to verify the circuit, then connect the ESP32 by USB.</p></div>
      <div class="rc-step-card"><span class="rc-flow-index">02</span><strong>Capture</strong><p>Select the port and read one complete block from <code># BLOCK</code> to <code># END</code>.</p></div>
      <div class="rc-step-card"><span class="rc-flow-index">03</span><strong>Review</strong><p>Check the detected measurement, chart and derived values before saving.</p></div>
    </div>
    """
)

ui.section_title("Connection")
with st.container(key="bench-connection", border=True):
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        if not ports:
            st.error(
                "No serial device detected. Reconnect the USB cable, confirm the board is powered, "
                "and verify that your user can access the serial port.",
                icon=":material/usb_off:",
            )
        port = st.selectbox(
            "Serial port",
            ports or ["No port available"],
            disabled=not ports,
            help="The console checks ttyUSB and ttyACM devices reported by the operating system.",
        )
    with c2:
        baud = st.number_input(
            "Baud rate",
            value=blocks.DEFAULT_BAUD,
            min_value=1_200,
            step=9_600,
            help="Must match the firmware serial rate.",
        )
    with c3:
        timeout_s = st.number_input(
            "Capture timeout (s)",
            value=15,
            min_value=2,
            max_value=120,
            help="Maximum wait for a complete block.",
        )

    capture_clicked = st.button(
        "Capture block",
        type="primary",
        icon=":material/sensors:",
        disabled=not ports,
        width="stretch",
    )

if capture_clicked:
    with st.status(f"Reading {port}", expanded=True) as status:
        st.write("Waiting for the next `# BLOCK` marker and a complete `# END` marker.")
        try:
            block = blocks.open_and_read(port, baud=int(baud), timeout_s=float(timeout_s))
        except (OSError, ValueError) as exc:
            status.update(label="Serial capture failed", state="error")
            st.error(f"Could not read {port}: {exc}")
            block = None
        if block is None:
            status.update(label="No complete block received", state="error")
            st.error("Check the flashed firmware and confirm that it emits the shared block protocol.")
        else:
            st.session_state.block = block
            kind = plots.detect_kind(block)
            status.update(label=f"Captured {len(block.rows)} rows as {kind}", state="complete")

block = st.session_state.block

if block is None:
    ui.section_title("Waiting for data")
    st.info(
        "Start in Wiring if the circuit is not ready. When the ESP32 appears above, capture one block to reveal the chart and quality checks.",
        icon=":material/info:",
    )
    st.page_link("pages/2_Wiring.py", label="Open the wiring guide", icon=":material/electrical_services:")
    st.stop()

kind = plots.detect_kind(block)
ui.section_title(f"Captured result: {kind}")

meta_col, quality_col = st.columns([1.3, 1])
with meta_col:
    st.caption("CAPTURE SUMMARY")
    a, b, c = st.columns(3)
    a.metric("Rows", len(block.rows))
    b.metric("Columns", len(block.rows[0]) if block.rows else 0)
    c.metric("Detected type", kind)
with quality_col:
    st.caption("SOURCE METADATA")
    st.json(block.meta, expanded=False)
    if block.columns:
        st.caption("Columns: " + ", ".join(block.columns))

try:
    fig, stats = plots.plot_block(block)
except (KeyError, ValueError, IndexError, TypeError) as exc:
    st.error(f"This block was captured but cannot be plotted: {exc}")
    fig, stats = None, {}

if fig is not None:
    ui.style_plotly(fig, height=500)
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})

if stats:
    st.caption("DERIVED VALUES")
    metric_cols = st.columns(min(4, len(stats)))
    for idx, (label, value) in enumerate(stats.items()):
        metric_cols[idx % len(metric_cols)].metric(label, value)

with st.container(key="bench-save", border=True):
    st.subheader("Save this capture")
    note = st.text_input(
        "Run note",
        key="note_input",
        placeholder="Example: RC filter, 220 ohm, first cold run",
        help="A specific note makes comparisons easier later.",
    )
    if st.button("Save to History", icon=":material/save:", width="stretch"):
        rid = store.save_run(kind, block.meta, block.columns, block.rows, note=note.strip())
        st.success(f"Run #{rid} saved to History.")
        st.page_link("pages/5_History.py", label="Open History", icon=":material/history:")
