#!/usr/bin/env python3
"""
ADC characterization & calibration (Phase 2c).

Reads the DAC-sweep block from the adc_cal firmware and:
  1. plots the transfer curve (raw ADC vs. calibrated ADC),
  2. quantifies the raw ADC's error against a straight-line ideal,
  3. fits our own polynomial calibration and shows the residual error,
  4. reports the measurement noise (std dev of repeated reads).

Usage:
    python adc_cal.py                 # auto-detect port
    python adc_cal.py /dev/ttyUSB0
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
    rows, capturing = [], False
    while True:
        line = ser.readline().decode(errors="ignore").strip()
        if line.startswith("# BLOCK ADC_CAL"):
            capturing = True
        elif line == "# END" and capturing:
            return np.array(rows, dtype=float)
        elif capturing and line.count(",") == 4 and not line[0].isalpha():
            try:
                rows.append([float(x) for x in line.split(",")])
            except ValueError:
                pass


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    print(f"Reading ADC sweep from {port} ... (~2 s)")
    with serial.Serial(port, 115200, timeout=10) as ser:
        data = read_block(ser)

    dac         = data[:, 0]
    dac_mv      = data[:, 1]     # DAC nominal output (our reference input)
    raw_count   = data[:, 2]     # raw ADC counts, 0..4095
    raw_std     = data[:, 3]     # noise, in counts
    cal_mv      = data[:, 4]     # ESP32 factory-calibrated millivolts

    # Naive conversion of raw counts to volts (what a beginner would do)
    raw_mv = raw_count / 4095.0 * 3300.0

    # Use a linear-ish region (avoid the dead zones at the very ends) as the
    # working reference for "ideal", then quantify how far raw drifts from it.
    mask = (dac_mv > 200) & (dac_mv < 3100)

    # Error of the naive raw conversion vs the DAC reference input:
    raw_err = raw_mv[mask] - dac_mv[mask]
    cal_err = cal_mv[mask] - dac_mv[mask]

    # Fit OUR OWN calibration: a cubic mapping raw_count -> true mV (using the
    # DAC input as ground truth). This is exactly what you do with a real sensor.
    coeffs = np.polyfit(raw_count[mask], dac_mv[mask], 3)
    our_cal_mv = np.polyval(coeffs, raw_count)
    our_err = our_cal_mv[mask] - dac_mv[mask]

    print(f"\nMeasurement noise (raw)     : {raw_std.mean():.1f} counts "
          f"(~{raw_std.mean()/4095*3300:.1f} mV)")
    print(f"Max error, naive raw        : {np.abs(raw_err).max():.0f} mV")
    print(f"Max error, factory cal      : {np.abs(cal_err).max():.0f} mV")
    print(f"Max error, our cubic cal    : {np.abs(our_err).max():.0f} mV")

    # ---- plots --------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.5))

    ax1.plot(dac_mv, dac_mv, "k--", lw=1, label="ideal (y = x)")
    ax1.plot(dac_mv, raw_mv, ".", ms=3, label="raw ADC (naive)")
    ax1.plot(dac_mv, cal_mv, ".", ms=3, label="factory calibrated")
    ax1.set(title="Transfer curve", xlabel="DAC input (mV)",
            ylabel="ADC reads (mV)")
    ax1.grid(alpha=0.3)
    ax1.legend()

    ax2.axhline(0, color="k", lw=1)
    ax2.plot(dac_mv[mask], raw_err, ".", ms=3, label="raw error")
    ax2.plot(dac_mv[mask], cal_err, ".", ms=3, label="factory-cal error")
    ax2.plot(dac_mv[mask], our_err, ".", ms=3, label="our cubic-cal error")
    ax2.set(title="Error vs. input (working range)", xlabel="DAC input (mV)",
            ylabel="error (mV)")
    ax2.grid(alpha=0.3)
    ax2.legend()

    fig.suptitle("ESP32 ADC characterization & calibration")
    fig.tight_layout()
    fig.savefig("adc_calibration.png", dpi=110)
    print("Saved adc_calibration.png")
    plt.show()


if __name__ == "__main__":
    main()
