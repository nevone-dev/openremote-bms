#!/usr/bin/env python3
"""
OpenRemote mock data seed script.
Creates: Building > Floor 1 & 2 > Offices (A, B, Meeting Room, Server Room)
Each office gets: Lighting, HVAC, Network Switch, Printer
"""

import json
import sys
import time
import urllib.request
import urllib.parse
import ssl

BASE = "https://localhost"
REALM = "master"
NOW = int(time.time() * 1000)

# Skip SSL verification (self-signed cert)
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def http(method, path, body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, context=CTX) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def get_token():
    url = f"{BASE}/auth/realms/{REALM}/protocol/openid-connect/token"
    data = urllib.parse.urlencode({
        "grant_type": "password",
        "client_id": "openremote",
        "username": "admin",
        "password": "secret",
    }).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"},
                                 method="POST")
    with urllib.request.urlopen(req, context=CTX) as r:
        return json.loads(r.read())["access_token"]


def create_asset(token, asset):
    result = http("POST", f"/api/{REALM}/asset", asset, token)
    if "id" not in result:
        print("ERROR:", json.dumps(result, indent=2), file=sys.stderr)
        sys.exit(1)
    return result["id"]


def attr(name, typ, value):
    return {name: {"name": name, "type": typ, "meta": {}, "value": value, "timestamp": NOW}}


def text(name, value):  return attr(name, "text", value)
def num(name, value):   return attr(name, "number", value)
def integer(name, v):   return attr(name, "positiveInteger", v)
def boolean(name, v):   return attr(name, "boolean", v)
def location(lon, lat): return attr("location", "GEO_JSONPoint",
                                    {"type": "Point", "coordinates": [lon, lat]})


def merge(*dicts):
    out = {}
    for d in dicts:
        out.update(d)
    return out


# ─── Auth ─────────────────────────────────────────────────────────────────────
print("Getting access token...")
TOKEN = get_token()

# ─── Building ─────────────────────────────────────────────────────────────────
print("Creating Building: OpenRemote HQ...")
building_id = create_asset(TOKEN, {
    "name": "OpenRemote HQ",
    "type": "BuildingAsset",
    "realm": REALM,
    "attributes": merge(
        text("street", "1 Innovation Drive"),
        text("city", "Amsterdam"),
        text("country", "Netherlands"),
        text("postalCode", "1012 AB"),
        text("notes", "Main headquarters building"),
        integer("area", 2000),
        location(4.9041, 52.3676),
    ),
})
print(f"  -> Building ID: {building_id}")

# ─── Floors & Rooms ───────────────────────────────────────────────────────────
OFFICES = ["Office A", "Office B", "Meeting Room", "Server Room"]

for floor_num in [1, 2]:
    print(f"\nCreating Floor {floor_num}...")
    floor_id = create_asset(TOKEN, {
        "name": f"Floor {floor_num}",
        "type": "FloorAsset",
        "realm": REALM,
        "parentId": building_id,
        "attributes": merge(
            integer("floorLevel", floor_num),
            integer("area", 800),
            text("notes", f"Office floor {floor_num}"),
            location(4.9041, 52.3676),
        ),
    })
    print(f"  -> Floor {floor_num} ID: {floor_id}")

    ip_octet = 1

    for room in OFFICES:
        print(f"\n  Room: {room} (Floor {floor_num})")

        # Room container
        room_id = create_asset(TOKEN, {
            "name": room,
            "type": "ThingAsset",
            "realm": REALM,
            "parentId": floor_id,
            "attributes": merge(
                text("notes", f"{room} – Floor {floor_num}"),
                location(4.9041, 52.3676),
            ),
        })
        print(f"    Room ID: {room_id}")

        # Lighting
        light_id = create_asset(TOKEN, {
            "name": f"{room} – Lighting",
            "type": "LightAsset",
            "realm": REALM,
            "parentId": room_id,
            "attributes": merge(
                boolean("onOff", True),
                num("brightness", 80),
                integer("colourTemperature", 4000),
                attr("colourRGB", "ColourRGB", {"r": 255, "g": 255, "b": 220}),
                text("notes", "LED panel ceiling lights"),
                location(4.9041, 52.3676),
            ),
        })
        print(f"    Lighting  : {light_id}")

        # HVAC
        hvac_id = create_asset(TOKEN, {
            "name": f"{room} – HVAC",
            "type": "ThingAsset",
            "realm": REALM,
            "parentId": room_id,
            "attributes": merge(
                text("notes", "Ceiling-mounted HVAC unit"),
                num("currentTemperature", round(21.0 + floor_num * 0.5 + OFFICES.index(room) * 0.3, 1)),
                num("temperatureSetpoint", 21.5),
                num("humidity", 45 + floor_num),
                num("powerConsumption", 1.2),
                text("hvacMode", "cooling"),
                text("status", "running"),
                text("manufacturer", "Daikin"),
                text("model", "FTXM35R"),
                location(4.9041, 52.3676),
            ),
        })
        print(f"    HVAC      : {hvac_id}")

        # Network Switch
        ip_switch = f"10.{floor_num}.{ip_octet}.1"
        net_id = create_asset(TOKEN, {
            "name": f"{room} – Network Switch",
            "type": "ThingAsset",
            "realm": REALM,
            "parentId": room_id,
            "attributes": merge(
                text("notes", "24-port managed Gigabit switch"),
                text("manufacturer", "Cisco"),
                text("model", "Catalyst 2960-24TT"),
                text("ipAddress", ip_switch),
                integer("activePorts", 8 + OFFICES.index(room)),
                integer("totalPorts", 24),
                text("uptime", f"{42 + floor_num}d 3h 17m"),
                text("status", "online"),
                text("firmwareVersion", "12.2(58)SE2"),
                location(4.9041, 52.3676),
            ),
        })
        print(f"    Net Switch : {net_id}  ({ip_switch})")

        # Printer
        ip_printer = f"10.{floor_num}.{ip_octet}.50"
        prn_id = create_asset(TOKEN, {
            "name": f"{room} – Printer",
            "type": "ThingAsset",
            "realm": REALM,
            "parentId": room_id,
            "attributes": merge(
                text("notes", "Network laser printer"),
                text("manufacturer", "HP"),
                text("model", "LaserJet Pro M404dn"),
                text("ipAddress", ip_printer),
                text("status", "ready"),
                num("tonerLevel", 74 - OFFICES.index(room) * 5),
                integer("pagesPrinted", 13842 + floor_num * 1000 + OFFICES.index(room) * 250),
                text("paperLevel", "OK"),
                text("serialNumber", f"VNB3K{floor_num}{OFFICES.index(room)}7842"),
                location(4.9041, 52.3676),
            ),
        })
        print(f"    Printer    : {prn_id}  ({ip_printer})")

        ip_octet += 1

print("\n" + "="*60)
print("All mock data created successfully!")
print("Visit https://localhost and log in with admin / secret")
print("="*60)
