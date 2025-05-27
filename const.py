"""Constants for the TIS integration."""

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    UnitOfTemperature,
)

DOMAIN = "tis_control"

DEVICES_DICT = {
    (0x1B, 0xBA): "RCU-8OUT-8IN",
    (0x0B, 0xE9): "SEC-SM",
    (0x80, 0x58): "IP-COM-PORT",
    (0x01, 0xA8): "RLY-4CH-10",
    (0x23, 0x32): "LUNA-TFT-43",
    (0x80, 0x25): "VEN-3S-3R-HC-BUS",
    (0x80, 0x38): "BUS-ES-IR",
    (0x02, 0x5A): "DIM-2CH-6A",
    (0x02, 0x58): "DIM-6CH-2A",
    (0x00, 0x76): "4DI-IN",
    (0x80, 0x2B): "24R20Z",
    (0x20, 0x58): "DIM-6CH-2A",
    (0x1B, 0xB6): "TIS-TE-DIM-4CH-1A",
    (0x80, 0x2D): "TIS-RCU-20OUT-20IN",
    (0x01, 0xB8): "TIS-VLC-12CH-10A",
    (0x01, 0xAA): "TIS-VLC-6CH-3A",
}

TEMPERATURE_RANGES = {
    HVACMode.COOL: {
        "min": (15.0, 59.0),
        "max": (26.0, 79.0),
        "target": (20.0, 68.0),
        "packet_mode_index": 0,
    },
    HVACMode.HEAT: {
        "min": (20.0, 68.0),
        "max": (35.0, 95.0),
        "target": (28.0, 82.0),
        "packet_mode_index": 1,
    },
    HVACMode.FAN_ONLY: {
        "min": (15.0, 59.0),
        "max": (26.0, 79.0),
        "target": (20.0, 68.0),
        "packet_mode_index": 2,
    },
    HVACMode.AUTO: {
        "min": (15.0, 59.0),
        "max": (35.0, 95.0),
        "target": (25.0, 77.0),
        "packet_mode_index": 3,
    },
    # off
    HVACMode.OFF: {
        "min": (15.0, 59.0),
        "max": (26.0, 79.0),
        "target": (20.0, 68.0),
        "packet_mode_index": 0,
    },
}
FAN_MODES = {
    FAN_AUTO: 0,
    FAN_HIGH: 1,
    FAN_MEDIUM: 2,
    FAN_LOW: 3,
}

ENERGY_SENSOR_TYPES = {
    "v1": "Voltage Phase 1",
    "v2": "Voltage Phase 2",
    "v3": "Voltage Phase 3",
    "current_p1": "Current Phase 1",
    "current_p2": "Current Phase 2",
    "current_p3": "Current Phase 3",
    "active_p1": "Active Power Phase 1",
    "active_p2": "Active Power Phase 2",
    "active_p3": "Active Power Phase 3",
    "apparent1": "Apparent Power Phase 1",
    "apparent2": "Apparent Power Phase 2",
    "apparent3": "Apparent Power Phase 3",
    "reactive1": "Reactive Power Phase 1",
    "reactive2": "Reactive Power Phase 2",
    "reactive3": "Reactive Power Phase 3",
    "pf1": "Power Factor Phase 1",
    "pf2": "Power Factor Phase 2",
    "pf3": "Power Factor Phase 3",
    "pa1": "Phase Angle Phase 1",
    "pa2": "Phase Angle Phase 2",
    "pa3": "Phase Angle Phase 3",
    "avg_live_to_neutral": "Average Live to Neutral Voltage",
    "avg_current": "Average Current",
    "sum_current": "Sum Current",
    "total_power": "Total Power",
    "total_volt_amps": "Total Volt Amps",
    "total_var": "Total VAR",
    "total_pf": "Total Power Factor",
    "total_pa": "Total Phase Angle",
    "frq": "Frequency",
}
