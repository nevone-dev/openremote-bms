#!/usr/bin/env python3
"""
OpenRemote dashboard creation script.
1. Enables storeDataPoints on key attributes (so widgets have historical data)
2. Creates a "Building Overview" dashboard with gauges and attribute widgets
"""

import json
import sys
import ssl
import urllib.request
import urllib.parse

BASE = "https://localhost"
REALM = "master"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

ROOMS = ["Office A", "Office B", "Meeting Room", "Server Room"]

# Which attributes to enable data point storage on, per device type
STORE_DATA_ATTRS = {
    "HVAC":     ["currentTemperature", "humidity", "powerConsumption"],
    "Lighting": ["brightness", "onOff", "colourTemperature"],
    "Printer":  ["tonerLevel", "pagesPrinted"],
}


# ─── HTTP helpers ─────────────────────────────────────────────────────────────

def get_token():
    url = f"{BASE}/auth/realms/{REALM}/protocol/openid-connect/token"
    data = urllib.parse.urlencode({
        "grant_type": "password",
        "client_id":  "openremote",
        "username":   "admin",
        "password":   "secret",
    }).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, context=CTX) as r:
        return json.loads(r.read())["access_token"]


def http(method, path, body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=CTX) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, (json.loads(raw) if raw else {})
        except json.JSONDecodeError:
            return e.code, raw.decode("utf-8", errors="replace")


# ─── Asset helpers ─────────────────────────────────────────────────────────────

def query_all_assets(token):
    _, assets = http("POST", f"/api/{REALM}/asset/query", {}, token)
    return assets


def enable_store_data_points(token, assets):
    """
    For each HVAC, Lighting, and Printer asset, add storeDataPoints=true
    to the specified attributes so the dashboard widgets have data to plot.
    """
    by_name = {a["name"]: a for a in assets}

    print("\nEnabling storeDataPoints on asset attributes...")
    for floor in [1, 2]:
        for room in ROOMS:
            for device_suffix, attr_names in STORE_DATA_ATTRS.items():
                asset_name = f"{room} \u2013 {device_suffix}"  # en-dash, matches seed.py
                asset = by_name.get(asset_name)
                if not asset:
                    print(f"  WARNING: not found: {asset_name}", file=sys.stderr)
                    continue

                asset_id = asset["id"]
                status, full = http("GET", f"/api/{REALM}/asset/{asset_id}", token=token)
                if status != 200:
                    print(f"  ERROR: GET {asset_name} -> {status}", file=sys.stderr)
                    continue

                attrs = full.get("attributes", {})
                changed = False
                for attr_name in attr_names:
                    if attr_name not in attrs:
                        continue
                    meta = attrs[attr_name].get("meta") or {}
                    if not meta.get("storeDataPoints"):
                        meta["storeDataPoints"] = True
                        attrs[attr_name]["meta"] = meta
                        changed = True

                if not changed:
                    print(f"  - already set: {asset_name}")
                    continue

                full["attributes"] = attrs
                status, result = http("PUT", f"/api/{REALM}/asset/{asset_id}", full, token)
                if status == 200:
                    print(f"  ✓ {asset_name}")
                else:
                    print(f"  ✗ {asset_name}: {status} {result}", file=sys.stderr)


# ─── Widget builder ─────────────────────────────────────────────────────────────

_wid = 0

GAUGE_CONFIG_DEFAULTS = {
    "thresholds": [[0, "#4caf50"], [75, "#ff9800"], [90, "#ef5350"]],
    "decimals": 0,
    "min": 0,
    "max": 100,
    "valueType": "number",
    "showUnits": False,
}
ATTRINPUT_CONFIG_DEFAULTS = {
    "readonly": False,
    "showHelperText": True,
}


def widget(display_name, widget_type, asset_id, attr_name, x, y, w=3, h=3):
    global _wid
    _wid += 1
    if widget_type == "gauge":
        extra = GAUGE_CONFIG_DEFAULTS
    elif widget_type == "attributeinput":
        extra = ATTRINPUT_CONFIG_DEFAULTS
    else:
        extra = {}
    return {
        "id": f"w{_wid}",
        "displayName": display_name,
        "widgetTypeId": widget_type,
        "gridItem": {
            "x": x, "y": y, "w": w, "h": h,
            "minH": 2, "minW": 2,
            "noResize": False, "noMove": False, "locked": False,
        },
        "widgetConfig": {
            "attributeRefs": [{"id": asset_id, "name": attr_name}],
            **extra,
        },
    }


def build_widgets(by_name):
    widgets = []
    y = 0

    for floor in [1, 2]:
        # Row: Temperature gauges
        for i, room in enumerate(ROOMS):
            hvac_id = by_name.get(f"{room} \u2013 HVAC")
            if hvac_id:
                widgets.append(widget(
                    f"F{floor} {room}\nTemperature", "gauge",
                    hvac_id, "currentTemperature",
                    x=i * 3, y=y,
                ))
        y += 3

        # Row: Lighting on/off attribute widgets
        for i, room in enumerate(ROOMS):
            light_id = by_name.get(f"{room} \u2013 Lighting")
            if light_id:
                widgets.append(widget(
                    f"F{floor} {room}\nLighting", "attributeinput",
                    light_id, "onOff",
                    x=i * 3, y=y,
                ))
        y += 3

        # Row: Humidity gauges
        for i, room in enumerate(ROOMS):
            hvac_id = by_name.get(f"{room} \u2013 HVAC")
            if hvac_id:
                widgets.append(widget(
                    f"F{floor} {room}\nHumidity", "gauge",
                    hvac_id, "humidity",
                    x=i * 3, y=y,
                ))
        y += 3

    # Final row: Printer toner levels (Floor 1 only — 4 rooms fit in 12 cols)
    for i, room in enumerate(ROOMS):
        prn_id = by_name.get(f"{room} \u2013 Printer")
        if prn_id:
            widgets.append(widget(
                f"F1 {room}\nToner", "gauge",
                prn_id, "tonerLevel",
                x=i * 3, y=y,
            ))
    y += 3

    return widgets


# ─── Dashboard creation ────────────────────────────────────────────────────────

def create_dashboard(token, widgets):
    # screenPresets must be non-empty: Jackson strips empty arrays (WRITE_EMPTY_JSON_ARRAYS=false),
    # causing the frontend to receive undefined and crash on .sort()
    payload = {
        "realm": REALM,
        "displayName": "Building Overview",
        "access": "PUBLIC",
        "template": {
            "columns": 12,
            "maxScreenWidth": 1920,
            "refreshInterval": "FIVE_MIN",
            "screenPresets": [
                {"id": "default", "displayName": "Default", "breakpoint": 1920, "scalingPreset": "KEEP_LAYOUT"}
            ],
            "widgets": widgets,
        },
    }
    status, result = http("POST", f"/api/{REALM}/dashboard", payload, token)
    if status not in (200, 201, 204) or "id" not in result:
        print(f"ERROR creating dashboard: {status}", file=sys.stderr)
        print(json.dumps(result, indent=2), file=sys.stderr)
        sys.exit(1)
    return result["id"]


# ─── Main ──────────────────────────────────────────────────────────────────────

print("Getting access token...")
TOKEN = get_token()

print("Querying assets...")
all_assets = query_all_assets(TOKEN)
print(f"  Found {len(all_assets)} assets")

# Enable data point storage on key attributes
enable_store_data_points(TOKEN, all_assets)

# Build name→id lookup (filter to the real building's assets only)
# Use floor-qualified names to avoid ambiguity across duplicate buildings
by_name = {a["name"]: a["id"] for a in all_assets}

print("\nBuilding widget layout...")
widgets = build_widgets(by_name)
print(f"  {len(widgets)} widgets created")

print("\nCreating dashboard...")
dash_id = create_dashboard(TOKEN, widgets)

print(f"\n{'='*60}")
print(f"Dashboard created: {dash_id}")
print(f"Visit https://localhost → Insights tab to view it")
print(f"{'='*60}")
