"""Rocketry Console home and system status."""
import sys
from html import escape
from pathlib import Path

import streamlit as st

CORE = Path(__file__).resolve().parent / "core"
sys.path.insert(0, str(CORE))

import blocks  # noqa: E402
import store  # noqa: E402
import ui  # noqa: E402

st.set_page_config(
    page_title="Rocketry Console",
    page_icon=":material/rocket_launch:",
    layout="wide",
    initial_sidebar_state="auto",
)
ui.setup_page("Home")

ports = blocks.find_ports()
port_label = escape(ports[0]) if ports else "ESP32 offline"
port_state = "ok" if ports else "off"

st.html(
    f"""
    <section class="rc-hero">
      <div class="rc-hero-copy">
        <div class="rc-page-kicker">LOCAL ENGINEERING WORKSTATION</div>
        <h1>Measure. Model. Fly.</h1>
        <p>One console for hardware captures, propulsion studies, flight simulation and traceable run history.</p>
        <div class="rc-status" data-state="{port_state}">
          <span class="rc-status-dot"></span><span>{port_label}</span>
        </div>
      </div>
      <div class="rc-orbit" aria-label="Animated system telemetry">
        <div class="rc-crosshair"></div>
        <div class="rc-orbit-ring"></div>
        <div class="rc-orbit-scan"></div>
        <div class="rc-orbit-core"></div>
        <div class="rc-orbit-node"></div>
      </div>
    </section>
    """
)

ui.section_title("System status")
m1, m2, m3, m4 = st.columns(4)
m1.metric("ESP32", "Connected" if ports else "Not detected", help=", ".join(ports) if ports else "Connect by USB and check permissions.")
m2.metric("Saved runs", store.count_runs())
m3.metric("openMotor", "Ready" if (Path.home() / "openMotor" / ".venv" / "bin" / "python").exists() else "Unavailable")
m4.metric("OpenRocket", "Ready" if (Path.home() / "openrocket" / ".venv" / "bin" / "python").exists() else "Unavailable")

ui.section_title("Engineering loop")
st.html(
    """
    <div class="rc-flow">
      <div class="rc-flow-step"><span class="rc-flow-index">01</span><b>Wire</b><span>Build the bench circuit and verify every connection.</span></div>
      <div class="rc-flow-step"><span class="rc-flow-index">02</span><b>Measure</b><span>Capture a complete signal block from the ESP32.</span></div>
      <div class="rc-flow-step"><span class="rc-flow-index">03</span><b>Simulate</b><span>Explore motor geometry and fly a candidate vehicle.</span></div>
      <div class="rc-flow-step"><span class="rc-flow-index">04</span><b>Review</b><span>Save, reopen, compare and export every run.</span></div>
    </div>
    """
)

ui.section_title("Choose your next action")
left, middle, right = st.columns([1.15, 1, 1])
with left:
    st.html(ui.card("Hardware", "Capture a signal", "Read one complete serial block, detect its measurement type and inspect the raw response."))
    st.page_link("pages/1_Bench.py", label="Open Bench", icon=":material/monitor_heart:", width="stretch")
with middle:
    st.html(ui.card("Setup", "Wire the circuit", "Follow a guided pin-by-pin build sequence before connecting power or capturing data."))
    st.page_link("pages/2_Wiring.py", label="Open Wiring", icon=":material/electrical_services:", width="stretch")
with right:
    st.html(ui.card("Analysis", "Run a simulation", "Sweep viable BATES grains, then evaluate the complete vehicle in OpenRocket."))
    c1, c2 = st.columns(2)
    c1.page_link("pages/3_Motor.py", label="Motor", icon=":material/local_fire_department:", width="stretch")
    c2.page_link("pages/4_Flight.py", label="Flight", icon=":material/rocket_launch:", width="stretch")

st.caption("Simulation output supports engineering decisions. It does not replace design review, test evidence or launch safety procedures.")
