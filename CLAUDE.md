# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a local OpenRemote IoT platform simulation. OpenRemote runs as a Docker Compose stack, and `seed.py` populates it with a mock smart-building asset hierarchy via the REST API.

## Running the Stack

```bash
cd /Users/nevo/open_remote
docker compose up -d          # start all services
docker compose down           # stop
docker compose logs -f manager  # tail manager logs
```

Services: `proxy` (443), `keycloak`, `postgresql`, `manager`. The UI is at https://localhost — log in with `admin` / `secret`.

## Seeding Mock Data

```bash
python3 seed.py
```

This creates the full asset tree via the OpenRemote REST API. It is idempotent in the sense that re-running it creates duplicate assets (there is no upsert — each run appends).

## Authentication

The scripts authenticate against Keycloak using `client_id=openremote` with direct access grants enabled. This was enabled manually via the Keycloak admin API (it is not the default). The `admin-cli` client also has direct access grants but its tokens are rejected by the OpenRemote Manager API with "role not allowed".

```python
POST /auth/realms/master/protocol/openid-connect/token
  grant_type=password
  client_id=openremote
  username=admin
  password=secret
```

## OpenRemote REST API

All asset operations go through:
```
POST   /api/master/asset       # create asset, returns full asset object with "id"
GET    /api/master/asset/{id}  # fetch asset
PUT    /api/master/asset/{id}  # update asset (DELETE returns 405 — use the UI instead)
```

### Attribute Schema

Every attribute must have this exact shape:
```json
{
  "attributeName": {
    "name": "attributeName",
    "type": "text|number|positiveInteger|boolean|GEO_JSONPoint|ColourRGB|...",
    "meta": {},
    "value": <value>,
    "timestamp": <unix_ms>
  }
}
```

### Asset Type Requirements

| Asset Type | Required Attributes |
|---|---|
| `BuildingAsset` | `street`, `city`, `country`, `postalCode`, `notes`, `area` (positiveInteger), `location` |
| `FloorAsset` | `floorLevel` (positiveInteger), `area` (positiveInteger), `notes`, `location` |
| `ThingAsset` | `notes`, `location` (others are optional) |
| `LightAsset` | `onOff` (boolean), `brightness` (number), `colourTemperature` (positiveInteger), `colourRGB` (ColourRGB), `notes`, `location` |

**Note British spellings**: `colourTemperature`, `colourRGB` — NOT `color*`.

Special value types:
- `GEO_JSONPoint`: `{"type": "Point", "coordinates": [lon, lat]}`
- `ColourRGB`: `{"r": 255, "g": 255, "b": 220}`

### Asset Hierarchy

```
OpenRemote HQ (BuildingAsset)
├── Floor 1 (FloorAsset)
│   ├── Office A (ThingAsset)
│   │   ├── Office A – Lighting (LightAsset)
│   │   ├── Office A – HVAC (ThingAsset)
│   │   ├── Office A – Network Switch (ThingAsset)
│   │   └── Office A – Printer (ThingAsset)
│   ├── Office B  (same structure)
│   ├── Meeting Room  (same structure)
│   └── Server Room  (same structure)
└── Floor 2 (FloorAsset)
    └── (same 4 rooms × 4 devices)
```

Network IP scheme: switches at `10.{floor}.{octet}.1`, printers at `10.{floor}.{octet}.50`.

## SSL

All scripts disable SSL verification (`ssl.CERT_NONE`) because the local stack uses a self-signed certificate. Never enable verification against localhost.

## Dashboard API

Dashboard CRUD paths (different from asset paths):
```
POST   /api/master/dashboard              # create, returns full dashboard with "id"
GET    /api/master/dashboard/master/{id}  # fetch by id (realm repeated in path)
PUT    /api/master/dashboard/master/{id}  # returns 405 — update via SQL instead
```

### Dashboard Widget Config

Every widget requires a `widgetConfig` with type-specific fields. Missing fields cause JS crashes (`TypeError: Cannot read properties of undefined`).

**gauge** widget — required fields:
```json
{
  "attributeRefs": [{"id": "<assetId>", "name": "<attrName>"}],
  "thresholds": [[0, "#4caf50"], [75, "#ff9800"], [90, "#ef5350"]],
  "decimals": 0,
  "min": 0,
  "max": 100,
  "valueType": "number",
  "showUnits": false
}
```

**attributeinput** widget — required fields:
```json
{
  "attributeRefs": [{"id": "<assetId>", "name": "<attrName>"}],
  "readonly": false,
  "showHelperText": true
}
```

### screenPresets — critical gotcha

`DashboardTemplate.screenPresets` must be a **non-empty array**. Jackson is configured with `WRITE_EMPTY_JSON_ARRAYS=false`, so an empty `[]` is stripped from the API response. The frontend JS then receives `undefined` and crashes with `.sort()`.

Always include at least one real screen preset:
```json
[{"id": "default", "displayName": "Default", "breakpoint": 1920, "scalingPreset": "KEEP_LAYOUT"}]
```

Valid `scalingPreset` values: `WRAP_TO_SINGLE_COLUMN`, `KEEP_LAYOUT`, `REDIRECT`, `BLOCK_DEVICE`.

### WebSocket / WAMP (real-time connection)

The frontend uses WAMP over WebSocket at `/websocket/events`. This requires HTTP/1.1 — HTTP/2 does not support the `Upgrade` mechanism.

The proxy is configured with `alpn http/1.1` on the HTTPS bind in `/deployment/haproxy.cfg` (the custom config referenced by `HAPROXY_CONFIG` env var). Do not remove this — reverting to the default would re-enable HTTP/2 and break the real-time connection.

## Key Pitfalls

- Do not use `admin-cli` tokens against the Manager API — use `openremote` client tokens.
- OpenRemote uses British spellings in attribute names (`colour` not `color`).
- Deleting assets via API returns 405 — use the web UI at https://localhost to delete assets.
- The `meta` field in attributes must be present (even if `{}`); omitting it causes 400 errors.
- All JSON must be generated programmatically (e.g., `json.dumps`) — shell string interpolation produces malformed JSON that the API silently or loudly rejects.
- Dashboard PUT via API returns 405 — modify dashboards via POST (recreate) or direct SQL UPDATE on the `dashboard` table (`template` column is JSONB).
- `colourRGB` attribute value must be `{"r": 255, "g": 255, "b": 220}` (object), not a hex string `"#FFFFDC"`.
