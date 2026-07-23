"""Simulate a complete vehicle in OpenRocket."""
import sys
from pathlib import Path

import streamlit as st

CORE = Path(__file__).resolve().parent.parent / "core"
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CORE))

from adapters import openrocket  # noqa: E402
import store  # noqa: E402
import ui  # noqa: E402

st.set_page_config(
    page_title="Flight | Rocketry Console",
    page_icon=":material/rocket_launch:",
    layout="wide",
    initial_sidebar_state="auto",
)
ui.setup_page("Flight")
ui.page_header(
    "Six-degree flight model",
    "Flight",
    "Pair a motor curve with an airframe architecture, define the fins and evaluate the complete trajectory in OpenRocket.",
)

eng_dir = REPO_ROOT / "simulation" / "internal-ballistics"
eng_files = sorted(eng_dir.glob("*.eng"))
eng_names = [path.name for path in eng_files]

st.html(
    """
    <div class="rc-step-strip">
      <div class="rc-step-card"><span class="rc-flow-index">01</span><strong>Select architecture</strong><p>Choose whether the motor tube is structural or installed inside a separate airframe.</p></div>
      <div class="rc-step-card"><span class="rc-flow-index">02</span><strong>Define fins</strong><p>Enter the real trapezoidal fin geometry and expected launch wind.</p></div>
      <div class="rc-step-card"><span class="rc-flow-index">03</span><strong>Check margins</strong><p>Review apogee, rail speed, maximum velocity and stability through burnout.</p></div>
    </div>
    """
)

if not eng_names:
    st.error(
        f"No `.eng` motor curves were found in `{eng_dir}`. Export a motor curve before running Flight.",
        icon=":material/file_open:",
    )
    st.page_link("pages/3_Motor.py", label="Open Motor", icon=":material/local_fire_department:")
    st.stop()

default_index = eng_names.index("E_sintubo.eng") if "E_sintubo.eng" in eng_names else 0

with st.form("flight_form"):
    st.subheader("Vehicle definition")
    c1, c2 = st.columns([1, 1.25])
    with c1:
        architecture = st.radio(
            "Airframe architecture",
            ["mindia", "separate"],
            format_func=lambda value: "Minimum diameter" if value == "mindia" else "Separate airframe",
            captions=[
                "The aluminium motor tube is part of the airframe. Use a *_sintubo.eng curve.",
                "The motor slides inside a separate fibreglass airframe. Any .eng curve is accepted.",
            ],
        )
        compatible_names = (
            [name for name in eng_names if "sintubo" in Path(name).stem]
            if architecture == "mindia"
            else eng_names
        )
        if not compatible_names:
            st.error("No motor curve is compatible with the selected architecture.")
            eng_name = eng_names[0]
        else:
            compatible_default = (
                compatible_names.index("E_sintubo.eng")
                if "E_sintubo.eng" in compatible_names
                else min(default_index, len(compatible_names) - 1)
            )
            eng_name = st.selectbox(
                "Motor curve",
                compatible_names,
                index=compatible_default,
                help="Minimum-diameter models require hardware-only mass in the motor file.",
            )
        wind = st.slider("Wind speed (m/s)", 0.0, 15.0, 2.0, step=0.5)

    with c2:
        st.markdown("**Trapezoidal fin geometry**")
        f1, f2 = st.columns(2)
        root_mm = f1.number_input("Root chord (mm)", value=55.0, min_value=1.0)
        tip_mm = f2.number_input("Tip chord (mm)", value=25.0, min_value=1.0)
        f3, f4 = st.columns(2)
        height_mm = f3.number_input("Span / height (mm)", value=30.0, min_value=1.0)
        sweep_mm = f4.number_input("Sweep length (mm)", value=30.0, min_value=0.0)
        thickness_mm = st.number_input("Thickness (mm)", value=1.6, min_value=0.1)

        geometry_valid = tip_mm <= root_mm
        if tip_mm > root_mm:
            st.warning("Tip chord is larger than root chord. Confirm that this is intentional.")

    submitted = st.form_submit_button(
        "Simulate flight",
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
    with st.status("Starting OpenRocket", expanded=True) as status:
        st.write("Building the vehicle, starting one isolated JVM and running the flight simulation.")
        try:
            result = openrocket.fly(eng_path, architecture=architecture, fin=fin, wind=wind)
            st.session_state.flight_result = result
            status.update(label="Flight simulation complete", state="complete")
        except openrocket.OpenRocketError as exc:
            st.session_state.flight_result = None
            status.update(label="Flight simulation failed", state="error")
            st.error(str(exc))

result = st.session_state.flight_result

if result is None:
    ui.section_title("Waiting for a vehicle")
    st.info("Select a compatible motor and architecture, then enter the physical fin dimensions.")
    st.stop()

ui.section_title("Flight envelope")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Apogee", f'{result["apogee"]:.0f} m')
m2.metric("Maximum speed", f'{result["vmax"]:.0f} m/s', help=f'Mach {result["mach"]:.2f}')
m3.metric("Stability at launch", f'{result["margin"]:.2f} cal')
m4.metric("Rail exit speed", f'{result["rail"]:.1f} m/s')

detail_left, detail_right = st.columns([1.2, 1])
with detail_left:
    st.subheader("Configuration")
    a, b, c = st.columns(3)
    a.metric("Launch mass", f'{result["mass"]:.0f} g')
    b.metric("Burnout stability", f'{result["margin_bo"]:.2f} cal')
    c.metric("Architecture", "Minimum diameter" if result["architecture"] == "mindia" else "Separate")
    st.caption(f'Motor curve: {Path(result["eng_path"]).name} · Wind: {result["wind"]:.1f} m/s')
with detail_right:
    st.subheader("Model checks")
    if result.get("warn"):
        st.warning(str(result["warn"]), icon=":material/warning:")
    else:
        st.success("OpenRocket returned no simulation warnings.", icon=":material/check_circle:")

with st.container(key="flight-save", border=True):
    st.subheader("Save this flight")
    note = st.text_input("Run note", key="flight_note", placeholder="Example: E_sintubo, baseline fins, 2 m/s wind")
    if st.button("Save to History", icon=":material/save:", width="stretch"):
        rid = store.save_run(
            "FLIGHT",
            {key: value for key, value in result.items() if key != "warn"},
            ["metric", "value"],
            [[key, value] for key, value in result.items() if isinstance(value, (int, float))],
            note=note.strip(),
        )
        st.success(f"Flight #{rid} saved to History.")

st.caption("Simulation results depend on the model inputs and component assumptions. Confirm critical margins with review and test evidence.")
