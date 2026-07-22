#!/usr/bin/env python3
"""
Measures the timing JITTER of a sampling method.

Each sample carries a timestamp (microseconds). Ideally every sample is exactly
TARGET_US apart. Jitter is how much the real spacing wanders from that ideal.
Low jitter = trustworthy timing = trustworthy data.

Capture a block from the timing_test firmware (soft or timer mode) and this
reports the interval statistics and plots interval-vs-sample.

Usage:
    python jitter_analysis.py                 # auto-detect, one method
    python jitter_analysis.py /dev/ttyUSB0
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
    meta, ts, capturing = {}, [], False
    while True:
        line = ser.readline().decode(errors="ignore").strip()
        if line.startswith("# BLOCK"):
            for tok in line.split():
                if "=" in tok:
                    k, v = tok.split("=")
                    meta[k] = v
            ts, capturing = [], True
        elif line == "# END" and capturing:
            return meta, np.array(ts, dtype=float)
        elif capturing and line.count(",") == 2:
            try:
                ts.append(int(line.split(",")[2]))   # timestamp is the 3rd field
            except (ValueError, IndexError):
                pass


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    with serial.Serial(port, 115200, timeout=6) as ser:
        meta, ts = read_block(ser)

    method = meta.get("METHOD", "?")
    target = float(meta.get("TARGET_US", 1000))
    intervals = np.diff(ts)                 # spacing between consecutive samples

    mean = intervals.mean()
    jitter = intervals.std()                # THE number: timing jitter
    worst = intervals.max() - target

    print(f"Method            : {method}")
    print(f"Target interval   : {target:.0f} us")
    print(f"Mean interval     : {mean:.1f} us")
    print(f"Jitter (std dev)  : {jitter:.1f} us")
    print(f"Worst-case late   : {worst:.0f} us")

    plt.figure(figsize=(10, 4))
    plt.plot(intervals, ".-", ms=3)
    plt.axhline(target, color="g", ls="--", alpha=0.7, label=f"ideal {target:.0f} us")
    plt.title(f"Sampling intervals -- method: {method}  |  jitter (std) = {jitter:.1f} us")
    plt.xlabel("sample number")
    plt.ylabel("interval to previous sample (us)")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    out = f"jitter_{method}.png"
    plt.savefig(out, dpi=110)
    print(f"Saved {out}")
    plt.show()


if __name__ == "__main__":
    main()
