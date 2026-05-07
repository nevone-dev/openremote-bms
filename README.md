# OpenRemote Smart-Office BMS

A local [OpenRemote](https://openremote.io) IoT platform simulation with a full smart-building asset hierarchy, a live sensor simulator, a GraphQL gateway, and a Python SDK for AI agent integration.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Docker Compose Stack                                   │
│                                                         │
│  proxy (HAProxy, 443) ──► manager (OpenRemote)         │
│                      ──► keycloak (Auth)               │
│                      ──► postgresql (DB)               │
│                      ──► gateway (FastAPI + GraphQL)   │
└─────────────────────────────────────────────────────────┘
        │
        │  REST / MQTT / WebSocket
        ▼
┌──────────────────┐    ┌─────────────────────┐
│  BMS Python SDK  │    │  Simulator          │
│  (bms/)          │    │  (simulator/)       │
│                  │    │  Writes live sensor │
│  AI-agent-ready  │    │  data every N secs  │
└──────────────────┘    └─────────────────────┘
```

### Asset Hierarchy

```
OpenRemote HQ (BuildingAsset)
├── Floor 1 (FloorAsset)
│   ├── Office A (ThingAsset)
│   │   ├── Office A – Lighting (LightAsset)
│   │   ├── Office A – HVAC (ThingAsset)
│   │   ├── Office A – Network Switch (ThingAsset)
│   │   └── Office A – Printer (ThingAsset)
│   ├── Office B   (same structure)
│   ├── Meeting Room  (same structure)
│   └── Server Room   (same structure)
└── Floor 2 (FloorAsset)
    └── (same 4 rooms × 4 devices)
```

## Quick Start

```bash
# One-time setup: start stack, fix auth, seed asset tree
make bootstrap

# The UI is now at https://localhost  (admin / secret)
# GraphQL gateway is at http://localhost:8000/graphql
```

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make bootstrap` | First-time setup: `up` + `auth-fix` + `seed` |
| `make up` | Start Docker stack, wait until gateway is healthy |
| `make down` | Stop and remove containers |
| `make logs` | Tail all container logs |
| `make status` | Container status + gateway `/health` JSON |
| `make seed` | Populate OpenRemote with the mock asset tree |
| `make auth-fix` | Enable direct-access grants on the Keycloak `openremote` client |
| `make sim` | Run the sensor simulator in the foreground (`TICK=5`) |
| `make sim-start` | Start simulator in background |
| `make sim-stop` | Stop background simulator |
| `make gateway-dev` | Run gateway outside Docker with hot-reload |
| `make scenario SCENARIO=<name>` | Apply a named building state |
| `make clean` | Remove `.venv` and all `__pycache__` directories |

## Scenarios

Pre-defined building states for testing:

```bash
make scenario SCENARIO=normal            # Comfortable working day
make scenario SCENARIO=summer_heat       # Offices overheating, HVAC struggling
make scenario SCENARIO=after_hours       # Lights off, HVAC idle, printers offline
make scenario SCENARIO=energy_crisis     # All lights max, extreme HVAC setpoints
make scenario SCENARIO=printer_emergency # Office A toner at 3%, status=error
```

Or run directly:

```bash
python run_scenario.py summer_heat
```

## BMS Python SDK

`bms/` is a clean async Python SDK designed for AI agent use. It works entirely by asset **name**, not ID.

```python
from bms import BMSClient

async with BMSClient() as bms:
    # Read
    building = await bms.get_building()
    for room in building.rooms:
        print(room.name, room.hvac.current_temp, room.light.on)

    room = await bms.get_room("Office A")
    print(room.printer.toner_level)

    # Write
    await bms.set_light("Office A", on=True, brightness=80, colour_temp=4000)
    await bms.set_hvac("Office A", mode="cooling", setpoint=20.0)

    # Live subscriptions (requires gateway)
    async for temp in bms.watch_temperature("Office A"):
        print(f"Office A temp: {temp}°C")
```

## GraphQL Gateway

The gateway (`gateway/`) is a FastAPI + Strawberry GraphQL service that exposes:

- **Queries**: read asset state
- **Mutations**: write asset attributes
- **Subscriptions**: real-time attribute change events via WebSocket (backed by OpenRemote MQTT)

```
GET  http://localhost:8000/health
POST http://localhost:8000/graphql  (queries & mutations)
WS   ws://localhost:8000/graphql   (subscriptions)
```

Interactive GraphiQL explorer: [http://localhost:8000/graphql](http://localhost:8000/graphql)

## Simulator

`simulator/` continuously pushes realistic sensor readings to OpenRemote, cycling through time-of-day patterns (work hours vs after-hours) with per-room variation.

```bash
make sim          # foreground, TICK=5s
make sim-start    # background daemon
TICK=30 make sim  # slower tick
```

## Project Layout

```
.
├── bms/               Python SDK for AI agents
│   ├── client.py      BMSClient — high-level async API
│   ├── models.py      Pydantic models (Room, HVACReading, …)
│   └── _or_transport.py  Low-level REST + auth
├── gateway/           FastAPI + GraphQL service
│   ├── main.py        App factory, lifespan, health endpoint
│   ├── auth.py        Token refresh loop
│   ├── mqtt_bridge.py MQTT subscriber → event queue
│   ├── or_client.py   Async REST client
│   └── schema/        Strawberry types, queries, mutations, subscriptions
├── simulator/         Live sensor data generator
│   ├── sim.py         Main loop
│   ├── patterns.py    Time-of-day sensor curves
│   └── models.py      Simulator state models
├── scenarios/         Named building states for testing
│   └── scenarios.py
├── seed.py            Asset tree bootstrapper (REST API)
├── dashboard.py       Dashboard bootstrapper
├── run_scenario.py    CLI to apply a scenario
├── Dockerfile.gateway Container for the gateway
├── docker-compose.yml Stack definition
└── Makefile           All dev tasks
```

## Authentication

Scripts authenticate against Keycloak using the `openremote` client with direct access grants:

```
POST /auth/realms/master/protocol/openid-connect/token
  grant_type=password  client_id=openremote  username=admin  password=secret
```

`make auth-fix` enables direct access grants on the `openremote` client (required once after a fresh stack start).

## Notes

- The stack uses a **self-signed SSL certificate** — all scripts disable SSL verification.
- Deleting assets via the REST API returns 405; use the web UI at `https://localhost` instead.
- OpenRemote uses British spellings: `colourTemperature`, `colourRGB` (not `color*`).
- The HAProxy config forces **HTTP/1.1** on the HTTPS bind — this is required for the WebSocket/WAMP real-time connection; do not revert it.
- Dashboard `PUT` via the API returns 405 — update dashboards via SQL (`UPDATE dashboard SET template = ... WHERE id = ...`).
