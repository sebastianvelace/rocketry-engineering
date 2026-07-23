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
T = ui.tr

ports = blocks.find_ports()
port_label = escape(ports[0]) if ports else T("ESP32 offline", "ESP32 desconectada")
port_state = "ok" if ports else "off"

st.html(
    f"""
    <section class="rc-hero">
      <div class="rc-hero-copy">
        <div class="rc-page-kicker">{T("LOCAL ENGINEERING WORKSTATION", "ESTACIÓN LOCAL DE INGENIERÍA")}</div>
        <h1>{T("Measure. Model. Fly.", "Mide. Modela. Vuela.")}</h1>
        <p>{T(
            "One console for hardware captures, propulsion studies, flight simulation and traceable run history.",
            "Una consola para capturas de hardware, estudios de propulsión, simulación de vuelo e historial trazable.",
        )}</p>
        <div class="rc-status" data-state="{port_state}">
          <span class="rc-status-dot"></span><span>{port_label}</span>
        </div>
      </div>
      <div class="rc-mission-line">
        <div class="rc-signal" aria-hidden="true"></div>
        <strong>{T("MEASURE → VERIFY → DECIDE", "MEDIR → VERIFICAR → DECIDIR")}</strong>
        <span>{T("One result is a hypothesis. Agreement across methods turns it into evidence.", "Un resultado es una hipótesis. La concordancia entre métodos lo convierte en evidencia.")}</span>
      </div>
    </section>
    """
)

ui.section_title(T("System status", "Estado del sistema"))
m1, m2, m3, m4 = st.columns(4)
m1.metric(
    "ESP32",
    T("Connected", "Conectada") if ports else T("Not detected", "No detectada"),
    help=", ".join(ports) if ports else T("Connect by USB and check permissions.", "Conecta por USB y verifica los permisos."),
)
m2.metric(T("Saved runs", "Corridas guardadas"), store.count_runs())
m3.metric(
    "openMotor",
    T("Ready", "Listo") if (Path.home() / "openMotor" / ".venv" / "bin" / "python").exists() else T("Unavailable", "No disponible"),
)
m4.metric(
    "OpenRocket",
    T("Ready", "Listo") if (Path.home() / "openrocket" / ".venv" / "bin" / "python").exists() else T("Unavailable", "No disponible"),
)

ui.section_title(T("Engineering loop", "Ciclo de ingeniería"))
st.html(
    f"""
    <div class="rc-flow">
      <div class="rc-flow-step"><span class="rc-flow-index">01</span><b>{T("Wire", "Cablea")}</b><span>{T("Build the bench circuit and verify every connection.", "Arma el circuito del banco y verifica cada conexión.")}</span></div>
      <div class="rc-flow-step"><span class="rc-flow-index">02</span><b>{T("Measure", "Mide")}</b><span>{T("Capture a complete signal block from the ESP32.", "Captura un bloque completo de señal desde la ESP32.")}</span></div>
      <div class="rc-flow-step"><span class="rc-flow-index">03</span><b>{T("Simulate", "Simula")}</b><span>{T("Explore motor geometry and fly a candidate vehicle.", "Explora la geometría del motor y vuela un vehículo candidato.")}</span></div>
      <div class="rc-flow-step"><span class="rc-flow-index">04</span><b>{T("Review", "Revisa")}</b><span>{T("Save, reopen, compare and export every run.", "Guarda, reabre, compara y exporta cada corrida.")}</span></div>
    </div>
    """
)

ui.section_title(T("Choose your next action", "Elige tu siguiente acción"))
left, middle, right = st.columns([1.15, 1, 1])
with left:
    st.html(f'<div class="rc-action"><small>01 / {T("HARDWARE", "HARDWARE")}</small><h3>{T("Capture a signal", "Captura una señal")}</h3><p>{T("Read one serial block and inspect the raw response.", "Lee un bloque serial e inspecciona la respuesta cruda.")}</p></div>')
    st.page_link("pages/1_Bench.py", label=T("Open Bench", "Abrir banco"), icon=":material/monitor_heart:", width="stretch")
with middle:
    st.html(f'<div class="rc-action"><small>02 / {T("SETUP", "MONTAJE")}</small><h3>{T("Wire the circuit", "Cablea el circuito")}</h3><p>{T("Follow the pin sequence before applying power.", "Sigue la secuencia de pines antes de aplicar alimentación.")}</p></div>')
    st.page_link("pages/2_Wiring.py", label=T("Open Wiring", "Abrir cableado"), icon=":material/electrical_services:", width="stretch")
with right:
    st.html(f'<div class="rc-action"><small>03 / {T("ANALYSIS", "ANÁLISIS")}</small><h3>{T("Run a simulation", "Ejecuta una simulación")}</h3><p>{T("Explore the motor, then evaluate the complete vehicle.", "Explora el motor y luego evalúa el vehículo completo.")}</p></div>')
    c1, c2 = st.columns(2)
    c1.page_link("pages/3_Motor.py", label="Motor", icon=":material/local_fire_department:", width="stretch")
    c2.page_link("pages/4_Flight.py", label=T("Flight", "Vuelo"), icon=":material/rocket_launch:", width="stretch")

st.caption(T(
    "Simulation output supports engineering decisions. It does not replace design review, test evidence or launch safety procedures.",
    "La simulación apoya decisiones de ingeniería. No reemplaza la revisión de diseño, la evidencia de pruebas ni los procedimientos de seguridad.",
))
