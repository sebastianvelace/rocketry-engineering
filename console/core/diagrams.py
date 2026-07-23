"""
Wiring diagrams for the bench circuits, generated from code (schemdraw) so
they're reproducible and versioned instead of hand-drawn once and forgotten.

Each circuit returns (schematic_svg_bytes, pin_table). The pin table is the
part that actually prevents wiring mistakes -- explicit "this wire, from this
pin, to that pin" rows are far less ambiguous than reading a schematic symbol.
The schematic is there to give the overall shape at a glance.
"""
from __future__ import annotations

import io

import schemdraw
import schemdraw.elements as elm


def direct_jumper() -> tuple[bytes, list[dict]]:
    """Phase 1/2b/4: DAC output looped straight to the ADC input.
    Used by main.cpp (sine capture) and thrust_replay/main.cpp."""
    with schemdraw.Drawing(show=False) as d:
        d += elm.Dot().label("GPIO25\n(DAC)", loc="left")
        d += elm.Line().right().length(3).label("jumper wire", loc="top")
        d += elm.Dot().label("GPIO34\n(ADC)", loc="right")
        svg = d.get_imagedata("svg")

    pins = [
        {"from": "ESP32 GPIO25 (DAC)", "to": "ESP32 GPIO34 (ADC)",
         "how": "single jumper wire"},
    ]
    return svg, pins


def rc_filter(r_ohm: int = 220, c_uf: float = 10.0) -> tuple[bytes, list[dict]]:
    """Phase 3: first-order RC low-pass between the DAC and the ADC.
    Matches rc_filter/main.cpp and step_test/main.cpp exactly."""
    with schemdraw.Drawing(show=False) as d:
        d += (dac := elm.Dot().label("GPIO25\n(DAC)", loc="left"))
        d += elm.Resistor().right().length(3).label(f"R = {r_ohm} Ω")
        d += (node := elm.Dot())
        d += elm.Line().right().length(2)
        d += elm.Dot().label("GPIO34\n(ADC)", loc="right")
        d += elm.Capacitor().down().at(node.center).label(f"C = {c_uf:.0f} µF", loc="right")
        d += elm.Ground()
        svg = d.get_imagedata("svg")

    pins = [
        {"from": "ESP32 GPIO25 (DAC)", "to": f"Resistor leg 1 ({r_ohm} Ω)",
         "how": "jumper wire"},
        {"from": f"Resistor leg 2 ({r_ohm} Ω)", "to": "node: ESP32 GPIO34 (ADC) AND capacitor + (long leg)",
         "how": "shared breadboard row"},
        {"from": "Capacitor − (short leg / stripe)", "to": "ESP32 GND",
         "how": "jumper wire"},
    ]
    return svg, pins


def imu_baro_i2c(imu_label: str = "MPU6050 (GY-521)",
                  baro_label: str = "BME280") -> tuple[bytes, list[dict]]:
    """Future sensors (Fase 6 / Option A): both are I2C, 3.3V, share the bus."""
    with schemdraw.Drawing(show=False) as d:
        d += elm.Dot().label("ESP32\n3.3V", loc="left")
        d += elm.Line().right().length(1)
        d += (vcc := elm.Dot())
        d += elm.Line().right().length(4)
        d += elm.Dot().label(f"{imu_label}\nVCC", loc="right")

        d.push()
        d += elm.Line().down().at(vcc.center).length(1.5)
        d += elm.Line().right().length(4)
        d += elm.Dot().label(f"{baro_label}\nVCC", loc="right")
        d.pop()

        svg = d.get_imagedata("svg")

    pins = [
        {"from": "ESP32 3.3V", "to": f"{imu_label} VCC AND {baro_label} VCC",
         "how": "shared power rail (both are 3.3V modules)"},
        {"from": "ESP32 GND", "to": f"{imu_label} GND AND {baro_label} GND",
         "how": "shared ground rail"},
        {"from": "ESP32 GPIO21 (SDA)", "to": f"{imu_label} SDA AND {baro_label} SDA",
         "how": "shared I2C data bus"},
        {"from": "ESP32 GPIO22 (SCL)", "to": f"{imu_label} SCL AND {baro_label} SCL",
         "how": "shared I2C clock bus"},
    ]
    return svg, pins


CIRCUITS = {
    "Direct jumper (Phase 1/2/4)": direct_jumper,
    "RC anti-aliasing filter (Phase 3)": rc_filter,
    "IMU + barometer I2C (future)": imu_baro_i2c,
}


CIRCUIT_GUIDES = {
    "Direct jumper (Phase 1/2/4)": {
        "short": "DAC loopback",
        "purpose": "Send the ESP32 DAC output directly back into its ADC input.",
        "use_for": "Sine, FFT, ADC timing and thrust replay captures.",
        "parts": ["1 ESP32", "1 jumper wire", "1 USB data cable"],
        "before": "Disconnect USB power before moving the jumper.",
        "verify": [
            "GPIO25 is the signal source (DAC).",
            "GPIO34 is the measurement input (ADC).",
            "No external voltage source is connected to GPIO34.",
        ],
    },
    "RC anti-aliasing filter (Phase 3)": {
        "short": "RC filter",
        "purpose": "Place a first-order low-pass filter between the DAC and ADC.",
        "use_for": "Step response and Bode response captures.",
        "parts": ["1 ESP32", "1 × 220 Ω resistor", "1 × 10 µF capacitor", "Jumper wires", "Breadboard"],
        "before": "Disconnect USB power and identify the capacitor polarity before wiring.",
        "verify": [
            "The capacitor long leg (+) shares the GPIO34 node.",
            "The striped or short capacitor leg (-) goes to GND.",
            "The resistor sits between GPIO25 and the GPIO34 node.",
        ],
    },
    "IMU + barometer I2C (future)": {
        "short": "I2C sensors",
        "purpose": "Share one 3.3 V I2C bus between the IMU and barometer.",
        "use_for": "Future inertial and atmospheric sensor integration.",
        "parts": ["1 ESP32", "1 MPU6050 / GY-521", "1 BME280", "Jumper wires", "Breadboard"],
        "before": "Confirm both sensor modules accept 3.3 V logic and power.",
        "verify": [
            "Both sensors share 3.3 V and GND.",
            "Both SDA pins connect to GPIO21.",
            "Both SCL pins connect to GPIO22.",
        ],
    },
}
