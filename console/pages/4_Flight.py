"""Simulate a complete vehicle in OpenRocket."""
import sys
from pathlib import Path

import streamlit as st

CORE = Path(__file__).resolve().parent.parent / "core"
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CORE))

import services  # noqa: E402
import ui  # noqa: E402

st.set_page_config(
    page_title="Flight | Rocketry Console",
    page_icon=":material/rocket_launch:",
    layout="wide",
    initial_sidebar_state="auto",
)
ui.setup_page("Flight")
T = ui.tr
flight_service = services.FlightService()
ui.page_header(
    T("Six-degree flight model", "Modelo de vuelo de seis grados"),
    T("Flight", "Vuelo"),
    T(
        "Pair a motor curve with an airframe architecture, define the fins and evaluate the complete trajectory in OpenRocket.",
        "Combina una curva de motor con una arquitectura, define las aletas y evalúa la trayectoria completa en OpenRocket.",
    ),
)

eng_dir = REPO_ROOT / "simulation" / "internal-ballistics"
eng_files = sorted(eng_dir.glob("*.eng"))
eng_names = [path.name for path in eng_files]

st.html(
    f"""
    <div class="rc-step-strip">
      <div class="rc-step-card"><span class="rc-flow-index">01</span><strong>{T("Select architecture", "Selecciona la arquitectura")}</strong><p>{T("Choose whether the motor tube is structural or installed inside a separate airframe.", "Elige si el tubo motor es estructural o va dentro de un fuselaje independiente.")}</p></div>
      <div class="rc-step-card"><span class="rc-flow-index">02</span><strong>{T("Define fins", "Define las aletas")}</strong><p>{T("Enter the real trapezoidal fin geometry and expected launch wind.", "Ingresa la geometría trapezoidal real y el viento esperado en el lanzamiento.")}</p></div>
      <div class="rc-step-card"><span class="rc-flow-index">03</span><strong>{T("Check margins", "Revisa los márgenes")}</strong><p>{T("Review apogee, rail speed, maximum velocity and stability through burnout.", "Revisa apogeo, velocidad de salida del riel, velocidad máxima y estabilidad hasta burnout.")}</p></div>
    </div>
    """
)

if not eng_names:
    st.error(
        T(
            f"No `.eng` motor curves were found in `{eng_dir}`. Export a motor curve before running Flight.",
            f"No se encontraron curvas de motor `.eng` en `{eng_dir}`. Exporta una curva antes de ejecutar Vuelo.",
        ),
        icon=":material/file_open:",
    )
    st.page_link("pages/3_Motor.py", label=T("Open Motor", "Abrir Motor"), icon=":material/local_fire_department:")
    st.stop()

default_index = eng_names.index("E_sintubo.eng") if "E_sintubo.eng" in eng_names else 0

with st.form("flight_form"):
    st.subheader(T("Vehicle definition", "Definición del vehículo"))
    c1, c2 = st.columns([1, 1.25])
    with c1:
        architecture = st.radio(
            T("Airframe architecture", "Arquitectura del fuselaje"),
            ["mindia", "separate"],
            format_func=lambda value: T("Minimum diameter", "Diámetro mínimo") if value == "mindia" else T("Separate airframe", "Fuselaje independiente"),
            captions=[
                T("The aluminium motor tube is part of the airframe. Use a *_sintubo.eng curve.", "El tubo motor de aluminio forma parte del fuselaje. Usa una curva *_sintubo.eng."),
                T("The motor slides inside a separate fibreglass airframe. Any .eng curve is accepted.", "El motor entra en un fuselaje independiente de fibra de vidrio. Se acepta cualquier curva .eng."),
            ],
        )
        compatible_names = (
            [name for name in eng_names if "sintubo" in Path(name).stem]
            if architecture == "mindia"
            else eng_names
        )
        if not compatible_names:
            st.error(T("No motor curve is compatible with the selected architecture.", "Ninguna curva de motor es compatible con la arquitectura seleccionada."))
            eng_name = eng_names[0]
        else:
            compatible_default = (
                compatible_names.index("E_sintubo.eng")
                if "E_sintubo.eng" in compatible_names
                else min(default_index, len(compatible_names) - 1)
            )
            eng_name = st.selectbox(
                T("Motor curve", "Curva de motor"),
                compatible_names,
                index=compatible_default,
                help=T("Minimum-diameter models require hardware-only mass in the motor file.", "Los modelos de diámetro mínimo requieren que el archivo contenga solo la masa del hardware."),
            )
        wind = st.slider(T("Wind speed (m/s)", "Velocidad del viento (m/s)"), 0.0, 15.0, 2.0, step=0.5)

    with c2:
        st.markdown(T("**Trapezoidal fin geometry**", "**Geometría trapezoidal de las aletas**"))
        f1, f2 = st.columns(2)
        root_mm = f1.number_input(T("Root chord (mm)", "Cuerda de raíz (mm)"), value=55.0, min_value=1.0)
        tip_mm = f2.number_input(T("Tip chord (mm)", "Cuerda de punta (mm)"), value=25.0, min_value=1.0)
        f3, f4 = st.columns(2)
        height_mm = f3.number_input(T("Span / height (mm)", "Envergadura / altura (mm)"), value=30.0, min_value=1.0)
        sweep_mm = f4.number_input(T("Sweep length (mm)", "Longitud de barrido (mm)"), value=30.0, min_value=0.0)
        thickness_mm = st.number_input(T("Thickness (mm)", "Espesor (mm)"), value=1.6, min_value=0.1)

        geometry_valid = tip_mm <= root_mm
        if tip_mm > root_mm:
            st.warning(T("Tip chord is larger than root chord. Confirm that this is intentional.", "La cuerda de punta es mayor que la cuerda de raíz. Confirma que sea intencional."))

    submitted = st.form_submit_button(
        T("Simulate flight", "Simular vuelo"),
        type="primary",
        icon=":material/rocket_launch:",
        disabled=not compatible_names or not geometry_valid,
        width="stretch",
    )

if "flight_result" not in st.session_state:
    st.session_state.flight_result = None

if submitted:
    eng_path = str(eng_dir / eng_name)
    fin = {
        "root": root_mm / 1000,
        "tip": tip_mm / 1000,
        "height": height_mm / 1000,
        "sweep": sweep_mm / 1000,
        "thickness": thickness_mm / 1000,
    }
    with st.status(T("Starting OpenRocket", "Iniciando OpenRocket"), expanded=True) as status:
        st.write(T(
            "Building the vehicle, starting one isolated JVM and running the flight simulation.",
            "Construyendo el vehículo, iniciando una JVM aislada y ejecutando la simulación de vuelo.",
        ))
        try:
            result = flight_service.run(
                eng_path,
                architecture=architecture,
                fin=fin,
                wind=wind,
            )
            st.session_state.flight_result = result
            status.update(label=T("Flight simulation complete", "Simulación de vuelo completada"), state="complete")
        except services.ServiceError as exc:
            st.session_state.flight_result = None
            status.update(label=T("Flight simulation failed", "La simulación de vuelo falló"), state="error")
            st.error(str(exc))

result = st.session_state.flight_result

if result is None:
    ui.section_title(T("Waiting for a vehicle", "Esperando un vehículo"))
    st.info(T("Select a compatible motor and architecture, then enter the physical fin dimensions.", "Selecciona un motor y una arquitectura compatibles, luego ingresa las dimensiones físicas de las aletas."))
    st.stop()

ui.section_title(T("Flight envelope", "Envolvente de vuelo"))
m1, m2, m3, m4 = st.columns(4)
m1.metric(T("Apogee", "Apogeo"), f'{result["apogee"]:.0f} m')
m2.metric(T("Maximum speed", "Velocidad máxima"), f'{result["vmax"]:.0f} m/s', help=f'Mach {result["mach"]:.2f}')
m3.metric(T("Stability at launch", "Estabilidad al lanzamiento"), f'{result["margin"]:.2f} cal')
m4.metric(T("Rail exit speed", "Velocidad de salida del riel"), f'{result["rail"]:.1f} m/s')

detail_left, detail_right = st.columns([1.2, 1])
with detail_left:
    st.subheader(T("Configuration", "Configuración"))
    a, b, c = st.columns(3)
    a.metric(T("Launch mass", "Masa de lanzamiento"), f'{result["mass"]:.0f} g')
    b.metric(T("Burnout stability", "Estabilidad en burnout"), f'{result["margin_bo"]:.2f} cal')
    c.metric(T("Architecture", "Arquitectura"), T("Minimum diameter", "Diámetro mínimo") if result["architecture"] == "mindia" else T("Separate", "Independiente"))
    st.caption(T("Motor curve", "Curva de motor") + f': {Path(result["eng_path"]).name} · ' + T("Wind", "Viento") + f': {result["wind"]:.1f} m/s')
with detail_right:
    st.subheader(T("Model checks", "Verificaciones del modelo"))
    if result.get("warn"):
        st.warning(str(result["warn"]), icon=":material/warning:")
    else:
        st.success(T("OpenRocket returned no simulation warnings.", "OpenRocket no devolvió advertencias de simulación."), icon=":material/check_circle:")

with st.container(key="flight-save"):
    st.subheader(T("Save this flight", "Guardar este vuelo"))
    note = st.text_input(T("Run note", "Nota de la corrida"), key="flight_note", placeholder=T("Example: E_sintubo, baseline fins, 2 m/s wind", "Ejemplo: E_sintubo, aletas base, viento de 2 m/s"))
    if st.button(T("Save to History", "Guardar en Historial"), icon=":material/save:", width="stretch"):
        rid = flight_service.save(result, note=note)
        st.success(T(f"Flight #{rid} saved to History.", f"Vuelo #{rid} guardado en Historial."))

st.caption(T(
    "Simulation results depend on the model inputs and component assumptions. Confirm critical margins with review and test evidence.",
    "Los resultados dependen de las entradas y supuestos del modelo. Confirma los márgenes críticos con revisión y evidencia de pruebas.",
))
