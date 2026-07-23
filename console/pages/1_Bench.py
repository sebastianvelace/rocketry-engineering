"""Capture and inspect one complete ESP32 data block."""
import sys
from pathlib import Path

import streamlit as st

CORE = Path(__file__).resolve().parent.parent / "core"
sys.path.insert(0, str(CORE))

import blocks  # noqa: E402
import plots  # noqa: E402
import services  # noqa: E402
import ui  # noqa: E402

st.set_page_config(
    page_title="Bench | Rocketry Console",
    page_icon=":material/monitor_heart:",
    layout="wide",
    initial_sidebar_state="auto",
)
ui.setup_page("Bench")
T = ui.tr
ui.page_header(
    T("Hardware capture", "Captura de hardware"),
    T("Bench", "Banco de pruebas"),
    T(
        "Connect the ESP32, capture one complete measurement block and inspect the signal before saving it.",
        "Conecta la ESP32, captura un bloque completo e inspecciona la señal antes de guardarla.",
    ),
)

if "block" not in st.session_state:
    st.session_state.block = None

bench_service = services.BenchService()
try:
    ports = bench_service.list_ports()
except services.ServiceError as exc:
    ports = []
    st.error(str(exc))

st.html(
    f"""
    <div class="rc-step-strip">
      <div class="rc-step-card"><span class="rc-flow-index">01</span><strong>{T("Connect", "Conecta")}</strong><p>{T("Use Wiring to verify the circuit, then connect the ESP32 by USB.", "Usa Cableado para verificar el circuito y conecta la ESP32 por USB.")}</p></div>
      <div class="rc-step-card"><span class="rc-flow-index">02</span><strong>{T("Capture", "Captura")}</strong><p>{T("Select the port and read one complete block from", "Selecciona el puerto y lee un bloque completo desde")} <code># BLOCK</code> {T("to", "hasta")} <code># END</code>.</p></div>
      <div class="rc-step-card"><span class="rc-flow-index">03</span><strong>{T("Review", "Revisa")}</strong><p>{T("Check the detected measurement, chart and derived values before saving.", "Revisa la medición detectada, la gráfica y los valores derivados antes de guardar.")}</p></div>
    </div>
    """
)

ui.section_title(T("Connection", "Conexión"))
with st.container(key="bench-connection"):
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        if not ports:
            st.error(
                T(
                    "No serial device detected. Reconnect the USB cable, confirm the board is powered, "
                    "and verify that your user can access the serial port.",
                    "No se detectó un dispositivo serial. Reconecta el cable USB, confirma que la placa tiene alimentación "
                    "y verifica que tu usuario pueda acceder al puerto serial.",
                ),
                icon=":material/usb_off:",
            )
        port = st.selectbox(
            T("Serial port", "Puerto serial"),
            ports or [T("No port available", "No hay puerto disponible")],
            disabled=not ports,
            help=T(
                "The console checks USB serial devices reported by the operating system.",
                "La consola revisa los dispositivos seriales USB reportados por el sistema operativo.",
            ),
        )
    with c2:
        baud = st.number_input(
            T("Baud rate", "Velocidad en baudios"),
            value=blocks.DEFAULT_BAUD,
            min_value=1_200,
            step=9_600,
            help=T("Must match the firmware serial rate.", "Debe coincidir con la velocidad serial del firmware."),
        )
    with c3:
        timeout_s = st.number_input(
            T("Capture timeout (s)", "Tiempo límite de captura (s)"),
            value=15,
            min_value=2,
            max_value=120,
            help=T("Maximum wait for a complete block.", "Espera máxima por un bloque completo."),
        )

    capture_clicked = st.button(
        T("Capture block", "Capturar bloque"),
        type="primary",
        icon=":material/sensors:",
        disabled=not ports,
        width="stretch",
    )

if capture_clicked:
    with st.status(T(f"Reading {port}", f"Leyendo {port}"), expanded=True) as status:
        st.write(T(
            "Waiting for the next `# BLOCK` marker and a complete `# END` marker.",
            "Esperando el siguiente marcador `# BLOCK` y un marcador `# END` completo.",
        ))
        try:
            capture = bench_service.capture(
                services.BenchCaptureRequest(
                    port=port,
                    baud=int(baud),
                    timeout_s=float(timeout_s),
                )
            )
            block = capture.block
            st.session_state.block = block
            status.update(
                label=T(
                    f"Captured {len(block.rows)} rows as {capture.detected_kind}",
                    f"Se capturaron {len(block.rows)} filas como {capture.detected_kind}",
                ),
                state="complete",
            )
        except services.ServiceError as exc:
            block = None
            status.update(label=T("Serial capture failed", "La captura serial falló"), state="error")
            if exc.code == "capture_timeout":
                st.error(T(
                    "No complete block was received. Check the flashed firmware and confirm that it emits the shared block protocol.",
                    "No se recibió un bloque completo. Revisa el firmware cargado y confirma que emita el protocolo de bloques compartido.",
                ))
            else:
                st.error(str(exc))

block = st.session_state.block

if block is None:
    ui.section_title(T("Waiting for data", "Esperando datos"))
    st.info(
        T(
            "Start in Wiring if the circuit is not ready. When the ESP32 appears above, capture one block to reveal the chart and quality checks.",
            "Empieza en Cableado si el circuito no está listo. Cuando aparezca la ESP32, captura un bloque para ver la gráfica y las verificaciones.",
        ),
        icon=":material/info:",
    )
    st.page_link("pages/2_Wiring.py", label=T("Open the wiring guide", "Abrir la guía de cableado"), icon=":material/electrical_services:")
    st.stop()

kind = plots.detect_kind(block)
ui.section_title(T(f"Captured result: {kind}", f"Resultado capturado: {kind}"))

meta_col, quality_col = st.columns([1.3, 1])
with meta_col:
    st.caption(T("CAPTURE SUMMARY", "RESUMEN DE CAPTURA"))
    a, b, c = st.columns(3)
    a.metric(T("Rows", "Filas"), len(block.rows))
    b.metric(T("Columns", "Columnas"), len(block.rows[0]) if block.rows else 0)
    c.metric(T("Detected type", "Tipo detectado"), kind)
with quality_col:
    st.caption(T("SOURCE METADATA", "METADATOS DE ORIGEN"))
    st.json(block.meta, expanded=False)
    if block.columns:
        st.caption(T("Columns", "Columnas") + ": " + ", ".join(block.columns))

try:
    fig, stats = plots.plot_block(block)
except (KeyError, ValueError, IndexError, TypeError) as exc:
    st.error(T(
        f"This block was captured but cannot be plotted: {exc}",
        f"El bloque fue capturado pero no se puede graficar: {exc}",
    ))
    fig, stats = None, {}

if fig is not None:
    ui.style_plotly(fig, height=500)
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})

if stats:
    st.caption(T("DERIVED VALUES", "VALORES DERIVADOS"))
    metric_cols = st.columns(min(4, len(stats)))
    for idx, (label, value) in enumerate(stats.items()):
        metric_cols[idx % len(metric_cols)].metric(ui.stat_label(label), ui.stat_value(value))

with st.container(key="bench-save"):
    st.subheader(T("Save this capture", "Guardar esta captura"))
    note = st.text_input(
        T("Run note", "Nota de la corrida"),
        key="note_input",
        placeholder=T("Example: RC filter, 220 ohm, first cold run", "Ejemplo: filtro RC, 220 ohm, primera corrida en frío"),
        help=T("A specific note makes comparisons easier later.", "Una nota específica facilita las comparaciones posteriores."),
    )
    if st.button(T("Save to History", "Guardar en Historial"), icon=":material/save:", width="stretch"):
        rid = bench_service.save(
            services.BenchCapture(block=block, detected_kind=kind),
            note=note,
        )
        st.success(T(f"Run #{rid} saved to History.", f"Corrida #{rid} guardada en Historial."))
        st.page_link("pages/5_History.py", label=T("Open History", "Abrir Historial"), icon=":material/history:")
