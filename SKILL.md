# BMS Gateway — Agent Skill Reference

A GraphQL gateway over an OpenRemote IoT platform running a simulated smart building.
Use this skill to read live sensor data, control devices, and subscribe to real-time events.

## Endpoint

```
http://localhost:8000/graphql          # HTTP queries & mutations
ws://localhost:8000/graphql            # WebSocket subscriptions (graphql-transport-ws)
GET http://localhost:8000/health       # Liveness check
```

No authentication is required on the gateway itself. It authenticates to OpenRemote internally.

---

## Building Layout

```
OpenRemote HQ  (BuildingAsset)
├── Floor 1  (FloorAsset)
│   ├── Office A        (ThingAsset)
│   │   ├── Office A – Lighting       (LightAsset)
│   │   ├── Office A – HVAC           (ThingAsset)
│   │   ├── Office A – Network Switch  (ThingAsset)
│   │   └── Office A – Printer        (ThingAsset)
│   ├── Office B        (same structure)
│   ├── Meeting Room    (same structure)
│   └── Server Room     (same structure)
└── Floor 2  (FloorAsset)
    └── (same 4 rooms × 4 devices)
```

Asset names use an **en-dash** separator: `"Office A – HVAC"` (U+2013, not a hyphen).

---

## Agent Workflow Pattern

Always follow this sequence when controlling devices:

1. **Discover** — call `{ assets { id name type parentId } }` to get current asset IDs. Never hardcode IDs; seed.py may have run multiple times producing duplicate names.
2. **Filter** — select assets by `type` and `parentId` chain to stay in the correct building/floor.
3. **Read** — query current attribute values before deciding what to write (e.g. don't turn off lights that are already off).
4. **Write** — use `writeAttributes` for multi-attribute updates (one round-trip per asset). Use `writeAttribute` for single targeted writes.
5. **Verify** — re-query the changed attributes to confirm the write succeeded.

```python
# Minimal agent pattern via GraphQL
import httpx

GQL = "http://localhost:8000/graphql"

def gql(query, variables=None):
    r = httpx.post(GQL, json={"query": query, "variables": variables or {}})
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(data["errors"])
    return data["data"]

# 1. Discover
assets = gql("{ assets { id name type } }")["assets"]
lights = [a for a in assets if a["type"] == "LightAsset"]

# 2. Read current state
for light in lights:
    detail = gql('{ asset(id: "%s") { attributes { name value } } }' % light["id"])
    attrs = {a["name"]: a["value"] for a in detail["asset"]["attributes"]}
    print(light["name"], "onOff=", attrs.get("onOff"))

# 3. Write (batch)
events = [{"assetId": l["id"], "attributeName": "onOff", "value": False} for l in lights]
gql("""
mutation TurnOff($events: [AttributeEventInput!]!) {
  writeAttributes(events: $events)
}
""", {"events": events})
```

---

## Queries

### List all assets

```graphql
{
  assets {
    id
    name
    type
    parentId
  }
}
```

### Get a single asset with live attribute values

```graphql
{
  asset(id: "ASSET_ID") {
    id
    name
    type
    parentId
    attributes {
      name
      type
      value
      timestamp
    }
  }
}
```

`timestamp` on queried attributes is **Unix milliseconds** (ms since epoch).

`asset(id:)` returns `null` (not an error) when the ID does not exist. Always null-check
`data.asset` before accessing its fields.

---

## Asset IDs (first seeded building)

> **Warning — duplicate buildings:** If `seed.py` has been run more than once, the system
> contains multiple buildings with identical names (`"OpenRemote HQ"`, `"Office A"`, etc.).
> Always look up IDs at runtime with `{ assets { id name parentId } }` and filter by
> `parentId` to stay in the correct building. The IDs below are from the first seed run.

Use `{ assets { id name } }` to discover IDs at runtime. The simulator continuously
updates the first seeded building. Reference IDs from that run:

| Asset | ID |
|---|---|
| OpenRemote HQ | `44M1MqIAqZO63JgwOjn9ED` |
| Floor 1 | `5Pzj7HWLJCyG1qocyaJsq7` |
| Office A | `57TkgwOJmE0Pu1nJ4xkfFP` |
| Office A – HVAC | `5511GO9B6UCDT79TVIwPv7` |
| Office A – Lighting | `7OBufgFtmfK2GaIjo7ew8l` |
| Office A – Network Switch | `5F26VgAohUkni6eRWZgwJj` |
| Office A – Printer | `2arkTUO7KLePGhbuU3aAo7` |
| Office B | `3TMbJYofzwoXH9DL3wRwLo` |
| Office B – HVAC | `6mmpXAF4iF11DfegyqOiXt` |
| Office B – Lighting | `60bqeOHliloyVuzyktbXYL` |
| Office B – Network Switch | `2g61JsJsABvDPuAKGYKTRu` |
| Office B – Printer | `2lEeCfpqMZD2JoLimhDHB7` |
| Meeting Room | `4GblRVHHekwGdwCTrwuMyj` |
| Meeting Room – HVAC | `3v9kB6exlgCcy3Sahlke5L` |
| Meeting Room – Lighting | `2tEkHY7IknVnO8cnc47YBb` |
| Meeting Room – Network Switch | `7h9IGjVILI2dfvbtmDof2h` |
| Meeting Room – Printer | `7lztBqN4nthUO1PqaNZUwx` |
| Server Room | `46lETGaguWHc8yqM4vgpSe` |
| Server Room – HVAC | `7UXCuImnGkTq75ApMYZgWZ` |
| Server Room – Lighting | `6BvZQSSxE65SW5TsqKePbl` |
| Server Room – Network Switch | `4NyKC3nZtwpFvbbvFAdm9l` |
| Server Room – Printer | `2n9E0pFA2RcmXMRJSzHn9Y` |
| Floor 2 | `4e088zwdIynyuRur6OzgIP` |

Floor 2 rooms follow the same naming pattern; query `{ assets { id name } }` to get their IDs.

---

## Device Attributes

### HVAC (`"… – HVAC"`)

| Attribute | Type | Description | Writable |
|---|---|---|---|
| `currentTemperature` | number | °C, live sensor reading | no |
| `temperatureSetpoint` | number | Target temperature °C | **yes** |
| `hvacMode` | text | `"heating"` \| `"cooling"` \| `"off"` | **yes** |
| `humidity` | number | % relative humidity | no |
| `powerConsumption` | number | kW | no |
| `status` | text | `"running"` \| `"idle"` | no |
| `manufacturer` | text | `"Daikin"` | no |
| `model` | text | `"FTXM35R"` | no |

### Lighting (`"… – Lighting"`)

| Attribute | Type | Description | Writable |
|---|---|---|---|
| `onOff` | boolean | `true` = on | **yes** |
| `brightness` | positiveInteger | 0–100 % | **yes** |
| `colourTemperature` | positiveInteger | Kelvin (warm ~2700, cool ~6500) | **yes** |
| `colourRGB` | colourRGB | RGB object e.g. `{"r": 255, "g": 220, "b": 100}` | **yes** |

**Note:** British spelling — `colourTemperature`, `colourRGB` (not `color*`).
`colourRGB` values are RGB objects `{"r": R, "g": G, "b": B}`, **not** hex strings.
When writing via GraphQL, pass the object as a variable (not an inline literal):
```graphql
mutation SetColour($v: JSON!) {
  writeAttribute(assetId: "ASSET_ID", attribute: "colourRGB", value: $v)
}
```
Variables: `{"v": {"r": 255, "g": 220, "b": 100}}`

### Network Switch (`"… – Network Switch"`)

| Attribute | Type | Description | Writable |
|---|---|---|---|
| `activePorts` | positiveInteger | Currently active ports (live) | no |
| `totalPorts` | positiveInteger | Total port count | no |
| `status` | text | `"online"` \| `"offline"` | no |
| `uptime` | text | Human-readable uptime e.g. `"43d 3h 17m"` | no |
| `ipAddress` | text | Management IP e.g. `"10.1.1.1"` | no |
| `manufacturer` | text | `"Cisco"` | no |
| `model` | text | `"Catalyst 2960-24TT"` | no |
| `firmwareVersion` | text | e.g. `"12.2(58)SE2"` | no |

IP scheme: switches at `10.{floor}.{room_index}.1` (floor 1 = `10.1.*`, floor 2 = `10.2.*`; room index 1–4 for Office A / B / Meeting Room / Server Room).

### Printer (`"… – Printer"`)

| Attribute | Type | Description | Writable |
|---|---|---|---|
| `tonerLevel` | number | % remaining (resets to 100 at ≤5%) | no |
| `pagesPrinted` | number | Cumulative page count (live) | no |
| `status` | text | `"ready"` \| `"offline"` \| `"error"` | no |
| `ipAddress` | text | Management IP e.g. `"10.1.1.50"` | no |
| `manufacturer` | text | `"HP"` | no |
| `model` | text | `"LaserJet Pro M404dn"` | no |
| `paperLevel` | text | `"OK"` | no |
| `serialNumber` | text | e.g. `"VNB3K1X7842"` | no |

Printer `status` is `"offline"` outside work hours (before 07:00, after 20:00),
`"error"` when toner ≤ 5%, `"ready"` otherwise.

IP scheme: printers at `10.{floor}.{room_index}.50`.

---

## Mutations

> **Error handling:** GraphQL does not use HTTP 4xx for mutation failures. A failed write
> returns HTTP 200 with `data.writeAttribute = null` and a non-empty `errors` array.
> Always check `response["errors"]` before assuming success.

### Write a single attribute

> **Argument name:** `writeAttribute` uses **`attribute`** (not `attributeName`).

```graphql
mutation {
  writeAttribute(
    assetId: "5511GO9B6UCDT79TVIwPv7",
    attribute: "hvacMode",
    value: "cooling"
  )
}
```

Returns `true` on success, `null` on failure (check `errors`).

### Write multiple attributes in one call

> **Argument name:** `writeAttributes` input type uses **`attributeName`** (not `attribute`).
> These two mutations use different argument names — do not mix them.

```graphql
mutation {
  writeAttributes(events: [
    { assetId: "7OBufgFtmfK2GaIjo7ew8l", attributeName: "onOff",      value: false },
    { assetId: "7OBufgFtmfK2GaIjo7ew8l", attributeName: "brightness", value: 50 }
  ])
}
```

Returns `true` on success. Groups writes by asset internally — efficient for multi-attribute updates.

### Create an asset

```graphql
mutation {
  createAsset(input: {
    name: "New Sensor",
    type: "ThingAsset",
    parentId: "57TkgwOJmE0Pu1nJ4xkfFP",
    attributes: [
      { name: "notes", type: "text", value: "Test device" }
    ]
  }) {
    id
    name
  }
}
```

---

## Subscriptions (real-time)

Subscriptions use WebSocket with the `graphql-transport-ws` subprotocol.

`timestamp` on subscription events is **Unix milliseconds** (same unit as queried attributes).

### Subscribe to all attribute changes

```graphql
subscription {
  attributeChanged {
    assetId
    attributeName
    value
    timestamp
  }
}
```

### Filter by asset

```graphql
subscription {
  attributeChanged(assetId: "5511GO9B6UCDT79TVIwPv7") {
    assetId
    attributeName
    value
    timestamp
  }
}
```

### Filter by asset and attribute name

```graphql
subscription {
  attributeChanged(
    assetId: "5511GO9B6UCDT79TVIwPv7",
    attributeName: "currentTemperature"
  ) {
    assetId
    attributeName
    value
    timestamp
  }
}
```

---

## Python Examples

### Query — read live temperature

```python
import httpx

resp = httpx.post("http://localhost:8000/graphql", json={"query": """
{
  asset(id: "5511GO9B6UCDT79TVIwPv7") {
    attributes { name value }
  }
}
"""})
data = resp.json()
if data.get("errors"):
    raise RuntimeError(data["errors"])
asset = data["data"]["asset"]
if asset is None:
    raise RuntimeError("Asset not found")
attrs = {a["name"]: a["value"] for a in asset["attributes"]}
print(attrs["currentTemperature"])  # e.g. 22.9
```

### Mutation — set HVAC mode

```python
import httpx

resp = httpx.post("http://localhost:8000/graphql", json={"query": """
mutation {
  writeAttribute(
    assetId: "5511GO9B6UCDT79TVIwPv7",
    attribute: "hvacMode",
    value: "off"
  )
}
"""})
data = resp.json()
if data.get("errors") or not data["data"]["writeAttribute"]:
    raise RuntimeError(data.get("errors"))
```

### Subscription — stream temperature changes

```python
import asyncio, json, websockets

async def watch():
    async with websockets.connect(
        "ws://localhost:8000/graphql",
        subprotocols=["graphql-transport-ws"],
    ) as ws:
        await ws.send(json.dumps({"type": "connection_init", "payload": {}}))
        await ws.recv()  # connection_ack

        await ws.send(json.dumps({
            "id": "1",
            "type": "subscribe",
            "payload": {
                "query": """
                subscription {
                  attributeChanged(
                    assetId: "5511GO9B6UCDT79TVIwPv7",
                    attributeName: "currentTemperature"
                  ) { value timestamp }
                }
                """
            }
        }))

        async for msg in ws:
            data = json.loads(msg)
            if data["type"] == "next":
                print(data["payload"]["data"]["attributeChanged"]["value"])

asyncio.run(watch())
```

---

## Higher-Level Python SDK

If running in the same Python environment, import the `BMSClient` for a cleaner interface:

```python
import asyncio
from bms import BMSClient

async def main():
    async with BMSClient() as bms:
        # Discover what rooms exist
        rooms = await bms.list_rooms()  # ["Office A", "Office B", ...]

        # Full building snapshot
        building = await bms.get_building()
        for room in building.rooms:
            print(room.name, room.floor, room.hvac.current_temp, room.hvac.mode)

        # Single room
        room = await bms.get_room("Office A")
        print(room.light.on, room.light.brightness)

        # Control lighting (pass only the fields you want to change)
        await bms.set_light("Office A", on=False)
        await bms.set_light("Meeting Room", brightness=80, colour_temp=4000)

        # Control HVAC
        await bms.set_hvac("Server Room", mode="cooling", setpoint=19.0)
        await bms.set_hvac("Office B", mode="off")

        # Low-level escape hatch for any attribute (including colourRGB)
        await bms.write_device_attribute(
            "Office A", "Lighting", "colourRGB", {"r": 255, "g": 220, "b": 100}
        )

        # Real-time streams
        async for temp in bms.watch_temperature("Office A"):
            print("temp:", temp)          # yields float °C on every change

        async for event in bms.watch_room("Office B"):
            # event.device: "hvac" | "light" | "network" | "printer"
            print(event.device, event.attribute, event.value)

asyncio.run(main())
```

**BMSClient method reference**

| Method | Returns | Description |
|---|---|---|
| `list_rooms()` | `list[str]` | All unique room names |
| `get_room(name)` | `Room` | Snapshot of one room (all 4 devices) |
| `get_building()` | `BuildingState` | Full building snapshot |
| `set_light(room, *, on, brightness, colour_temp)` | — | Set any lighting fields (omit unchanged) |
| `set_hvac(room, *, mode, setpoint)` | — | Set HVAC mode and/or setpoint |
| `write_device_attribute(room, device, attribute, value)` | — | Write any attribute by name (escape hatch) |
| `watch_temperature(room)` | `AsyncGenerator[float]` | Stream live °C readings |
| `watch_room(room)` | `AsyncGenerator[RoomEvent]` | Stream all attribute changes in a room |

`device` argument for `write_device_attribute`: `"HVAC"`, `"Lighting"`, `"Network Switch"`, `"Printer"`.

---

## Scenarios (pre-built building states)

Apply named scenarios to put the building in a specific state for testing:

```bash
make scenario SCENARIO=summer_heat      # high temps, HVAC cooling
make scenario SCENARIO=after_hours      # lights off, HVAC off, printers offline
make scenario SCENARIO=energy_crisis    # lights max, HVAC extreme setpoints
make scenario SCENARIO=printer_emergency # Office A printer toner=3%, status=error
make scenario SCENARIO=normal           # nominal working-day values
```

Or from Python:

```python
import asyncio
from bms import BMSClient
from scenarios import apply_scenario, list_scenarios

async def main():
    print(list_scenarios())  # ["normal", "summer_heat", "after_hours", "energy_crisis", "printer_emergency"]
    async with BMSClient() as bms:
        await apply_scenario(bms, "summer_heat")

asyncio.run(main())
```

---

## Simulator

Live data is generated by a background simulator writing to all 8 rooms (2 floors × 4 rooms)
every 5 seconds. It models realistic diurnal patterns (temperature, occupancy, lighting,
printer usage). The simulator must be running for attribute values to change over time.

```bash
make sim-start    # start in background
make sim-status   # check PID + last 5 log lines
make sim-logs     # tail live log
make sim-stop     # stop
```

---

## Dashboards

The gateway exposes full dashboard CRUD via GraphQL. Dashboards appear in the OpenRemote UI
under **Insights**.

### Widget type IDs

| `widgetTypeId` | Purpose | Key `widgetConfig` fields |
|---|---|---|
| `"gauge"` | Circular gauge / meter | `attributeRefs`, `thresholds: [[num, color]]`, `min`, `max`, `decimals` |
| `"attributeinput"` | Show & control a single value | `attributeRefs` |
| `"kpi"` | Value + delta vs. time period | `attributeRefs`, `period` (year/month/week/day/hour), `decimals`, `deltaFormat` (absolute/percentage) |
| `"linechart"` | Time-series line chart | `attributeRefs`, `attributeColors`, `showTimestampControls`, `showLegend`, `showZoomBar`, `stacked` |
| `"barchart"` | Bar chart | same shape as linechart |
| `"table"` | Multi-asset attribute table | `assetIds`, `attributeNames`, `tableSize` |
| `"map"` | Live asset map | `attributeRefs` |
| `"image"` | Static image with overlays | `imageData`, `markers` |
| `"gateway"` | Edge gateway tunnel button | `gatewayId` |

`widgetConfig` is a free-form JSON object — only `attributeRefs` is needed for most widgets.
Omitted config fields fall back to widget defaults.

`refreshInterval` values: `"OFF"`, `"ONE_MIN"`, `"FIVE_MIN"`, `"QUARTER"`, `"ONE_HOUR"`.

`access` values: `"PUBLIC"`, `"SHARED"`, `"PRIVATE"`.

### Query — list and inspect dashboards

```graphql
{
  dashboards {
    id
    displayName
    access
    template {
      refreshInterval
      widgets {
        id
        displayName
        widgetTypeId
        gridItem { x y w h }
        widgetConfig
      }
    }
  }
}
```

```graphql
{
  dashboard(id: "DASHBOARD_ID") {
    id
    displayName
    template {
      widgets { id displayName widgetTypeId widgetConfig }
    }
  }
}
```

### Mutation — create a dashboard

```graphql
mutation {
  createDashboard(input: {
    displayName: "Building Overview",
    access: "SHARED",
    refreshInterval: "FIVE_MIN",
    widgets: [
      {
        displayName: "Office A – Temp",
        widgetTypeId: "gauge",
        gridItem: { x: 0, y: 0, w: 3, h: 3 },
        widgetConfig: {
          attributeRefs: [{ id: "ASSET_ID", name: "currentTemperature" }]
        }
      },
      {
        displayName: "Office A – Lighting",
        widgetTypeId: "attributeinput",
        gridItem: { x: 3, y: 0, w: 3, h: 3 },
        widgetConfig: {
          attributeRefs: [{ id: "ASSET_ID", name: "onOff" }]
        }
      }
    ]
  }) {
    id
    displayName
  }
}
```

### Mutation — update a dashboard (partial)

```graphql
mutation {
  updateDashboard(input: {
    id: "DASHBOARD_ID",
    displayName: "New Title",
    refreshInterval: "ONE_MIN"
  }) {
    id
    displayName
  }
}
```

Pass `widgets: [...]` to fully replace the widget list.

### Mutation — delete a dashboard

```graphql
mutation {
  deleteDashboard(id: "DASHBOARD_ID")
}
```

Returns `true` on success.
