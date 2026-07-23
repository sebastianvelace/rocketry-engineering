"""
Generic reader for the project's serial block protocol.

Every DAQ firmware in avionics/daq-fase1 emits data the same way:

    # BLOCK <meta>
    col1,col2,...          <- optional header line (absent only in main.cpp,
    v1,v2,...                  which always emits "i,value" pairs)
    v1,v2,...
    # END

<meta> is either a bare token ("STEP", "ADC_CAL") followed by key=value pairs
("BODE R=220 C=10uF", "THRUST_REPLAY DT_MS=2.0 N=218"), or pure key=value
pairs with no token ("F_SIGNAL=50.00 F_SAMPLE=1000.00 N=200",
"METHOD=timer TARGET_US=1000"). This module handles both and replaces the
seven near-identical read_block() copies scattered across the phase scripts.
"""
from __future__ import annotations

import glob
import re
import time
from dataclasses import dataclass, field

import serial

DEFAULT_BAUD = 115200

# Recognize a bare token in the meta line: an all-caps word (with underscores)
# that is not itself a key=value pair.
_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_KV_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=([^\s]+)")


@dataclass
class Block:
    """One captured '# BLOCK ... # END' section."""

    kind: str                      # bare token if present, else "" (e.g. "STEP", "ADC_CAL")
    meta: dict = field(default_factory=dict)   # parsed key=value pairs (numeric when possible)
    columns: list = field(default_factory=list)  # header names, e.g. ["t_us", "adc"]
    rows: list = field(default_factory=list)      # list of float lists

    def column(self, name_or_index):
        """Return one column of the row data by header name or index."""
        if isinstance(name_or_index, int):
            idx = name_or_index
        elif self.columns and name_or_index in self.columns:
            idx = self.columns.index(name_or_index)
        else:
            raise KeyError(f"No column '{name_or_index}' in {self.columns}")
        return [r[idx] for r in self.rows]


def find_ports():
    """List candidate serial ports (Linux naming)."""
    return sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))


def _parse_meta_line(line):
    """Parse '# BLOCK <rest>' into (kind, meta_dict)."""
    rest = line[len("# BLOCK"):].strip()
    kind = ""
    tokens = rest.split()
    remaining = []
    for i, tok in enumerate(tokens):
        if i == 0 and _TOKEN_RE.match(tok) and "=" not in tok:
            kind = tok
        else:
            remaining.append(tok)
    meta = {}
    for m in _KV_RE.finditer(" ".join(remaining)):
        key, val = m.group(1), m.group(2)
        try:
            meta[key] = float(val) if ("." in val or "e" in val.lower()) else int(val)
        except ValueError:
            meta[key] = val
    return kind, meta


def _looks_like_header(line: str) -> bool:
    """True if a CSV line is a text header (e.g. 'freq_hz,amp_counts') rather
    than numeric data."""
    first_field = line.split(",")[0]
    try:
        float(first_field)
        return False
    except ValueError:
        return True


def read_one_block(ser: serial.Serial, timeout_s: float = 15.0) -> Block | None:
    """Read a single '# BLOCK ... # END' section from an open serial port.

    Returns None if no complete block arrives within timeout_s.
    """
    deadline = time.time() + timeout_s
    kind, meta, columns, rows = "", {}, [], []
    capturing = False

    while time.time() < deadline:
        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode(errors="ignore").strip()
        if not line:
            continue

        if line.startswith("# BLOCK"):
            kind, meta = _parse_meta_line(line)
            columns, rows = [], []
            capturing = True
            continue

        if line == "# END" and capturing:
            return Block(kind=kind, meta=meta, columns=columns, rows=rows)

        if not capturing:
            continue

        if "," not in line or line.startswith("#"):
            continue

        if not rows and not columns and _looks_like_header(line):
            columns = [c.strip() for c in line.split(",")]
            continue

        try:
            rows.append([float(x) for x in line.split(",")])
        except ValueError:
            continue

    return None


def open_and_read(port: str, baud: int = DEFAULT_BAUD, timeout_s: float = 15.0) -> Block | None:
    """Convenience: open a port, read one block, close it."""
    with serial.Serial(port, baud, timeout=timeout_s) as ser:
        return read_one_block(ser, timeout_s=timeout_s)
