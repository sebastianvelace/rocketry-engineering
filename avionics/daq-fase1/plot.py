#!/usr/bin/env python3
"""
Reads one CSV block from the ESP32 DAQ-Fase-1 firmware and plots it.

Usage:
    python plot.py                 # auto-detect port
    python plot.py /dev/ttyUSB0    # explicit port

The firmware prints blocks like:
    # BLOCK F_SIGNAL=50.0 F_SAMPLE=1000.0 N=200
    0,2048
    1,2510
    ...
    # END
"""
import sys
import glob

import serial
import matplotlib.pyplot as plt


def find_port():
    ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    if not ports:
        sys.exit("No serial port found. Plug in the ESP32 and try again.")
    return ports[0]


def read_block(ser):
    """Wait for one complete '# BLOCK ... # END' section and return (meta, values)."""
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
                _, val = line.split(",")
                values.append(int(val))
            except ValueError:
                pass


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    print(f"Reading from {port} ...")
    with serial.Serial(port, 115200, timeout=5) as ser:
        meta, values = read_block(ser)

    fsig = meta.get("F_SIGNAL", 0)
    fsamp = meta.get("F_SAMPLE", 1)
    nyq = fsamp / 2

    # Convert ADC counts (0..4095) to volts (~0..3.3V)
    volts = [v / 4095.0 * 3.3 for v in values]
    t_ms = [i / fsamp * 1000.0 for i in range(len(values))]

    plt.figure(figsize=(10, 4))
    plt.plot(t_ms, volts, ".-", markersize=4)
    alias = " -- ALIASING (signal above Nyquist!)" if fsig > nyq else ""
    plt.title(f"F_signal={fsig:.0f} Hz | F_sample={fsamp:.0f} Hz | Nyquist={nyq:.0f} Hz{alias}")
    plt.xlabel("time (ms)")
    plt.ylabel("voltage (V)")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    out = "capture.png"
    plt.savefig(out, dpi=110)
    print(f"Saved {out}  ({len(values)} samples)")
    plt.show()


if __name__ == "__main__":
    main()
