from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class LightReading:
    on: bool
    brightness: float           # 0–100
    colour_temp: int            # Kelvin
    colour_rgb: Optional[dict]  # {"r": int, "g": int, "b": int} or None


@dataclass
class HVACReading:
    current_temp: float         # °C
    setpoint: float             # °C
    humidity: float             # %
    power_kw: float
    mode: str                   # "heating" | "cooling" | "off"
    status: str                 # "running" | "idle"


@dataclass
class NetworkReading:
    active_ports: int
    total_ports: int
    status: str
    uptime: str


@dataclass
class PrinterReading:
    toner_level: float          # %
    pages_printed: int
    status: str                 # "ready" | "offline" | "error"


@dataclass
class Room:
    name: str
    floor: int
    light: Optional[LightReading]   = None
    hvac: Optional[HVACReading]     = None
    network: Optional[NetworkReading] = None
    printer: Optional[PrinterReading] = None


@dataclass
class BuildingState:
    name: str
    rooms: list[Room] = field(default_factory=list)

    def get_room(self, name: str) -> Optional[Room]:
        for r in self.rooms:
            if r.name == name:
                return r
        return None

    @property
    def room_names(self) -> list[str]:
        seen: list[str] = []
        for r in self.rooms:
            if r.name not in seen:
                seen.append(r.name)
        return seen


@dataclass
class RoomEvent:
    room: str
    floor: int
    device: str         # "hvac" | "light" | "network" | "printer"
    attribute: str
    value: Any
    timestamp: float    # unix ms
