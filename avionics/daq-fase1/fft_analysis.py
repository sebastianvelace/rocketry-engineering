#!/usr/bin/env python3
"""
Captures one block from the DAQ firmware and shows it in BOTH domains:
  - left:  the signal in time (volts vs ms)  -- what we already saw
  - right: the signal in FREQUENCY (the FFT) -- where aliasing becomes a number

The FFT (Fast Fourier Transform) answers: "which frequencies are present in this
signal, and how strong is each one?" A pure sine shows up as a single peak at its
frequency. If aliasing is happening, the peak appears at the WRONG (aliased)
frequency -- quantitative proof, not just eyeballing the waveform.

Usage:
    python fft_analysis.py                 # auto-detect port
    python fft_analysis.py /dev/ttyUSB0
"""
import sys
import glob

import numpy as np
import serial
import matplotlib.pyplot as plt


def find_port():
    ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    if not ports:
        sys.exit("No serial port found.")
    return ports[0]


def read_block(ser):
    meta, values, capturing = {}, [], False
    while True:
        line = ser.readline().decode(errors="ignore").strip()
        if line.startswith("# BLOCK"):
            for tok in line.split():
                if "=" in tok:
                    k, v = tok.split("=")
                    meta[k] = float(v)
            values, capturing = [], True
        elif line == "# END" and capturing:
            return meta, values
        elif capturing and "," in line:
            try:
                values.append(int(line.split(",")[1]))
            except (ValueError, IndexError):
                pass


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    print(f"Reading from {port} ...")
    with serial.Serial(port, 115200, timeout=5) as ser:
        meta, values = read_block(ser)

    fsig = meta.get("F_SIGNAL", 0.0)
    fsamp = meta.get("F_SAMPLE", 1.0)
    nyq = fsamp / 2.0

    x = np.array(values, dtype=float)
    x = x - x.mean()                       # remove DC so the FFT peak is the tone
    n = len(x)

    # FFT -> magnitude spectrum. rfft gives the 0..Nyquist half (real signal).
    spectrum = np.abs(np.fft.rfft(x)) / n
    freqs = np.fft.rfftfreq(n, d=1.0 / fsamp)   # frequency axis, 0..Nyquist

    peak_hz = freqs[np.argmax(spectrum)]        # dominant frequency the ADC "sees"
    apparent = abs(fsamp - fsig) if fsig > nyq else fsig  # expected aliased freq

    # ---- plot both domains --------------------------------------------------
    volts = np.array(values) / 4095.0 * 3.3
    t_ms = np.arange(n) / fsamp * 1000.0

    fig, (axt, axf) = plt.subplots(1, 2, figsize=(13, 4))

    axt.plot(t_ms, volts, ".-", ms=3)
    axt.set(title="TIME domain", xlabel="time (ms)", ylabel="volts")
    axt.grid(alpha=0.3)

    axf.plot(freqs, spectrum, "-")
    axf.axvline(peak_hz, color="r", ls="--", alpha=0.7,
                label=f"peak seen: {peak_hz:.0f} Hz")
    axf.set(title="FREQUENCY domain (FFT)", xlabel="frequency (Hz)",
            ylabel="magnitude")
    axf.grid(alpha=0.3)
    axf.legend()

    aliased = fsig > nyq
    tag = "  --  ALIASING" if aliased else ""
    fig.suptitle(f"F_signal={fsig:.0f} Hz  |  F_sample={fsamp:.0f} Hz  |  "
                 f"Nyquist={nyq:.0f} Hz{tag}")
    fig.tight_layout()

    out = "fft_alias.png" if aliased else "fft_clean.png"
    fig.savefig(out, dpi=110)
    print(f"Real signal : {fsig:.0f} Hz")
    print(f"ADC sees    : {peak_hz:.0f} Hz  (expected {apparent:.0f} Hz)")
    print(f"Saved {out}")
    plt.show()


if __name__ == "__main__":
    main()
