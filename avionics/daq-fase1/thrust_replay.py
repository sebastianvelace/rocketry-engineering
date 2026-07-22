#!/usr/bin/env python3
"""
Phase 4 -- analyze the thrust-replay capture.

Reconstructs the thrust curve from what the ADC measured, integrates it to get
the total impulse, and compares against the true impulse of the original .eng.

Impulse = area under the thrust-vs-time curve = integral of F dt. If our DAQ
recovers the right impulse from a KNOWN curve, we can trust it on a real motor.

Usage:
    python thrust_replay.py /home/sebasvelace/openMotor/eng/E.eng [/dev/ttyUSB0]
"""
import sys
import glob
import numpy as np
import serial
import matplotlib.pyplot as plt

DAC_MIN, DAC_MAX = 30, 230       # must match gen_thrust_firmware.py


def parse_eng(path):
    t, f, header = [], [], False
    for line in open(path):
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if not header:
            header = True
            continue
        p = line.split()
        if len(p) == 2:
            t.append(float(p[0])); f.append(float(p[1]))
    return np.array(t), np.array(f)


def read_block(ser):
    meta, rows, cap = {}, [], False
    while True:
        line = ser.readline().decode(errors="ignore").strip()
        if line.startswith("# BLOCK THRUST_REPLAY"):
            for tok in line.split():
                if "=" in tok:
                    k, v = tok.split("="); meta[k] = float(v)
            rows, cap = [], True
        elif line == "# END" and cap:
            return meta, np.array(rows, dtype=float)
        elif cap and line.count(",") == 2 and not line[0].isalpha():
            try:
                rows.append([float(x) for x in line.split(",")])
            except ValueError:
                pass


def main():
    eng = sys.argv[1] if len(sys.argv) > 1 else "/home/sebasvelace/openMotor/eng/E.eng"
    port = sys.argv[2] if len(sys.argv) > 2 else (
        (glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))[0])

    t_eng, f_eng = parse_eng(eng)
    i_true = np.trapezoid(f_eng, t_eng)
    f_max = f_eng.max()

    print(f"Reading replay from {port} ...")
    with serial.Serial(port, 115200, timeout=10) as ser:
        meta, data = read_block(ser)

    dt = meta["DT_MS"] / 1000.0
    idx        = data[:, 0]
    dac_played = data[:, 1]
    adc_mv     = data[:, 2]
    t = idx * dt

    # Reconstruct thrust from the ADC's measured millivolts (undo the scaling):
    #   dac_code = adc_mv / 3300 * 255 ;  F = (dac_code - DAC_MIN)/(DAC_MAX-DAC_MIN)*Fmax
    dac_equiv = adc_mv / 3300.0 * 255.0
    f_meas = (dac_equiv - DAC_MIN) / (DAC_MAX - DAC_MIN) * f_max
    f_meas = np.clip(f_meas, 0, None)

    i_meas = np.trapezoid(f_meas, t)
    err = 100 * (i_meas - i_true) / i_true

    # Peak thrust and burn time recovered from the measurement
    peak_meas = f_meas.max()
    burn_meas = t[f_meas > 0.05 * peak_meas][-1] if (f_meas > 0.05*peak_meas).any() else t[-1]

    print(f"\n--- Impulse validation ---")
    print(f"TRUE impulse (from .eng)  : {i_true:.2f} N*s")
    print(f"MEASURED impulse (DAQ)    : {i_meas:.2f} N*s")
    print(f"Error                     : {err:+.1f} %")
    print(f"Peak thrust  true/meas    : {f_max:.0f} / {peak_meas:.0f} N")
    print(f"Burn time    true/meas    : {t_eng[-1]*1000:.0f} / {burn_meas*1000:.0f} ms")

    plt.figure(figsize=(10, 4.5))
    plt.plot(t_eng*1000, f_eng, "-", lw=2, alpha=0.6,
             label=f"true curve  (I = {i_true:.1f} N·s)")
    plt.plot(t*1000, f_meas, ".", ms=4,
             label=f"measured by DAQ  (I = {i_meas:.1f} N·s, {err:+.1f}%)")
    plt.title(f"Thrust-curve replay through the DAQ pipeline  --  {eng.split('/')[-1]}")
    plt.xlabel("time (ms)")
    plt.ylabel("thrust (N)")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig("thrust_replay.png", dpi=110)
    print("Saved thrust_replay.png")
    plt.show()


if __name__ == "__main__":
    main()
