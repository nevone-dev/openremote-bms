from dataclasses import dataclass


@dataclass
class HVACState:
    current_temp: float   # °C
    setpoint: float       # °C
    humidity: float       # %
    power: float          # kW
    mode: str             # "heating" | "cooling" | "off"
    status: str           # "running" | "idle"


@dataclass
class LightState:
    on: bool
    brightness: float     # 0–100
    colour_temp: int      # Kelvin


@dataclass
class NetworkState:
    active_ports: int


@dataclass
class PrinterState:
    toner: float          # %
    pages_printed: int
    status: str           # "ready" | "offline" | "error"


@dataclass
class RoomSimState:
    name: str
    floor: int
    hvac: HVACState
    light: LightState
    network: NetworkState
    printer: PrinterState
