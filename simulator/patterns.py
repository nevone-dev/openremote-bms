"""
Pure signal-generation functions — no I/O, no side effects.
All functions that take `t` expect a unix timestamp (float, seconds).
"""

import math
import random
import time as _time

# Per-room constants: temperature offset from base curve, HVAC setpoint,
# total switch ports, initial toner level.
ROOM_OFFSETS: dict[str, dict] = {
    "Office A":     {"temp": 0.0, "setpoint": 21.5, "total_ports": 24, "init_toner": 74.0},
    "Office B":     {"temp": 0.3, "setpoint": 21.5, "total_ports": 24, "init_toner": 69.0},
    "Meeting Room": {"temp": 0.6, "setpoint": 22.0, "total_ports": 24, "init_toner": 64.0},
    "Server Room":  {"temp": 2.5, "setpoint": 19.0, "total_ports": 24, "init_toner": 59.0},
}


def _hour(t: float) -> float:
    lt = _time.localtime(t)
    return lt.tm_hour + lt.tm_min / 60.0 + lt.tm_sec / 3600.0


def occupancy_factor(t: float) -> float:
    """0.0 (night) → 1.0 (peak work hours 9-18), linear ramp at edges."""
    h = _hour(t)
    if h < 7.0 or h >= 20.0:
        return 0.0
    if 9.0 <= h < 18.0:
        return 1.0
    if h < 9.0:
        return (h - 7.0) / 2.0
    return (20.0 - h) / 2.0


def is_work_hours(t: float) -> bool:
    h = _hour(t)
    return 9.0 <= h < 18.0


def temperature(t: float, prev: float, room_offset: float) -> float:
    """Sinusoidal daily curve blended with thermal inertia + small noise.

    Base: 22.5 + 4.5·sin(2π·(h-14)/24)  → trough ≈06:00 (~18°C), peak ≈14:00 (~27°C)
    Blend: new = 0.95·prev + 0.05·(target + offset + N(0,0.05))
    """
    h = _hour(t)
    target = 22.5 + 4.5 * math.sin(2 * math.pi * (h - 14.0) / 24.0) + room_offset
    noisy = target + random.gauss(0, 0.05)
    return round(0.95 * prev + 0.05 * noisy, 2)


def humidity(prev: float) -> float:
    """Random walk bounded [35, 65], step ~ N(0, 0.3)."""
    return round(max(35.0, min(65.0, prev + random.gauss(0, 0.3))), 1)


def power_consumption(t: float, prev: float, room_name: str) -> float:
    """Step function: base load + work load × occupancy, blended with inertia.

    Server Room: base=5 kW, work_extra=8 kW
    Meeting Room: base=0.3 kW, work_extra=3 kW
    Others:       base=0.3 kW, work_extra=4.5 kW
    """
    occ = occupancy_factor(t)
    if room_name == "Server Room":
        base, work = 5.0, 8.0
    elif room_name == "Meeting Room":
        base, work = 0.3, 3.0
    else:
        base, work = 0.3, 4.5
    peak = base + work * occ + random.gauss(0, 0.05)
    return round(max(0.1, 0.9 * prev + 0.1 * peak), 2)


def hvac_mode_status(current_temp: float, setpoint: float) -> tuple[str, str]:
    """Derive HVAC mode and status from temperature vs setpoint (±0.5°C hysteresis)."""
    if current_temp < setpoint - 0.5:
        return "heating", "running"
    if current_temp > setpoint + 0.5:
        return "cooling", "running"
    return "off", "idle"


def lighting(t: float, room_name: str) -> tuple[bool, float, int]:
    """Return (on, brightness 0–100, colour_temp K).

    Server Room: always on during work hours, brightness=60 (equipment lighting).
    Others: 98% on probability during work hours; off otherwise.
    Colour temp transitions 4000K (day) → 3000K after 17:00.
    """
    work = is_work_hours(t)
    h = _hour(t)

    if not work:
        return False, 0.0, 4000

    if room_name == "Server Room":
        on = True
        brightness = round(random.uniform(55.0, 65.0), 1)
    else:
        on = random.random() > 0.02
        brightness = round(random.uniform(75.0, 100.0), 1) if on else 0.0

    colour_temp = 4000 if h < 17.0 else 3000
    return on, brightness, colour_temp


def network_ports(prev: int, total: int = 24) -> int:
    """Slow random walk ±1, bounded [2, total-2].  Biased toward stability."""
    delta = random.choice([-1, 0, 0, 0, 1])
    return max(2, min(total - 2, prev + delta))


def printer_toner(prev: float, t: float) -> float:
    """Deplete slightly each tick during work hours; auto-refill at ≤5%."""
    if prev <= 5.0:
        return 100.0
    if is_work_hours(t):
        return round(max(0.0, prev - random.uniform(0.001, 0.005)), 3)
    return round(max(0.0, prev - random.uniform(0.0, 0.001)), 3)


def printer_pages(prev: int, t: float) -> int:
    """Monotonically increasing; faster during work hours."""
    if is_work_hours(t):
        return prev + random.randint(0, 3)
    return prev + (1 if random.random() < 0.1 else 0)


def printer_status(toner: float, t: float) -> str:
    if toner <= 5.0:
        return "error"
    if not is_work_hours(t):
        return "offline"
    return "ready"
