#!/usr/bin/env python3
"""
Phase 3 -- plot the measured frequency response (Bode) of the RC filter and
extract its real cutoff frequency.

Usage:
    python bode_analysis.py [/dev/ttyUSB0]
"""
import sys
import glob
import numpy as np
import serial
import matplotlib.pyplot as plt

C = 10e-6          # capacitor value (F)
R_NOMINAL = 220    # what we believe the resistor is (ohms)


def find_port():
    ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    if not ports:
        sys.exit("No serial port found.")
    return ports[0]


def read_block(ser):
    rows, cap = [], False
    while True:
        line = ser.readline().decode(errors="ignore").strip()
        if line.startswith("# BLOCK BODE"):
            rows, cap = [], True
        elif line == "# END" and cap:
            return np.array(rows, dtype=float)
        elif cap and "," in line and not line[0].isalpha():
            try:
                f, a = line.split(",")
                rows.append([float(f), float(a)])
            except ValueError:
                pass


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    print(f"Reading Bode sweep from {port} ...")
    with serial.Serial(port, 115200, timeout=25) as ser:
        data = read_block(ser)

    freq = data[:, 0]
    amp = data[:, 1]
    a0 = amp[0]                              # amplitude at the lowest frequency
    gain_db = 20 * np.log10(amp / a0)

    # Cutoff = where gain crosses -3 dB. Interpolate on the (freq, gain) curve.
    fc_meas = np.interp(-3.0, gain_db[::-1], freq[::-1])
    r_implied = 1 / (2 * np.pi * fc_meas * C)
    fc_nominal = 1 / (2 * np.pi * R_NOMINAL * C)

    print(f"\nMeasured cutoff (-3 dB)   : {fc_meas:.1f} Hz")
    print(f"Cutoff from R=220, C=10uF : {fc_nominal:.1f} Hz")
    print(f"Implied series resistance : {r_implied:.0f} ohms "
          f"(vs {R_NOMINAL} nominal)")

    # Theoretical first-order curves for comparison
    ff = np.logspace(np.log10(freq.min()), np.log10(freq.max()), 200)
    th_meas = 20 * np.log10(1 / np.sqrt(1 + (ff / fc_meas) ** 2))
    th_nom = 20 * np.log10(1 / np.sqrt(1 + (ff / fc_nominal) ** 2))

    plt.figure(figsize=(10, 5))
    plt.semilogx(freq, gain_db, "o-", label="measured")
    plt.semilogx(ff, th_meas, "--", alpha=0.7,
                 label=f"1st-order fit (fc={fc_meas:.1f} Hz)")
    plt.semilogx(ff, th_nom, ":", alpha=0.6,
                 label=f"expected from R,C (fc={fc_nominal:.0f} Hz)")
    plt.axhline(-3, color="r", ls="--", alpha=0.5, label="-3 dB")
    plt.axvline(fc_meas, color="g", ls="--", alpha=0.5)
    plt.title("RC low-pass filter -- measured frequency response (Bode)")
    plt.xlabel("frequency (Hz)")
    plt.ylabel("gain (dB)")
    plt.grid(True, which="both", alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig("bode.png", dpi=110)
    print("Saved bode.png")
    plt.show()


if __name__ == "__main__":
    main()
