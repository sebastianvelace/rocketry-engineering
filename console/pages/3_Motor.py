"""Motor page: run a BATES grain sweep in openMotor (via subprocess adapter)
and browse the viable configurations."""
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from adapters import openmotor  # noqa: E402
import store  # noqa: E402

st.set_page_config(page_title="Motor — Rocketry Console", layout="wide")
st.title("Motor sweep (openMotor)")
st.caption("Headless BATES grain sweep, same physics and safety gates as simulation/internal-ballistics/sweep_bates.py.")

with st.form("sweep_form"):
    st.caption(
        "Each combination runs a full internal-ballistics simulation (~0.3-0.5s each). "
        "Start small (defaults below run in a few seconds) and widen the ranges once "
        "you know how long your grid takes."
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        # Small defaults on purpose: the full 9-17mm x all-segment-counts x
        # 25-60mm grid (~200 combinations) was clocked at over 240s end to
        # end, well past a comfortable wait and past the adapter's old 120s
        # timeout -- caught by actually running it once from this page.
        core_lo, core_hi = st.slider("Core diameter range (mm)", 8, 20, (12, 14))
    with c2:
        seg_counts = st.multiselect("Segment counts", [2, 3, 4, 5, 6], default=[4, 5])
    with c3:
        len_lo, len_hi = st.slider("Segment length range (mm)", 20, 70, (45, 55))

    c4, c5 = st.columns(2)
    with c4:
        len_step = st.number_input("Segment length step (mm)", value=5, min_value=1)
    with c5:
        max_total = st.number_input("Max total grain length (mm)", value=320, min_value=50)

    target_kn = st.number_input("Target peak Kn", value=280.0, step=10.0)

    n_core = core_hi - core_lo
    n_len = max(1, (len_hi - len_lo) // max(1, int(len_step)) + 1)
    n_combos = n_core * max(1, len(seg_counts)) * n_len
    if n_combos > 80:
        st.warning(
            f"~{n_combos} combinations in this grid. Large grids can take several "
            "minutes -- consider narrowing the ranges if this is your first run."
        )
    else:
        st.caption(f"~{n_combos} combinations in this grid.")

    submitted = st.form_submit_button("Run sweep", type="primary")

if "sweep_result" not in st.session_state:
    st.session_state.sweep_result = None

if submitted:
    params = {
        "core_range_mm": [core_lo, core_hi],
        "seg_counts": seg_counts or [4],
        "seg_len_range_mm": [len_lo, len_hi, int(len_step)],
        "max_total_mm": int(max_total),
        "target_peak_kn": target_kn,
    }
    with st.spinner("Running sweep in openMotor (subprocess) ..."):
        try:
            result = openmotor.run_sweep(params)
            st.session_state.sweep_result = result
        except openmotor.OpenMotorError as e:
            st.error(f"Sweep failed: {e}")
            st.session_state.sweep_result = None

result = st.session_state.sweep_result

if result is not None:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tube ID (mm)", result["tube_id_mm"])
    m2.metric("Grain OD (mm)", result["grain_od_mm"])
    m3.metric("Viable configs", result["n_viable"])
    m4.metric("Target peak Kn", result["target_peak_kn"])

    st.caption(f"Rejected: {result['rejected']}")

    if result["rows"]:
        df = pd.DataFrame(result["rows"])
        st.dataframe(df, use_container_width=True, height=350)

        fig = px.scatter(
            df, x="burn_time_s", y="impulse_ns", color="n_segments",
            size="peak_thrust_n", hover_data=["designation", "core_mm", "port_throat_ratio"],
            title="Impulse vs. burn time (color = segments, size = peak thrust)",
        )
        st.plotly_chart(fig, use_container_width=True)

        note = st.text_input("Note for this sweep", key="motor_note")
        if st.button("Save sweep to history"):
            rid = store.save_run(
                "MOTOR_SWEEP",
                {k: v for k, v in result.items() if k != "rows"},
                list(df.columns),
                df.values.tolist(),
                note=note,
            )
            st.success(f"Saved as run #{rid}.")
    else:
        st.warning("No viable configurations under these constraints.")
else:
    st.info("Set the sweep parameters and click **Run sweep**.")
