"""
BMSClient — clean interface for AI agents to interact with the building.

Works by name (room names, not asset IDs).
Reads/writes go directly to OpenRemote REST.
Live subscriptions (watch_*) go through the gateway GraphQL WebSocket.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Optional

from ._or_transport import ORTransport
from .models import (
    BuildingState,
    HVACReading,
    LightReading,
    NetworkReading,
    PrinterReading,
    Room,
    RoomEvent,
)

log = logging.getLogger(__name__)

_SEP   = " – "   # en-dash — matches seed.py / sim.py asset names
_ROOMS = ["Office A", "Office B", "Meeting Room", "Server Room"]


def _attr(raw: dict, name: str, default=None) -> Any:
    return raw.get("attributes", {}).get(name, {}).get("value", default)


def _parse_light(raw: dict) -> Optional[LightReading]:
    attrs = raw.get("attributes", {})
    if not attrs:
        return None
    return LightReading(
        on=attrs.get("onOff", {}).get("value", False),
        brightness=float(attrs.get("brightness", {}).get("value") or 0),
        colour_temp=int(attrs.get("colourTemperature", {}).get("value") or 4000),
        colour_rgb=attrs.get("colourRGB", {}).get("value"),
    )


def _parse_hvac(raw: dict) -> Optional[HVACReading]:
    attrs = raw.get("attributes", {})
    if not attrs:
        return None
    return HVACReading(
        current_temp=float(attrs.get("currentTemperature", {}).get("value") or 0),
        setpoint=float(attrs.get("temperatureSetpoint", {}).get("value") or 21.5),
        humidity=float(attrs.get("humidity", {}).get("value") or 0),
        power_kw=float(attrs.get("powerConsumption", {}).get("value") or 0),
        mode=attrs.get("hvacMode", {}).get("value") or "off",
        status=attrs.get("status", {}).get("value") or "idle",
    )


def _parse_network(raw: dict) -> Optional[NetworkReading]:
    attrs = raw.get("attributes", {})
    if not attrs:
        return None
    return NetworkReading(
        active_ports=int(attrs.get("activePorts", {}).get("value") or 0),
        total_ports=int(attrs.get("totalPorts", {}).get("value") or 24),
        status=attrs.get("status", {}).get("value") or "unknown",
        uptime=attrs.get("uptime", {}).get("value") or "",
    )


def _parse_printer(raw: dict) -> Optional[PrinterReading]:
    attrs = raw.get("attributes", {})
    if not attrs:
        return None
    return PrinterReading(
        toner_level=float(attrs.get("tonerLevel", {}).get("value") or 0),
        pages_printed=int(attrs.get("pagesPrinted", {}).get("value") or 0),
        status=attrs.get("status", {}).get("value") or "unknown",
    )


def _floor_of(asset: dict, all_by_id: dict[str, dict]) -> int:
    """Walk parent chain to find the FloorAsset and return its floorLevel."""
    parent_id = asset.get("parentId")
    while parent_id:
        parent = all_by_id.get(parent_id, {})
        if parent.get("type") == "FloorAsset":
            return int(_attr(parent, "floorLevel") or 0)
        parent_id = parent.get("parentId")
    return 0


class BMSClient:
    """AI agent interface to the building management system.

    Usage::

        async with BMSClient() as bms:
            rooms = await bms.list_rooms()
            room  = await bms.get_room("Office A")
            print(room.hvac.current_temp)
            await bms.set_light("Office A", on=False)

    Subscriptions require the gateway to be running (default http://localhost:8000)::

        async for temp in bms.watch_temperature("Office A"):
            print(temp)
    """

    def __init__(
        self,
        or_base_url:  str = "https://localhost",
        or_realm:     str = "master",
        or_username:  str = "admin",
        or_password:  str = "secret",
        gateway_url:  str = "http://localhost:8000",
    ) -> None:
        self._gateway_url = gateway_url.rstrip("/")
        self._t = ORTransport(or_base_url, or_realm, or_username, or_password)
        self._cache: dict[str, str] = {}   # name → asset_id

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def __aenter__(self) -> "BMSClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    async def close(self) -> None:
        await self._t.close()

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _warm_cache(self) -> dict[str, str]:
        """Load asset name→id map once, return it."""
        if self._cache:
            return self._cache
        assets = await self._t.get_assets()
        self._cache = {a["name"]: a["id"] for a in assets}
        return self._cache

    async def _id(self, name: str) -> str:
        cache = await self._warm_cache()
        asset_id = cache.get(name)
        if not asset_id:
            raise KeyError(f"Asset not found: {name!r} — did you run seed.py?")
        return asset_id

    # ── Queries ───────────────────────────────────────────────────────────────

    async def list_rooms(self) -> list[str]:
        """Return all room names (unique, in seed.py order)."""
        cache = await self._warm_cache()
        # Room assets are ThingAssets whose names match the known room list pattern
        rooms: list[str] = []
        for name in cache:
            # A room asset name is the plain room name (no en-dash device suffix)
            if name in _ROOMS:
                if name not in rooms:
                    rooms.append(name)
        return rooms if rooms else _ROOMS  # fall back to known list

    async def get_room(self, name: str) -> Room:
        """Fetch current state of one room (all 4 devices)."""
        cache = await self._warm_cache()
        all_raw = await self._t.get_assets()
        all_by_id = {a["id"]: a for a in all_raw}

        # Find the room container asset to determine floor
        room_asset = None
        for a in all_raw:
            if a.get("name") == name and a.get("type") == "ThingAsset":
                room_asset = a
                break

        floor = _floor_of(room_asset, all_by_id) if room_asset else 0

        def _find(suffix: str) -> Optional[dict]:
            return all_by_id.get(cache.get(f"{name}{_SEP}{suffix}", ""))

        return Room(
            name=name,
            floor=floor,
            light=_parse_light(_find("Lighting") or {}),
            hvac=_parse_hvac(_find("HVAC") or {}),
            network=_parse_network(_find("Network Switch") or {}),
            printer=_parse_printer(_find("Printer") or {}),
        )

    async def get_building(self) -> BuildingState:
        """Fetch full building snapshot — all rooms on all floors."""
        all_raw = await self._t.get_assets()
        all_by_id = {a["id"]: a for a in all_raw}
        cache = {a["name"]: a["id"] for a in all_raw}

        building_name = next(
            (a["name"] for a in all_raw if a.get("type") == "BuildingAsset"),
            "OpenRemote HQ",
        )

        # Collect unique room names
        seen: list[str] = []
        for a in all_raw:
            if a.get("type") == "ThingAsset" and a["name"] in _ROOMS:
                if a["name"] not in seen:
                    seen.append(a["name"])
        if not seen:
            seen = _ROOMS

        rooms: list[Room] = []
        for room_name in seen:
            room_asset = next(
                (a for a in all_raw if a["name"] == room_name and a.get("type") == "ThingAsset"),
                None,
            )
            floor = _floor_of(room_asset, all_by_id) if room_asset else 0

            def _find(suffix: str, _cache=cache, _byid=all_by_id) -> Optional[dict]:
                return _byid.get(_cache.get(f"{room_name}{_SEP}{suffix}", ""))

            rooms.append(Room(
                name=room_name,
                floor=floor,
                light=_parse_light(_find("Lighting") or {}),
                hvac=_parse_hvac(_find("HVAC") or {}),
                network=_parse_network(_find("Network Switch") or {}),
                printer=_parse_printer(_find("Printer") or {}),
            ))

        return BuildingState(name=building_name, rooms=rooms)

    # ── Controls ──────────────────────────────────────────────────────────────

    async def set_light(
        self,
        room: str,
        *,
        on: Optional[bool]   = None,
        brightness: Optional[float] = None,
        colour_temp: Optional[int]  = None,
    ) -> None:
        """Set lighting state for a room. Pass only the fields you want to change."""
        asset_id = await self._id(f"{room}{_SEP}Lighting")
        writes: list[tuple[str, Any]] = []
        if on          is not None: writes.append(("onOff",             on))
        if brightness  is not None: writes.append(("brightness",        brightness))
        if colour_temp is not None: writes.append(("colourTemperature", colour_temp))
        for attr_name, val in writes:
            await self._t.write_attribute(asset_id, attr_name, val)

    async def set_hvac(
        self,
        room: str,
        *,
        mode:     Optional[str]   = None,
        setpoint: Optional[float] = None,
    ) -> None:
        """Set HVAC mode and/or temperature setpoint for a room."""
        asset_id = await self._id(f"{room}{_SEP}HVAC")
        if mode     is not None: await self._t.write_attribute(asset_id, "hvacMode",            mode)
        if setpoint is not None: await self._t.write_attribute(asset_id, "temperatureSetpoint", setpoint)

    async def write_device_attribute(
        self,
        room: str,
        device: str,   # "HVAC" | "Lighting" | "Network Switch" | "Printer"
        attribute: str,
        value: Any,
    ) -> None:
        """Low-level escape hatch for scenarios that need to set arbitrary attributes."""
        asset_id = await self._id(f"{room}{_SEP}{device}")
        await self._t.write_attribute(asset_id, attribute, value)

    # ── Subscriptions ─────────────────────────────────────────────────────────

    async def watch_temperature(self, room: str) -> AsyncGenerator[float, None]:
        """Yield live temperature readings for a room (requires gateway)."""
        asset_id = await self._id(f"{room}{_SEP}HVAC")
        async for event in self._gql_subscribe(asset_id, "currentTemperature"):
            val = event.get("value")
            if val is not None:
                yield float(val)

    async def watch_room(self, room: str) -> AsyncGenerator[RoomEvent, None]:
        """Yield all attribute change events for every device in a room."""
        cache = await self._warm_cache()
        device_map = {
            "HVAC":           "hvac",
            "Lighting":       "light",
            "Network Switch": "network",
            "Printer":        "printer",
        }
        asset_ids = {
            label: cache[f"{room}{_SEP}{suffix}"]
            for suffix, label in device_map.items()
            if f"{room}{_SEP}{suffix}" in cache
        }
        id_to_label = {v: k for k, v in asset_ids.items()}

        # Determine floor once
        all_raw = await self._t.get_assets()
        all_by_id = {a["id"]: a for a in all_raw}
        room_asset = next(
            (a for a in all_raw if a["name"] == room and a.get("type") == "ThingAsset"),
            None,
        )
        floor = _floor_of(room_asset, all_by_id) if room_asset else 0

        # Subscribe to each device asset in parallel via separate WS connections
        # For simplicity, fan out on the first matching device and re-subscribe
        for device_label, asset_id in asset_ids.items():
            async def _stream(aid=asset_id, dlabel=device_label):
                async for event in self._gql_subscribe(aid):
                    yield RoomEvent(
                        room=room,
                        floor=floor,
                        device=dlabel,
                        attribute=event["attributeName"],
                        value=event["value"],
                        timestamp=event["timestamp"],
                    )

        # Merge streams using asyncio
        import asyncio

        queue: asyncio.Queue = asyncio.Queue()

        async def _feed(aid: str, dlabel: str) -> None:
            async for event in self._gql_subscribe(aid):
                await queue.put(RoomEvent(
                    room=room,
                    floor=floor,
                    device=dlabel,
                    attribute=event["attributeName"],
                    value=event["value"],
                    timestamp=event["timestamp"],
                ))

        tasks = [
            asyncio.create_task(_feed(aid, dlabel))
            for dlabel, aid in asset_ids.items()
        ]
        try:
            while True:
                yield await queue.get()
        finally:
            for task in tasks:
                task.cancel()

    async def _gql_subscribe(
        self,
        asset_id: str,
        attribute_name: Optional[str] = None,
    ) -> AsyncGenerator[dict, None]:
        """Open a GraphQL WebSocket subscription and yield raw event dicts.

        Uses the graphql-ws protocol (Strawberry's default).
        """
        import websockets

        ws_url = self._gateway_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/graphql"

        attr_arg = f', attributeName: "{attribute_name}"' if attribute_name else ""
        query = (
            "subscription { attributeChanged("
            f'assetId: "{asset_id}"{attr_arg}'
            ") { assetId attributeName value timestamp } }"
        )

        async with websockets.connect(
            ws_url,
            subprotocols=["graphql-transport-ws"],
        ) as ws:
            # graphql-transport-ws handshake
            await ws.send(json.dumps({"type": "connection_init", "payload": {}}))
            await ws.recv()  # connection_ack

            await ws.send(json.dumps({
                "id":      "1",
                "type":    "subscribe",
                "payload": {"query": query},
            }))

            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("type") == "next":
                    data = msg.get("payload", {}).get("data", {}).get("attributeChanged")
                    if data:
                        yield data
                elif msg.get("type") == "error":
                    log.error("GraphQL subscription error: %s", msg)
                    break
                elif msg.get("type") == "complete":
                    break
