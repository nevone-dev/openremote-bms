#!/usr/bin/env python3
"""
BMS Simulator — continuously pushes realistic sensor data to OpenRemote.

Usage:
    python -m simulator.sim

Environment:
    OR_BASE_URL    https://localhost
    OR_REALM       master
    OR_USERNAME    admin
    OR_PASSWORD    secret
    TICK_SECONDS   5
    LOG_LEVEL      INFO
"""

import json
import logging
import os
import signal
import ssl
import threading
import time
import urllib.parse
import urllib.request

from .models import HVACState, LightState, NetworkState, PrinterState, RoomSimState
from .patterns import (
    ROOM_OFFSETS,
    humidity,
    hvac_mode_status,
    is_work_hours,
    lighting,
    network_ports,
    occupancy_factor,
    power_consumption,
    printer_pages,
    printer_status,
    printer_toner,
    temperature,
)

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_URL  = os.environ.get("OR_BASE_URL", "https://localhost")
REALM     = os.environ.get("OR_REALM", "master")
USERNAME  = os.environ.get("OR_USERNAME", "admin")
PASSWORD  = os.environ.get("OR_PASSWORD", "secret")
TICK      = int(os.environ.get("TICK_SECONDS", "5"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)-8s sim — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sim")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

FLOORS = [1, 2]
ROOMS  = ["Office A", "Office B", "Meeting Room", "Server Room"]

# Signal flag — set by SIGINT/SIGTERM to break the main loop
_stop = threading.Event()


# ── Auth ───────────────────────────────────────────────────────────────────────

_token: str = ""
_token_expires: float = 0.0


def _get_token() -> str:
    global _token, _token_expires
    if _token and time.time() < _token_expires:
        return _token
    url = f"{BASE_URL}/auth/realms/{REALM}/protocol/openid-connect/token"
    data = urllib.parse.urlencode({
        "grant_type": "password",
        "client_id":  "openremote",
        "username":   USERNAME,
        "password":   PASSWORD,
    }).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, context=SSL_CTX) as r:
        body = json.loads(r.read())
    _token = body["access_token"]
    _token_expires = time.time() + body["expires_in"] - 30
    log.debug("Token refreshed")
    return _token


# ── OR helpers ─────────────────────────────────────────────────────────────────

def _http(method: str, path: str, body=None) -> object:
    token = _get_token()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE_URL + path, data=data,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {token}",
        },
        method=method,
    )
    with urllib.request.urlopen(req, context=SSL_CTX) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def _put_asset(asset: dict) -> dict:
    """PUT the full asset object back to OR. Returns the updated asset (with new version)."""
    return _http("PUT", f"/api/{REALM}/asset/{asset['id']}", asset)


def _patch_attrs(asset: dict, updates: list[tuple[str, object]]) -> None:
    """Mutate attribute values in a cached asset dict (in-place)."""
    now = int(time.time() * 1000)
    attrs = asset.setdefault("attributes", {})
    for name, value in updates:
        if name in attrs:
            attrs[name]["value"] = value
            attrs[name]["timestamp"] = now


# ── Asset discovery ────────────────────────────────────────────────────────────

def _discover_assets() -> dict[str, dict]:
    """Query OR, return {assetName → full_asset_dict}. Retries until OR is up."""
    while not _stop.is_set():
        try:
            assets = _http("POST", f"/api/{REALM}/asset/query", {})
            # Fetch full detail for each asset (query returns partial objects)
            full = {}
            for a in assets:
                detail = _http("GET", f"/api/{REALM}/asset/{a['id']}")
                full[a["name"]] = detail
            log.info("Discovered and loaded %d assets", len(full))
            return full
        except Exception as exc:
            log.warning("Asset discovery failed (%s) — retrying in 10 s", exc)
            _stop.wait(10)
    return {}


# ── State initialisation ───────────────────────────────────────────────────────

def _init_states() -> list[RoomSimState]:
    """Seed initial state to match the values written by seed.py."""
    states = []
    for floor in FLOORS:
        for i, room in enumerate(ROOMS):
            cfg = ROOM_OFFSETS[room]
            init_temp = round(21.0 + floor * 0.5 + i * 0.3, 1)
            states.append(RoomSimState(
                name=room,
                floor=floor,
                hvac=HVACState(
                    current_temp=init_temp,
                    setpoint=cfg["setpoint"],
                    humidity=float(45 + floor),
                    power=1.2,
                    mode="off",
                    status="idle",
                ),
                light=LightState(on=True, brightness=80.0, colour_temp=4000),
                network=NetworkState(active_ports=8 + i),
                printer=PrinterState(
                    toner=cfg["init_toner"],
                    pages_printed=13842 + floor * 1000 + i * 250,
                    status="ready",
                ),
            ))
    return states


# ── Tick logic ─────────────────────────────────────────────────────────────────

def _advance(state: RoomSimState, t: float) -> RoomSimState:
    cfg = ROOM_OFFSETS[state.name]

    new_temp   = temperature(t, state.hvac.current_temp, cfg["temp"])
    new_humid  = humidity(state.hvac.humidity)
    new_power  = power_consumption(t, state.hvac.power, state.name)
    new_mode, new_status = hvac_mode_status(new_temp, state.hvac.setpoint)

    new_on, new_bright, new_ctemp = lighting(t, state.name)

    new_ports  = network_ports(state.network.active_ports, cfg["total_ports"])

    new_toner  = printer_toner(state.printer.toner, t)
    new_pages  = printer_pages(state.printer.pages_printed, t)
    new_pstat  = printer_status(new_toner, t)

    return RoomSimState(
        name=state.name,
        floor=state.floor,
        hvac=HVACState(
            current_temp=new_temp,
            setpoint=state.hvac.setpoint,
            humidity=new_humid,
            power=new_power,
            mode=new_mode,
            status=new_status,
        ),
        light=LightState(on=new_on, brightness=new_bright, colour_temp=new_ctemp),
        network=NetworkState(active_ports=new_ports),
        printer=PrinterState(toner=new_toner, pages_printed=new_pages, status=new_pstat),
    )


_SEP = " – "  # en-dash — matches seed.py asset names

# Attribute updates per device type: (device_suffix, [(attr_name, state_accessor), ...])
def _device_updates(state: RoomSimState) -> list[tuple[str, list[tuple[str, object]]]]:
    return [
        (f"{state.name}{_SEP}HVAC", [
            ("currentTemperature", state.hvac.current_temp),
            ("humidity",           state.hvac.humidity),
            ("powerConsumption",   state.hvac.power),
            ("hvacMode",           state.hvac.mode),
            ("status",             state.hvac.status),
        ]),
        (f"{state.name}{_SEP}Lighting", [
            ("onOff",             state.light.on),
            ("brightness",        state.light.brightness),
            ("colourTemperature", state.light.colour_temp),
        ]),
        (f"{state.name}{_SEP}Network Switch", [
            ("activePorts", state.network.active_ports),
        ]),
        (f"{state.name}{_SEP}Printer", [
            ("tonerLevel",   state.printer.toner),
            ("pagesPrinted", state.printer.pages_printed),
            ("status",       state.printer.status),
        ]),
    ]


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("Simulator starting  tick=%ds  OR=%s", TICK, BASE_URL)

    asset_cache = _discover_assets()  # {name: full_asset_dict}
    if not asset_cache:
        log.warning("No assets discovered — did you run seed.py?")
        return

    states = _init_states()
    tick_n = 0

    while not _stop.is_set():
        t = time.time()
        writes = 0
        errors = 0

        for i, state in enumerate(states):
            new_state = _advance(state, t)
            states[i]  = new_state

            log.debug(
                "F%d %-12s  %.1f°C  hum=%.0f%%  %.1fkW  lights=%-3s  toner=%.1f%%",
                new_state.floor, new_state.name,
                new_state.hvac.current_temp, new_state.hvac.humidity,
                new_state.hvac.power, "ON" if new_state.light.on else "OFF",
                new_state.printer.toner,
            )

            for asset_name, updates in _device_updates(new_state):
                asset = asset_cache.get(asset_name)
                if not asset:
                    continue
                _patch_attrs(asset, updates)
                try:
                    updated = _put_asset(asset)
                    # Store the response so the next tick has the new version number
                    if isinstance(updated, dict) and "id" in updated:
                        asset_cache[asset_name] = updated
                    writes += 1
                except Exception as exc:
                    log.error("PUT failed for %s: %s", asset_name, exc)
                    errors += 1

        tick_n += 1
        log.info("Tick %-4d  %d assets written  %d errors  occ=%.0f%%",
                 tick_n, writes, errors, occupancy_factor(t) * 100)

        _stop.wait(TICK)

    log.info("Simulator stopped after %d ticks", tick_n)


def _handle_signal(signum, frame):
    log.info("Signal %d received — shutting down…", signum)
    _stop.set()


if __name__ == "__main__":
    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    main()
