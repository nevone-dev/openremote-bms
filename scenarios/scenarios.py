"""
Predefined building states for AI agent testing.

Each scenario is a list of write operations that set the building into
a specific, reproducible state.  Apply one with::

    async with BMSClient() as bms:
        await apply_scenario(bms, "summer_heat")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bms.client import BMSClient

_ROOMS = ["Office A", "Office B", "Meeting Room", "Server Room"]

# Each entry: (room, device_suffix, attribute_name, value)
# device_suffix matches the en-dash naming in seed.py: e.g. "HVAC", "Lighting"
_WRITES: dict[str, list[tuple[str, str, str, object]]] = {

    # ── normal ────────────────────────────────────────────────────────────────
    # Typical working day: lights on at 80%, comfortable temperature, HVAC idle
    "normal": [
        *(
            (room, "Lighting", attr, val)
            for room in _ROOMS
            for attr, val in [("onOff", True), ("brightness", 80.0), ("colourTemperature", 4000)]
        ),
        *(
            (room, "HVAC", attr, val)
            for room in ["Office A", "Office B", "Meeting Room"]
            for attr, val in [
                ("currentTemperature", 21.5),
                ("temperatureSetpoint", 21.5),
                ("humidity",           48.0),
                ("powerConsumption",   1.2),
                ("hvacMode",           "off"),
                ("status",             "idle"),
            ]
        ),
        ("Server Room", "HVAC", "currentTemperature", 22.0),
        ("Server Room", "HVAC", "temperatureSetpoint", 19.0),
        ("Server Room", "HVAC", "hvacMode",  "cooling"),
        ("Server Room", "HVAC", "status",    "running"),
        ("Server Room", "HVAC", "powerConsumption", 6.5),
    ],

    # ── summer_heat ───────────────────────────────────────────────────────────
    # Offices are overheating; HVAC is running cooling but struggling
    "summer_heat": [
        ("Office A",    "HVAC", "currentTemperature", 28.5),
        ("Office A",    "HVAC", "hvacMode",           "cooling"),
        ("Office A",    "HVAC", "status",             "running"),
        ("Office A",    "HVAC", "powerConsumption",   4.8),
        ("Office B",    "HVAC", "currentTemperature", 27.8),
        ("Office B",    "HVAC", "hvacMode",           "cooling"),
        ("Office B",    "HVAC", "status",             "running"),
        ("Office B",    "HVAC", "powerConsumption",   4.5),
        ("Meeting Room","HVAC", "currentTemperature", 26.3),
        ("Meeting Room","HVAC", "hvacMode",           "cooling"),
        ("Meeting Room","HVAC", "status",             "running"),
        ("Server Room", "HVAC", "currentTemperature", 31.0),
        ("Server Room", "HVAC", "hvacMode",           "cooling"),
        ("Server Room", "HVAC", "status",             "running"),
        ("Server Room", "HVAC", "powerConsumption",   12.0),
    ],

    # ── after_hours ───────────────────────────────────────────────────────────
    # End of day: all lights off, HVAC idle, printers offline
    "after_hours": [
        *(
            (room, "Lighting", attr, val)
            for room in _ROOMS
            for attr, val in [("onOff", False), ("brightness", 0.0)]
        ),
        *(
            (room, "HVAC", attr, val)
            for room in _ROOMS
            for attr, val in [
                ("hvacMode",         "off"),
                ("status",           "idle"),
                ("powerConsumption", 0.1),
            ]
        ),
        *(
            (room, "Printer", "status", "offline")
            for room in _ROOMS
        ),
        # Server room stays on
        ("Server Room", "Lighting", "onOff",      True),
        ("Server Room", "Lighting", "brightness", 60.0),
        ("Server Room", "HVAC",     "hvacMode",   "cooling"),
        ("Server Room", "HVAC",     "status",     "running"),
    ],

    # ── energy_crisis ─────────────────────────────────────────────────────────
    # Wasteful energy state: all lights at max, HVAC fighting extreme setpoints
    "energy_crisis": [
        *(
            (room, "Lighting", attr, val)
            for room in _ROOMS
            for attr, val in [("onOff", True), ("brightness", 100.0), ("colourTemperature", 6500)]
        ),
        *(
            (room, "HVAC", attr, val)
            for room in ["Office A", "Office B", "Meeting Room"]
            for attr, val in [
                ("temperatureSetpoint", 16.0),
                ("hvacMode",            "cooling"),
                ("status",              "running"),
                ("powerConsumption",    8.5),
            ]
        ),
        ("Server Room", "HVAC", "temperatureSetpoint", 14.0),
        ("Server Room", "HVAC", "powerConsumption",    15.0),
        ("Server Room", "HVAC", "hvacMode",            "cooling"),
        ("Server Room", "HVAC", "status",              "running"),
    ],

    # ── printer_emergency ─────────────────────────────────────────────────────
    # Office A printer is out of toner and in error; rest of building is normal
    "printer_emergency": [
        ("Office A",    "Printer", "tonerLevel", 3.0),
        ("Office A",    "Printer", "status",     "error"),
        ("Office B",    "Printer", "tonerLevel", 69.0),
        ("Office B",    "Printer", "status",     "ready"),
        ("Meeting Room","Printer", "tonerLevel", 64.0),
        ("Meeting Room","Printer", "status",     "ready"),
        ("Server Room", "Printer", "tonerLevel", 59.0),
        ("Server Room", "Printer", "status",     "ready"),
    ],
}


SCENARIOS = _WRITES  # public alias


def list_scenarios() -> list[str]:
    return list(_WRITES.keys())


async def apply_scenario(client: "BMSClient", name: str) -> None:
    """Set the building into the named scenario state.

    All writes go through BMSClient.write_device_attribute() so they
    use the same auth and asset-name resolution as the rest of the SDK.
    """
    writes = _WRITES.get(name)
    if writes is None:
        raise ValueError(f"Unknown scenario {name!r}. Available: {list_scenarios()}")

    for room, device, attribute, value in writes:
        try:
            await client.write_device_attribute(room, device, attribute, value)
        except KeyError:
            pass   # asset may not exist if seed.py wasn't run for that floor
