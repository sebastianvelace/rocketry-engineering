"""Browse, reopen, compare, export and manage saved engineering runs."""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

CORE = Path(__file__).resolve().parent.parent / "core"
sys.path.insert(0, str(CORE))

import blocks  # noqa: E402
import plots  # noqa: E402
import services  # noqa: E402
import store  # noqa: E402
import ui  # noqa: E402

st.set_page_config(
    page_title="History | Rocketry Console",
    page_icon=":material/history:",
    layout="wide",
    initial_sidebar_state="auto",
)
ui.setup_page("History")
T = ui.tr
history_service = services.HistoryService()
ui.page_header(
    T("Run archive", "Archivo de corridas"),
    T("History", "Historial"),
    T(
        "Reopen captured and simulated evidence, compare compatible values and export the underlying rows.",
        "Reabre evidencia capturada y simulada, compara valores compatibles y exporta las filas originales.",
    ),
)


def label_for(run: store.RunRecord) -> str:
    note = f" · {run.note}" if run.note else ""
    return f"#{run.id} · {run.created_at[:19]} · {run.kind}{note}"


def numeric_columns(run: store.RunRecord) -> list[tuple[str, int]]:
    columns = history_service.numeric_columns(run)
    if run.columns or not ui.is_spanish():
        return columns
    return [(name.replace("column_", "columna_"), idx) for name, idx in columns]


def get_or_none(run_id: int) -> store.RunRecord | None:
    try:
        return history_service.get(run_id)
    except services.ServiceError:
        return None


all_runs = history_service.list()

if not all_runs:
    st.info(
        T(
            "History is empty. Save a Bench capture, Motor sweep or Flight result to create the first run.",
            "El Historial está vacío. Guarda una captura del Banco, un barrido de Motor o un resultado de Vuelo para crear la primera corrida.",
        ),
        icon=":material/history:",
    )
    a, b, c = st.columns(3)
    a.page_link("pages/1_Bench.py", label=T("Open Bench", "Abrir banco"), icon=":material/monitor_heart:", width="stretch")
    b.page_link("pages/3_Motor.py", label=T("Open Motor", "Abrir Motor"), icon=":material/local_fire_department:", width="stretch")
    c.page_link("pages/4_Flight.py", label=T("Open Flight", "Abrir Vuelo"), icon=":material/rocket_launch:", width="stretch")
    st.stop()

kinds = sorted({run.kind for run in all_runs})
filter_col, search_col = st.columns([1.2, 1])
with filter_col:
    kind_filter = st.multiselect(T("Measurement type", "Tipo de medición"), kinds, default=kinds)
with search_col:
    note_query = st.text_input(T("Search notes", "Buscar en notas"), placeholder=T("Filter by note text", "Filtrar por texto de la nota"))

filtered = [
    run
    for run in all_runs
    if run.kind in kind_filter and note_query.casefold() in run.note.casefold()
]

shown, total, types = st.columns(3)
shown.metric(T("Runs shown", "Corridas visibles"), len(filtered))
total.metric(T("Total archive", "Total del archivo"), len(all_runs))
types.metric(T("Types", "Tipos"), len({run.kind for run in filtered}))

if not filtered:
    st.warning(T("No run matches the current filters. Clear the note search or select another measurement type.", "Ninguna corrida coincide con los filtros. Borra la búsqueda o selecciona otro tipo de medición."))
    st.stop()

table_data = [
    {
        T("Run", "Corrida"): run.id,
        T("Captured (UTC)", "Capturada (UTC)"): run.created_at,
        T("Type", "Tipo"): run.kind,
        T("Note", "Nota"): run.note or T("No note", "Sin nota"),
    }
    for run in filtered
]
st.dataframe(pd.DataFrame(table_data), width="stretch", height=270, hide_index=True)

tab_view, tab_compare, tab_manage = st.tabs(
    [
        T(":material/visibility: Inspect", ":material/visibility: Inspeccionar"),
        T(":material/compare_arrows: Compare", ":material/compare_arrows: Comparar"),
        T(":material/settings: Manage", ":material/settings: Gestionar"),
    ]
)

with tab_view:
    labels = {label_for(run): run.id for run in filtered}
    selected_label = st.selectbox(T("Run", "Corrida"), list(labels))
    run = get_or_none(labels[selected_label])

    if run is None:
        st.error(T("The selected run no longer exists. Refresh History.", "La corrida seleccionada ya no existe. Actualiza Historial."))
    else:
        meta_col, data_col = st.columns([1, 1.7])
        with meta_col:
            st.subheader(T(f"Run #{run.id}", f"Corrida #{run.id}"))
            st.caption(f"{run.kind} · {run.created_at}")
            if run.note:
                st.write(run.note)
            st.json(run.meta, expanded=False)

            csv = history_service.to_csv(run)
            st.download_button(
                T("Export CSV", "Exportar CSV"),
                csv,
                file_name=f"run_{run.id}_{run.kind}.csv",
                mime="text/csv",
                icon=":material/download:",
                width="stretch",
            )

        with data_col:
            if run.kind == "MOTOR_SWEEP":
                motor_df = pd.DataFrame(run.rows, columns=run.columns)
                if ui.is_spanish():
                    motor_df = motor_df.rename(columns={
                        "core_mm": "núcleo_mm",
                        "n_segments": "segmentos",
                        "segment_len_mm": "longitud_segmento_mm",
                        "total_len_mm": "longitud_total_mm",
                        "peak_pressure_mpa": "presión_pico_mpa",
                        "peak_thrust_n": "empuje_pico_n",
                        "avg_force_n": "empuje_promedio_n",
                        "impulse_ns": "impulso_ns",
                        "burn_time_s": "tiempo_quemado_s",
                        "designation": "designación",
                        "propellant_mass_g": "masa_propelente_g",
                    })
                st.dataframe(motor_df, width="stretch", height=430, hide_index=True)
            elif run.kind == "FLIGHT":
                flight_df = pd.DataFrame(run.rows, columns=run.columns)
                if ui.is_spanish():
                    flight_df = flight_df.rename(columns={"metric": "métrica", "value": "valor"})
                st.dataframe(flight_df, width="stretch", hide_index=True)
            else:
                try:
                    block = blocks.Block.from_run(run)
                    fig, stats = plots.plot_block(block)
                    ui.style_plotly(fig, height=480)
                    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
                    if stats:
                        metric_cols = st.columns(min(3, len(stats)))
                        for idx, (name, value) in enumerate(stats.items()):
                            metric_cols[idx % len(metric_cols)].metric(ui.stat_label(name), ui.stat_value(value))
                except (KeyError, ValueError, IndexError, TypeError) as exc:
                    st.warning(T(f"The original plot cannot be reconstructed: {exc}", f"No se puede reconstruir la gráfica original: {exc}"))
                    st.dataframe(pd.DataFrame(run.rows, columns=run.columns or None), width="stretch")

with tab_compare:
    st.write(T("Choose runs of one type, then select numeric axes that are meaningful for that data.", "Elige corridas de un mismo tipo y selecciona ejes numéricos con significado para esos datos."))
    compare_kind = st.selectbox(T("Type", "Tipo"), sorted({run.kind for run in filtered}), key="compare_kind")
    same_kind = [run for run in filtered if run.kind == compare_kind]
    compare_labels = {label_for(run): run.id for run in same_kind}
    picked = st.multiselect(T("Runs to overlay", "Corridas para superponer"), list(compare_labels), max_selections=6)

    loaded = [get_or_none(compare_labels[label]) for label in picked]
    loaded = [run for run in loaded if run is not None]

    if loaded:
        common_numeric = {
            name: idx for name, idx in numeric_columns(loaded[0])
        }
        for candidate in loaded[1:]:
            candidate_names = {name for name, _ in numeric_columns(candidate)}
            common_numeric = {name: idx for name, idx in common_numeric.items() if name in candidate_names}

        if not common_numeric:
            st.warning(T("The selected runs do not share a numeric column that can be compared.", "Las corridas seleccionadas no comparten una columna numérica comparable."))
        else:
            axis_a, axis_b = st.columns(2)
            names = list(common_numeric)
            with axis_a:
                sample_index = T("Sample index", "Índice de muestra")
                x_choice = st.selectbox(T("Horizontal axis", "Eje horizontal"), [sample_index, *names])
            with axis_b:
                y_default = min(1, len(names) - 1)
                y_choice = st.selectbox(T("Vertical axis", "Eje vertical"), names, index=y_default)

            if len(loaded) < 2:
                st.info(T("Select at least two runs to create an overlay.", "Selecciona al menos dos corridas para crear una superposición."))
            else:
                fig = go.Figure()
                for label, run in zip(picked, loaded):
                    name_to_idx = dict(numeric_columns(run))
                    y_idx = name_to_idx[y_choice]
                    y_values = [row[y_idx] for row in run.rows if len(row) > y_idx]
                    if x_choice == sample_index:
                        x_values = list(range(len(y_values)))
                    else:
                        x_idx = name_to_idx[x_choice]
                        paired = [
                            (row[x_idx], row[y_idx])
                            for row in run.rows
                            if len(row) > max(x_idx, y_idx)
                        ]
                        x_values = [pair[0] for pair in paired]
                        y_values = [pair[1] for pair in paired]
                    fig.add_trace(go.Scatter(x=x_values, y=y_values, mode="lines+markers", name=label))

                fig.update_layout(
                    title=T(f"{compare_kind} comparison", f"Comparación de {compare_kind}"),
                    xaxis_title=x_choice,
                    yaxis_title=y_choice,
                )
                ui.style_plotly(fig, height=540)
                st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
    else:
        st.info(T("Select two or more compatible runs.", "Selecciona dos o más corridas compatibles."))

with tab_manage:
    st.subheader(T("Delete a run", "Eliminar una corrida"))
    st.write(T("Deletion removes the selected run from the local SQLite archive and cannot be undone from the console.", "La eliminación borra la corrida del archivo SQLite local y no puede deshacerse desde la consola."))
    delete_labels = {label_for(run): run.id for run in filtered}
    delete_label = st.selectbox(T("Run to delete", "Corrida que se eliminará"), list(delete_labels), key="delete_run")
    confirm = st.checkbox(T("I understand that this permanently removes the selected run.", "Entiendo que esto elimina la corrida de forma permanente."))
    if st.button(
        T("Delete selected run", "Eliminar corrida seleccionada"),
        type="secondary",
        icon=":material/delete:",
        disabled=not confirm,
    ):
        delete_id = delete_labels[delete_label]
        history_service.delete(delete_id)
        st.success(T(f"Run #{delete_id} deleted.", f"Corrida #{delete_id} eliminada."))
        st.rerun()
