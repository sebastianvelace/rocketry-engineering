"""Flight page: simulate a rocket design in OpenRocket (via subprocess
adapter) using one of the project's exported .eng motor curves."""
import glob
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from adapters import openrocket  # noqa: E402
import store  # noqa: E402

st.set_page_config(page_title="Flight — Rocketry Console", layout="wide")
st.title("Flight simulation (OpenRocket)")
st.caption("Runs simulation/flight/architecture.py's design_mindia/design_separate + fly() unmodified.")

eng_dir = Path.home() / "rocketry-portfolio" / "simulation" / "internal-ballistics"
eng_files = sorted(glob.glob(str(eng_dir / "*.eng")))
eng_names = [Path(p).name for p in eng_files]

with st.form("flight_form"):
    c1, c2 = st.columns(2)
    with c1:
        eng_name = st.selectbox("Motor (.eng)", eng_names,
                                 index=eng_names.index("E_sintubo.eng") if "E_sintubo.eng" in eng_names else 0)
        architecture = st.radio(
            "Airframe architecture", ["mindia", "separate"],
            captions=["Aluminium motor tube IS the airframe (needs a *_sintubo.eng)",
                      "Motor slides inside a separate fibreglass tube (any .eng)"],
        )
    with c2:
        wind = st.slider("Wind speed (m/s)", 0.0, 15.0, 2.0, step=0.5)
        st.markdown("**Fins**")
        f1, f2 = st.columns(2)
        root = f1.number_input("Root (mm)", value=55.0) / 1000
        tip = f2.number_input("Tip (mm)", value=25.0) / 1000
        f3, f4 = st.columns(2)
        height = f3.number_input("Height (mm)", value=30.0) / 1000
        sweep = f4.number_input("Sweep (mm)", value=30.0) / 1000
        thickness = st.number_input("Thickness (mm)", value=1.6) / 1000

    submitted = st.form_submit_button("Fly", type="primary")

if "flight_result" not in st.session_state:
    st.session_state.flight_result = None

if submitted:
    eng_path = str(eng_dir / eng_name)
    fin = {"root": root, "tip": tip, "height": height, "sweep": sweep, "thickness": thickness}
    with st.spinner("Starting JVM and simulating in OpenRocket ..."):
        try:
            result = openrocket.fly(eng_path, architecture=architecture, fin=fin, wind=wind)
            st.session_state.flight_result = result
        except openrocket.OpenRocketError as e:
            st.error(f"Simulation failed: {e}")
            st.session_state.flight_result = None

result = st.session_state.flight_result

if result is not None:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Apogee (m)", round(result["apogee"], 0))
    m2.metric("Max speed (m/s)", round(result["vmax"], 0), help=f"Mach {result['mach']:.2f}")
    m3.metric("Stability margin (cal)", round(result["margin"], 2))
    m4.metric("Rail exit (m/s)", round(result["rail"], 1))

    st.caption(
        f"Launch mass: {result['mass']:.0f} g | Burnout margin: {result['margin_bo']:.2f} cal | "
        f"Architecture: {result['architecture']} | Motor: {Path(result['eng_path']).name}"
    )

    if result["warn"]:
        st.warning(f"Simulation warnings: {result['warn']}")
    else:
        st.success("No simulation warnings.")

    note = st.text_input("Note for this flight", key="flight_note")
    if st.button("Save flight to history"):
        rid = store.save_run(
            "FLIGHT",
            {k: v for k, v in result.items() if k != "warn"},
            ["metric", "value"],
            [[k, v] for k, v in result.items() if isinstance(v, (int, float))],
            note=note,
        )
        st.success(f"Saved as run #{rid}.")
else:
    st.info("Pick a motor and architecture, then click **Fly**.")
