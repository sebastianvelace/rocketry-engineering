"""Explore viable BATES grain geometries with openMotor."""
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

CORE = Path(__file__).resolve().parent.parent / "core"
sys.path.insert(0, str(CORE))

from adapters import openmotor  # noqa: E402
import store  # noqa: E402
import ui  # noqa: E402

st.set_page_config(
    page_title="Motor | Rocketry Console",
    page_icon=":material/local_fire_department:",
    layout="wide",
    initial_sidebar_state="auto",
)
ui.setup_page("Motor")
T = ui.tr
ui.page_header(
    T("Internal ballistics", "Balística interna"),
    "Motor",
    T(
        "Define a bounded BATES grain search, run openMotor and review only the configurations that pass every engineering gate.",
        "Define una búsqueda acotada de granos BATES, ejecuta openMotor y revisa solo las configuraciones que superan todos los límites.",
    ),
)

st.html(
    f"""
    <div class="rc-step-strip">
      <div class="rc-step-card"><span class="rc-flow-index">01</span><strong>{T("Bound the search", "Acota la búsqueda")}</strong><p>{T("Choose practical core diameters, segment counts and grain lengths.", "Elige diámetros de núcleo, cantidades de segmentos y longitudes prácticas.")}</p></div>
      <div class="rc-step-card"><span class="rc-flow-index">02</span><strong>{T("Simulate", "Simula")}</strong><p>{T("Each combination runs through the existing openMotor physics model.", "Cada combinación se ejecuta con el modelo físico existente de openMotor.")}</p></div>
      <div class="rc-step-card"><span class="rc-flow-index">03</span><strong>{T("Evaluate", "Evalúa")}</strong><p>{T("Review impulse, burn time, pressure and flow margins before saving.", "Revisa impulso, tiempo de quemado, presión y márgenes de flujo antes de guardar.")}</p></div>
    </div>
    """
)

with st.form("sweep_form"):
    st.subheader(T("Search envelope", "Espacio de búsqueda"))
    c1, c2, c3 = st.columns(3)
    with c1:
        core_lo, core_hi = st.slider(
            T("Core diameter (mm)", "Diámetro del núcleo (mm)"),
            8,
            20,
            (12, 14),
            help=T("Both range endpoints are included.", "Se incluyen ambos extremos del rango."),
        )
    with c2:
        seg_counts = st.multiselect(
            T("Segment count", "Cantidad de segmentos"),
            [2, 3, 4, 5, 6],
            default=[4, 5],
            help=T("Every selected count is evaluated.", "Se evalúa cada cantidad seleccionada."),
        )
    with c3:
        len_lo, len_hi = st.slider(
            T("Segment length (mm)", "Longitud del segmento (mm)"),
            20,
            70,
            (45, 55),
            help=T("Both range endpoints are included when they align with the step.", "Se incluyen ambos extremos cuando coinciden con el paso."),
        )

    with st.expander(T("Advanced constraints", "Restricciones avanzadas")):
        c4, c5, c6 = st.columns(3)
        with c4:
            len_step = st.number_input(T("Length step (mm)", "Paso de longitud (mm)"), value=5, min_value=1, max_value=25)
        with c5:
            max_total = st.number_input(T("Maximum grain stack (mm)", "Longitud máxima del conjunto (mm)"), value=320, min_value=50, max_value=1000)
        with c6:
            target_kn = st.number_input(T("Target peak Kn", "Kn pico objetivo"), value=280.0, min_value=1.0, step=10.0)

    n_core = core_hi - core_lo + 1
    n_len = max(1, (len_hi - len_lo) // max(1, int(len_step)) + 1)
    n_combos = n_core * len(seg_counts) * n_len
    estimated_seconds = n_combos * 0.4

    if not seg_counts:
        st.warning(T("Select at least one segment count.", "Selecciona al menos una cantidad de segmentos."))
    elif n_combos > 80:
        st.warning(T(
            f"{n_combos} combinations. Estimated runtime is roughly {estimated_seconds / 60:.1f} minutes.",
            f"{n_combos} combinaciones. El tiempo estimado es de aproximadamente {estimated_seconds / 60:.1f} minutos.",
        ))
    else:
        st.caption(T(
            f"{n_combos} combinations. Estimated runtime is roughly {max(1, round(estimated_seconds))} seconds.",
            f"{n_combos} combinaciones. El tiempo estimado es de aproximadamente {max(1, round(estimated_seconds))} segundos.",
        ))

    submitted = st.form_submit_button(
        T("Run motor sweep", "Ejecutar barrido de motor"),
        type="primary",
        icon=":material/play_arrow:",
        disabled=not seg_counts,
        width="stretch",
    )

if "sweep_result" not in st.session_state:
    st.session_state.sweep_result = None

if submitted:
    params = {
        "core_range_mm": [core_lo, core_hi],
        "seg_counts": seg_counts,
        "seg_len_range_mm": [len_lo, len_hi, int(len_step)],
        "max_total_mm": int(max_total),
        "target_peak_kn": float(target_kn),
    }
    with st.status(T("Running openMotor sweep", "Ejecutando barrido en openMotor"), expanded=True) as status:
        st.write(T(
            f"Evaluating {n_combos} candidate geometries in an isolated subprocess.",
            f"Evaluando {n_combos} geometrías candidatas en un subproceso aislado.",
        ))
        try:
            result = openmotor.run_sweep(params)
            st.session_state.sweep_result = result
            status.update(label=T("Motor sweep complete", "Barrido de motor completado"), state="complete")
        except openmotor.OpenMotorError as exc:
            st.session_state.sweep_result = None
            status.update(label=T("Motor sweep failed", "El barrido de motor falló"), state="error")
            st.error(str(exc))

result = st.session_state.sweep_result

if result is None:
    ui.section_title(T("Waiting for a search", "Esperando una búsqueda"))
    st.info(T(
        "Start with the compact default envelope. Widen one dimension at a time after confirming runtime and viable results.",
        "Empieza con el espacio compacto predeterminado. Amplía una dimensión a la vez después de confirmar el tiempo y los resultados viables.",
    ))
    st.stop()

ui.section_title(T("Sweep outcome", "Resultado del barrido"))
m1, m2, m3, m4 = st.columns(4)
m1.metric(T("Tube ID", "DI del tubo"), f'{result["tube_id_mm"]} mm')
m2.metric(T("Grain OD", "DE del grano"), f'{result["grain_od_mm"]} mm')
m3.metric(T("Viable", "Viables"), result["n_viable"])
m4.metric(T("Target peak Kn", "Kn pico objetivo"), result["target_peak_kn"])

rejected = result.get("rejected", {})
if rejected:
    gate_names = {
        "kn": "Kn",
        "port": T("Port ratio", "Relación del puerto"),
        "flux": T("Mass flux", "Flujo másico"),
        "mach": "Mach",
        "pressure": T("Pressure", "Presión"),
    }
    rejection_df = pd.DataFrame(
        {"gate": [gate_names.get(key, key) for key in rejected], "candidates": list(rejected.values())}
    )
    reject_fig = px.bar(
        rejection_df,
        x="candidates",
        y="gate",
        orientation="h",
        title=T("Rejected candidates by first failed gate", "Candidatos rechazados por el primer límite fallido"),
        labels={"candidates": T("Candidates", "Candidatos"), "gate": T("Gate", "Límite")},
        color_discrete_sequence=["#ef4444"],
    )
    ui.style_plotly(reject_fig, height=310)
    st.plotly_chart(reject_fig, width="stretch", config={"displaylogo": False})

if not result["rows"]:
    st.warning(
        T(
            "No configuration passed all gates. Widen the geometry envelope deliberately or revisit the target Kn; do not bypass a gate.",
            "Ninguna configuración superó todos los límites. Amplía el espacio deliberadamente o revisa el Kn objetivo; no ignores un límite.",
        ),
        icon=":material/warning:",
    )
    st.stop()

df = pd.DataFrame(result["rows"])
best = df.iloc[0]
st.subheader(T("Highest-impulse viable candidate", "Candidato viable con mayor impulso"))
a, b, c, d = st.columns(4)
a.metric(T("Designation", "Designación"), best["designation"])
b.metric(T("Impulse", "Impulso"), f'{best["impulse_ns"]:.2f} N·s')
c.metric(T("Burn time", "Tiempo de quemado"), f'{best["burn_time_s"]:.3f} s')
d.metric(T("Peak pressure", "Presión pico"), f'{best["peak_pressure_mpa"]:.3f} MPa')

tab_map, tab_table = st.tabs([
    T(":material/scatter_plot: Trade space", ":material/scatter_plot: Espacio de soluciones"),
    T(":material/table_view: All viable configurations", ":material/table_view: Todas las configuraciones viables"),
])
with tab_map:
    fig = px.scatter(
        df,
        x="burn_time_s",
        y="impulse_ns",
        color="n_segments",
        size="peak_thrust_n",
        hover_data=["designation", "core_mm", "port_throat_ratio", "peak_pressure_mpa"],
        title=T("Impulse and burn-time trade space", "Relación entre impulso y tiempo de quemado"),
        labels={
            "burn_time_s": T("Burn time (s)", "Tiempo de quemado (s)"),
            "impulse_ns": T("Impulse (N·s)", "Impulso (N·s)"),
            "n_segments": T("Segments", "Segmentos"),
            "peak_thrust_n": T("Peak thrust (N)", "Empuje pico (N)"),
        },
        color_continuous_scale=["#601818", "#ef4444", "#fecaca"],
    )
    ui.style_plotly(fig, height=520)
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
with tab_table:
    column_labels = {
        "core_mm": T("Core (mm)", "Núcleo (mm)"),
        "n_segments": T("Segments", "Segmentos"),
        "segment_len_mm": T("Segment length (mm)", "Longitud del segmento (mm)"),
        "total_len_mm": T("Total length (mm)", "Longitud total (mm)"),
        "throat_mm": T("Throat (mm)", "Garganta (mm)"),
        "exit_mm": T("Exit (mm)", "Salida (mm)"),
        "kn_peak": T("Peak Kn", "Kn pico"),
        "kn_avg": T("Average Kn", "Kn promedio"),
        "kn_initial": T("Initial Kn", "Kn inicial"),
        "peak_pressure_mpa": T("Peak pressure (MPa)", "Presión pico (MPa)"),
        "peak_thrust_n": T("Peak thrust (N)", "Empuje pico (N)"),
        "avg_force_n": T("Average thrust (N)", "Empuje promedio (N)"),
        "impulse_ns": T("Impulse (N·s)", "Impulso (N·s)"),
        "burn_time_s": T("Burn time (s)", "Tiempo de quemado (s)"),
        "designation": T("Designation", "Designación"),
        "propellant_mass_g": T("Propellant mass (g)", "Masa de propelente (g)"),
        "port_throat_ratio": T("Port/throat ratio", "Relación puerto/garganta"),
        "peak_mass_flux": T("Peak mass flux", "Flujo másico pico"),
        "mass_flux_pct_limit": T("Mass-flux limit (%)", "Límite de flujo másico (%)"),
    }
    st.dataframe(
        df,
        width="stretch",
        height=410,
        hide_index=True,
        column_config={
            **{key: st.column_config.Column(label) for key, label in column_labels.items()},
            "impulse_ns": st.column_config.NumberColumn(column_labels["impulse_ns"], format="%.2f"),
            "burn_time_s": st.column_config.NumberColumn(column_labels["burn_time_s"], format="%.3f"),
            "peak_pressure_mpa": st.column_config.NumberColumn(column_labels["peak_pressure_mpa"], format="%.3f"),
        },
    )

with st.container(key="motor-save", border=True):
    st.subheader(T("Save this sweep", "Guardar este barrido"))
    note = st.text_input(T("Run note", "Nota de la corrida"), key="motor_note", placeholder=T("Example: baseline E-class envelope", "Ejemplo: espacio base clase E"))
    if st.button(T("Save to History", "Guardar en Historial"), icon=":material/save:", width="stretch"):
        rid = store.save_run(
            "MOTOR_SWEEP",
            {key: value for key, value in result.items() if key != "rows"},
            list(df.columns),
            df.values.tolist(),
            note=note.strip(),
        )
        st.success(T(f"Motor sweep #{rid} saved to History.", f"Barrido de motor #{rid} guardado en Historial."))

st.caption(T(
    "Viable means the candidate passed the encoded model gates. It is not a manufacturing or firing authorization.",
    "Viable significa que el candidato superó los límites codificados del modelo. No es una autorización de fabricación ni de encendido.",
))
