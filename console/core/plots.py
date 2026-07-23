"""
One Plotly figure per block "kind", plus the type-detection that picks which
one to use. The math here mirrors the standalone scripts in
avionics/daq-fase1/ exactly (fft_analysis.py, jitter_analysis.py,
step_analysis.py, adc_cal.py, thrust_replay.py) -- this module does not
reinvent the analysis, it re-renders it interactively and keeps it in one
place instead of seven.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from blocks import Block


def detect_kind(block: Block) -> str:
    """Best-effort classification when the firmware's bare token is missing
    or ambiguous (main.cpp sine capture has no token; timing_test uses
    METHOD=timer/soft instead of a bare kind)."""
    if block.kind:
        return block.kind
    if "METHOD" in block.meta:
        return "TIMING"
    if "F_SIGNAL" in block.meta and "F_SAMPLE" in block.meta:
        return "SINE"
    return "UNKNOWN"


def plot_time_series(block: Block, x_label="time (ms)", y_label="value") -> go.Figure:
    """Generic fallback: first column as x, second as y."""
    if not block.rows:
        raise ValueError("the captured block contains no numeric rows")
    if block.columns and len(block.columns) >= 2:
        x, y = block.column(0), block.column(1)
    else:
        x = list(range(len(block.rows)))
        y = block.column(1) if len(block.rows[0]) > 1 else block.column(0)
    fig = go.Figure(go.Scatter(x=x, y=y, mode="lines+markers", marker=dict(size=4)))
    fig.update_layout(xaxis_title=x_label, yaxis_title=y_label)
    return fig


def plot_sine(block: Block) -> tuple[go.Figure, dict]:
    """Phase 1: DAC sine sampled by the ADC. Mirrors plot.py."""
    fsig = block.meta.get("F_SIGNAL", 0.0)
    fsamp = block.meta.get("F_SAMPLE", 1.0)
    values = block.column(1)
    n = len(values)
    volts = [v / 4095.0 * 3.3 for v in values]
    t_ms = [i / fsamp * 1000.0 for i in range(n)]

    fig = go.Figure(go.Scatter(x=t_ms, y=volts, mode="lines+markers", marker=dict(size=4)))
    nyq = fsamp / 2
    alias = fsig > nyq
    fig.update_layout(
        title=f"F_signal={fsig:.0f} Hz | F_sample={fsamp:.0f} Hz | Nyquist={nyq:.0f} Hz"
        + ("  -- ALIASING" if alias else ""),
        xaxis_title="time (ms)", yaxis_title="voltage (V)",
    )
    stats = {"F_signal (Hz)": fsig, "F_sample (Hz)": fsamp, "Nyquist (Hz)": nyq,
              "Aliasing?": "YES" if alias else "no"}
    return fig, stats


def plot_fft(block: Block) -> tuple[go.Figure, dict]:
    """Phase 2b: frequency-domain view of the same sine capture. Mirrors
    fft_analysis.py -- same rfft/argmax logic."""
    fsig = block.meta.get("F_SIGNAL", 0.0)
    fsamp = block.meta.get("F_SAMPLE", 1.0)
    values = np.array(block.column(1), dtype=float)
    values = values - values.mean()
    n = len(values)

    spectrum = np.abs(np.fft.rfft(values)) / n
    freqs = np.fft.rfftfreq(n, d=1.0 / fsamp)
    peak_hz = float(freqs[np.argmax(spectrum)])
    nyq = fsamp / 2

    fig = go.Figure(go.Scatter(x=freqs, y=spectrum, mode="lines"))
    fig.add_vline(x=peak_hz, line_dash="dash", line_color="red",
                  annotation_text=f"peak seen: {peak_hz:.0f} Hz")
    fig.update_layout(
        title=f"FFT -- real signal {fsig:.0f} Hz, ADC sees {peak_hz:.0f} Hz",
        xaxis_title="frequency (Hz)", yaxis_title="magnitude",
    )
    stats = {"Real signal (Hz)": fsig, "ADC sees (Hz)": round(peak_hz, 1),
              "Nyquist (Hz)": nyq}
    return fig, stats


def plot_jitter(block: Block) -> tuple[go.Figure, dict]:
    """Phase 2a: sampling-interval jitter. Mirrors jitter_analysis.py."""
    method = block.meta.get("METHOD", "?")
    target = float(block.meta.get("TARGET_US", 1000))
    ts = np.array(block.column(-1) if len(block.columns) else block.column(len(block.rows[0]) - 1),
                  dtype=float)
    intervals = np.diff(ts)
    jitter = float(intervals.std())
    worst = float(intervals.max() - target)

    fig = go.Figure(go.Scatter(y=intervals, mode="lines+markers", marker=dict(size=4)))
    fig.add_hline(y=target, line_dash="dash", line_color="green",
                  annotation_text=f"ideal {target:.0f} us")
    fig.update_layout(
        title=f"Sampling intervals -- method: {method} | jitter (std) = {jitter:.1f} us",
        xaxis_title="sample number", yaxis_title="interval to previous sample (us)",
    )
    stats = {"Method": method, "Target (us)": target, "Jitter std (us)": round(jitter, 1),
              "Worst-case late (us)": round(worst, 1)}
    return fig, stats


def plot_step(block: Block, capacitance_uf: float = 10.0) -> tuple[go.Figure, dict]:
    """Phase 3: RC charging curve -> extract tau and implied R. Mirrors
    step_analysis.py."""
    t_us = np.array(block.column(0), dtype=float)
    adc = np.array(block.column(1), dtype=float)

    final = float(np.mean(adc[t_us > t_us.max() * 0.8]))
    start = float(adc[0])
    target = start + 0.632 * (final - start)
    tau_us = float(np.interp(target, adc, t_us))
    r_ohms = tau_us * 1e-6 / (capacitance_uf * 1e-6)

    fig = go.Figure(go.Scatter(x=t_us / 1000, y=adc, mode="markers", marker=dict(size=3)))
    fig.add_hline(y=target, line_dash="dash", line_color="red",
                  annotation_text=f"63% (tau={tau_us/1000:.2f} ms -> R={r_ohms:.0f} ohm)")
    fig.update_layout(
        title="Capacitor charging curve -> R from RC time constant",
        xaxis_title="time (ms)", yaxis_title="ADC counts",
    )
    stats = {"tau (ms)": round(tau_us / 1000, 2), "C assumed (uF)": capacitance_uf,
              "Implied R (ohm)": round(r_ohms, 0)}
    return fig, stats


def plot_adc_cal(block: Block) -> tuple[go.Figure, dict]:
    """Phase 2c: ADC transfer curve and error vs. a naive and factory
    calibration. Mirrors adc_cal.py."""
    dac_mv = np.array(block.column("dac_mv_ideal"), dtype=float)
    raw_mean = np.array(block.column("adc_raw_mean"), dtype=float)
    cal_mv = np.array(block.column("adc_cal_mv"), dtype=float)
    raw_std = np.array(block.column("adc_raw_std"), dtype=float)

    raw_mv = raw_mean / 4095.0 * 3300.0
    mask = (dac_mv > 200) & (dac_mv < 3100)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dac_mv, y=dac_mv, mode="lines", name="ideal (y=x)",
                              line=dict(dash="dash", color="black")))
    fig.add_trace(go.Scatter(x=dac_mv, y=raw_mv, mode="markers", name="raw ADC (naive)",
                              marker=dict(size=4)))
    fig.add_trace(go.Scatter(x=dac_mv, y=cal_mv, mode="markers", name="factory calibrated",
                              marker=dict(size=4)))
    fig.update_layout(title="ADC transfer curve", xaxis_title="DAC input (mV)",
                       yaxis_title="ADC reads (mV)")

    raw_err = raw_mv[mask] - dac_mv[mask]
    cal_err = cal_mv[mask] - dac_mv[mask]
    stats = {
        "Noise (counts)": round(float(raw_std.mean()), 1),
        "Max error raw (mV)": round(float(np.abs(raw_err).max()), 0),
        "Max error factory-cal (mV)": round(float(np.abs(cal_err).max()), 0),
    }
    return fig, stats


def plot_bode(block: Block) -> tuple[go.Figure, dict]:
    """Phase 3: frequency response sweep of the RC filter. Mirrors
    bode_analysis.py."""
    freq = np.array(block.column("freq_hz"), dtype=float)
    amp = np.array(block.column("amp_counts"), dtype=float)
    a0 = amp[0]
    gain_db = 20 * np.log10(amp / a0)
    fc = float(np.interp(-3.0, gain_db[::-1], freq[::-1]))

    fig = go.Figure(go.Scatter(x=freq, y=gain_db, mode="lines+markers"))
    fig.add_hline(y=-3, line_dash="dash", line_color="red", annotation_text="-3 dB")
    fig.update_xaxes(type="log")
    fig.update_layout(title="RC filter frequency response", xaxis_title="frequency (Hz)",
                       yaxis_title="gain (dB)")
    stats = {"Measured cutoff -3dB (Hz)": round(fc, 1)}
    return fig, stats


def plot_thrust_replay(block: Block) -> tuple[go.Figure, dict]:
    """Phase 4: reconstructed thrust curve + integrated impulse. Mirrors
    thrust_replay.py (DAC_MIN/MAX must match gen_thrust_firmware.py)."""
    dt_ms = block.meta.get("DT_MS", 2.0)
    dac_min, dac_max = 30, 230
    idx = np.array(block.column(0), dtype=float)
    adc_mv = np.array(block.column(2), dtype=float)
    t = idx * dt_ms / 1000.0

    dac_equiv = adc_mv / 3300.0 * 255.0
    f_max_guess = 200.0  # generic axis scale; real F_max comes from the .eng at generation time
    f_meas = np.clip((dac_equiv - dac_min) / (dac_max - dac_min) * f_max_guess, 0, None)
    impulse = float(np.trapezoid(f_meas, t))

    fig = go.Figure(go.Scatter(x=t * 1000, y=f_meas, mode="markers", marker=dict(size=4)))
    fig.update_layout(title=f"Thrust replay (relative units) -- impulse proportional to {impulse:.1f}",
                       xaxis_title="time (ms)", yaxis_title="thrust (arb. units)")
    stats = {"Burn time (ms)": round(float(t[-1] * 1000), 0)}
    return fig, stats


_DISPATCH = {
    "SINE": plot_sine,
    "FFT": plot_fft,
    "TIMING": plot_jitter,
    "STEP": plot_step,
    "ADC_CAL": plot_adc_cal,
    "BODE": plot_bode,
    "THRUST_REPLAY": plot_thrust_replay,
}


def plot_block(block: Block):
    """Pick the right plot for a block and return (figure, stats_dict)."""
    if not block.rows:
        raise ValueError("the block is empty")
    widths = {len(row) for row in block.rows}
    if len(widths) != 1:
        raise ValueError("the block contains rows with inconsistent column counts")
    kind = detect_kind(block)
    fn = _DISPATCH.get(kind)
    if fn is None:
        return plot_time_series(block), {}
    return fn(block)
