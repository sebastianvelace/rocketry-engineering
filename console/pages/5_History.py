"""History page: browse every saved run (bench captures, motor sweeps, flight
sims), reopen one to re-plot it, or overlay several runs of the same kind to
compare them directly. This is what makes the console a single place instead
of a set of disconnected panels."""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
import blocks  # noqa: E402
import plots  # noqa: E402
import store  # noqa: E402

st.set_page_config(page_title="History — Rocketry Console", layout="wide")
st.title("Run history")
st.caption("Every saved bench capture, motor sweep, and flight simulation, in one place.")

all_runs = store.list_runs()

if not all_runs:
    st.info("No runs saved yet. Capture something on the Bench, Motor, or Flight pages first.")
    st.stop()

kinds = sorted({r.kind for r in all_runs})
kind_filter = st.multiselect("Filter by kind", kinds, default=kinds)

filtered = [r for r in all_runs if r.kind in kind_filter]

st.markdown(f"**{len(filtered)}** of {len(all_runs)} runs shown.")

table_data = [
    {"id": r.id, "created_at": r.created_at, "kind": r.kind, "note": r.note}
    for r in filtered
]
st.dataframe(pd.DataFrame(table_data), use_container_width=True, height=250)

st.divider()

tab_view, tab_compare, tab_manage = st.tabs(["View one run", "Compare runs", "Manage"])

with tab_view:
    ids = [r.id for r in filtered]
    if ids:
        selected_id = st.selectbox("Run id", ids, key="view_id")
        run = store.get_run(selected_id)
        st.markdown(f"**#{run.id}** · {run.kind} · {run.created_at}")
        if run.note:
            st.caption(f"Note: {run.note}")
        st.json(run.meta)

        if run.kind in ("MOTOR_SWEEP",):
            df = pd.DataFrame(run.rows, columns=run.columns)
            st.dataframe(df, use_container_width=True)
        elif run.kind == "FLIGHT":
            df = pd.DataFrame(run.rows, columns=run.columns)
            st.table(df)
        else:
            try:
                block = blocks.Block.from_run(run)
                fig, stats = plots.plot_block(block)
                st.plotly_chart(fig, use_container_width=True)
                if stats:
                    # Same fix as 1_Bench.py: stats mixes floats and strings,
                    # which breaks Arrow serialization unless stringified.
                    st.table({"value": {k: str(v) for k, v in stats.items()}})
            except Exception as e:
                st.warning(f"Could not render this run as a plot: {e}")
                st.dataframe(pd.DataFrame(run.rows, columns=run.columns or None))

        csv = pd.DataFrame(run.rows, columns=run.columns or None).to_csv(index=False)
        st.download_button("Download as CSV", csv, file_name=f"run_{run.id}_{run.kind}.csv")

with tab_compare:
    st.caption("Pick two or more runs of the *same kind* to overlay on one chart.")
    compare_kind = st.selectbox("Kind to compare", sorted({r.kind for r in filtered}))
    same_kind = [r for r in filtered if r.kind == compare_kind]
    labels = {f"#{r.id} ({r.created_at[:19]}) {r.note}".strip(): r.id for r in same_kind}
    picked = st.multiselect("Runs", list(labels.keys()))

    if len(picked) >= 2:
        fig = go.Figure()
        for label in picked:
            run = store.get_run(labels[label])
            if len(run.rows) < 1 or len(run.rows[0]) < 2:
                continue
            # Some firmwares (e.g. main.cpp's sine capture) emit no CSV header,
            # so run.columns can be empty -- fall back to positional indexing
            # rather than assuming named columns exist (this bug was caught
            # while verifying this page).
            x = [row[0] for row in run.rows]
            y = [row[1] for row in run.rows]
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=label))
        x_label = same_kind[0].columns[0] if same_kind[0].columns else "x"
        y_label = same_kind[0].columns[1] if len(same_kind[0].columns) > 1 else "y"
        fig.update_layout(title=f"Overlay — {compare_kind}", xaxis_title=x_label, yaxis_title=y_label)
        st.plotly_chart(fig, use_container_width=True)
    elif picked:
        st.info("Pick at least 2 runs to overlay them.")

with tab_manage:
    st.caption("Delete runs you no longer need.")
    del_id = st.selectbox("Run id to delete", [r.id for r in filtered], key="del_id")
    if st.button("Delete run", type="secondary"):
        store.delete_run(del_id)
        st.success(f"Deleted run #{del_id}. Refresh the page to update the list.")
