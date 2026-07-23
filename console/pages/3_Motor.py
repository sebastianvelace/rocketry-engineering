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
ui.page_header(
    "Internal ballistics",
    "Motor",
    "Define a bounded BATES grain search, run openMotor and review only the configurations that pass every engineering gate.",
)

st.html(
    """
    <div class="rc-step-strip">
      <div class="rc-step-card"><span class="rc-flow-index">01</span><strong>Bound the search</strong><p>Choose practical core diameters, segment counts and grain lengths.</p></div>
      <div class="rc-step-card"><span class="rc-flow-index">02</span><strong>Simulate</strong><p>Each combination runs through the existing openMotor physics model.</p></div>
      <div class="rc-step-card"><span class="rc-flow-index">03</span><strong>Evaluate</strong><p>Review impulse, burn time, pressure and flow margins before saving.</p></div>
    </div>
    """
)

with st.form("sweep_form"):
    st.subheader("Search envelope")
    c1, c2, c3 = st.columns(3)
    with c1:
        core_lo, core_hi = st.slider(
            "Core diameter (mm)",
            8,
            20,
            (12, 14),
            help="Both range endpoints are included.",
        )
    with c2:
        seg_counts = st.multiselect(
            "Segment count",
            [2, 3, 4, 5, 6],
            default=[4, 5],
            help="Every selected count is evaluated.",
        )
    with c3:
        len_lo, len_hi = st.slider(
            "Segment length (mm)",
            20,
            70,
            (45, 55),
            help="Both range endpoints are included when they align with the step.",
        )

    with st.expander("Advanced constraints"):
        c4, c5, c6 = st.columns(3)
        with c4:
            len_step = st.number_input("Length step (mm)", value=5, min_value=1, max_value=25)
        with c5:
            max_total = st.number_input("Maximum grain stack (mm)", value=320, min_value=50, max_value=1000)
        with c6:
            target_kn = st.number_input("Target peak Kn", value=280.0, min_value=1.0, step=10.0)

    n_core = core_hi - core_lo + 1
    n_len = max(1, (len_hi - len_lo) // max(1, int(len_step)) + 1)
    n_combos = n_core * len(seg_counts) * n_len
    estimated_seconds = n_combos * 0.4

    if not seg_counts:
        st.warning("Select at least one segment count.")
    elif n_combos > 80:
        st.warning(f"{n_combos} combinations. Estimated runtime is roughly {estimated_seconds / 60:.1f} minutes.")
    else:
        st.caption(f"{n_combos} combinations. Estimated runtime is roughly {max(1, round(estimated_seconds))} seconds.")

    submitted = st.form_submit_button(
        "Run motor sweep",
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
    with st.status("Running openMotor sweep", expanded=True) as status:
        st.write(f"Evaluating {n_combos} candidate geometries in an isolated subprocess.")
        try:
            result = openmotor.run_sweep(params)
            st.session_state.sweep_result = result
            status.update(label="Motor sweep complete", state="complete")
        except openmotor.OpenMotorError as exc:
            st.session_state.sweep_result = None
            status.update(label="Motor sweep failed", state="error")
            st.error(str(exc))

result = st.session_state.sweep_result

if result is None:
    ui.section_title("Waiting for a search")
    st.info("Start with the compact default envelope. Widen one dimension at a time after confirming runtime and viable results.")
    st.stop()

ui.section_title("Sweep outcome")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Tube ID", f'{result["tube_id_mm"]} mm')
m2.metric("Grain OD", f'{result["grain_od_mm"]} mm')
m3.metric("Viable", result["n_viable"])
m4.metric("Target peak Kn", result["target_peak_kn"])

rejected = result.get("rejected", {})
if rejected:
    rejection_df = pd.DataFrame(
        {"gate": [key.replace("_", " ").title() for key in rejected], "candidates": list(rejected.values())}
    )
    reject_fig = px.bar(
        rejection_df,
        x="candidates",
        y="gate",
        orientation="h",
        title="Rejected candidates by first failed gate",
        color_discrete_sequence=["#ff6b2c"],
    )
    ui.style_plotly(reject_fig, height=310)
    st.plotly_chart(reject_fig, width="stretch", config={"displaylogo": False})

if not result["rows"]:
    st.warning(
        "No configuration passed all gates. Widen the geometry envelope deliberately or revisit the target Kn; do not bypass a gate.",
        icon=":material/warning:",
    )
    st.stop()

df = pd.DataFrame(result["rows"])
best = df.iloc[0]
st.subheader("Highest-impulse viable candidate")
a, b, c, d = st.columns(4)
a.metric("Designation", best["designation"])
b.metric("Impulse", f'{best["impulse_ns"]:.2f} N·s')
c.metric("Burn time", f'{best["burn_time_s"]:.3f} s')
d.metric("Peak pressure", f'{best["peak_pressure_mpa"]:.3f} MPa')

tab_map, tab_table = st.tabs([":material/scatter_plot: Trade space", ":material/table_view: All viable configurations"])
with tab_map:
    fig = px.scatter(
        df,
        x="burn_time_s",
        y="impulse_ns",
        color="n_segments",
        size="peak_thrust_n",
        hover_data=["designation", "core_mm", "port_throat_ratio", "peak_pressure_mpa"],
        title="Impulse and burn-time trade space",
        labels={
            "burn_time_s": "Burn time (s)",
            "impulse_ns": "Impulse (N·s)",
            "n_segments": "Segments",
            "peak_thrust_n": "Peak thrust (N)",
        },
        color_continuous_scale=["#5c270f", "#ff6b2c", "#ffd1bd"],
    )
    ui.style_plotly(fig, height=520)
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
with tab_table:
    st.dataframe(
        df,
        width="stretch",
        height=410,
        hide_index=True,
        column_config={
            "impulse_ns": st.column_config.NumberColumn("Impulse (N·s)", format="%.2f"),
            "burn_time_s": st.column_config.NumberColumn("Burn time (s)", format="%.3f"),
            "peak_pressure_mpa": st.column_config.NumberColumn("Peak pressure (MPa)", format="%.3f"),
        },
    )

with st.container(key="motor-save", border=True):
    st.subheader("Save this sweep")
    note = st.text_input("Run note", key="motor_note", placeholder="Example: baseline E-class envelope")
    if st.button("Save to History", icon=":material/save:", width="stretch"):
        rid = store.save_run(
            "MOTOR_SWEEP",
            {key: value for key, value in result.items() if key != "rows"},
            list(df.columns),
            df.values.tolist(),
            note=note.strip(),
        )
        st.success(f"Motor sweep #{rid} saved to History.")

st.caption("Viable means the candidate passed the encoded model gates. It is not a manufacturing or firing authorization.")
