#!/usr/bin/env bash
# OpenRemote mock data seed script
# Creates: Building > Floor 1 & 2 > Offices with Lighting, HVAC, Network Switch, Printer

set -euo pipefail

BASE="https://localhost"
REALM="master"
CURL="curl -sk"

# ─── Auth ────────────────────────────────────────────────────────────────────
echo "Getting access token..."
TOKEN=$($CURL -X POST "$BASE/auth/realms/$REALM/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=openremote&username=admin&password=secret" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

AUTH="Authorization: Bearer $TOKEN"
CT="Content-Type: application/json"
NOW=$(python3 -c "import time; print(int(time.time()*1000))")

# Helper: POST asset, return ID
create_asset() {
  local body="$1"
  local result
  result=$($CURL -X POST "$BASE/api/$REALM/asset" \
    -H "$AUTH" -H "$CT" \
    -d "$body")
  echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['id'])" 2>/dev/null || {
    echo "ERROR creating asset:" >&2
    echo "$result" >&2
    exit 1
  }
}

attr_text()  { printf '"%s":{"name":"%s","type":"text","meta":{},"value":"%s","timestamp":%s}' "$1" "$1" "$2" "$NOW"; }
attr_int()   { printf '"%s":{"name":"%s","type":"positiveInteger","meta":{},"value":%s,"timestamp":%s}' "$1" "$1" "$2" "$NOW"; }
attr_num()   { printf '"%s":{"name":"%s","type":"number","meta":{},"value":%s,"timestamp":%s}' "$1" "$1" "$2" "$NOW"; }
attr_bool()  { printf '"%s":{"name":"%s","type":"boolean","meta":{},"value":%s,"timestamp":%s}' "$1" "$1" "$2" "$NOW"; }
attr_point() { printf '"location":{"name":"location","type":"GEO_JSONPoint","meta":{},"value":{"type":"Point","coordinates":[%s,%s]},"timestamp":%s}' "$1" "$2" "$NOW"; }

# ─── Building ────────────────────────────────────────────────────────────────
echo "Creating Building: OpenRemote HQ..."
BUILDING_ID=$(create_asset "{
  \"name\": \"OpenRemote HQ\",
  \"type\": \"BuildingAsset\",
  \"realm\": \"$REALM\",
  \"attributes\": {
    $(attr_text  street     \"1 Innovation Drive\"),
    $(attr_text  city       \"Amsterdam\"),
    $(attr_text  country    \"Netherlands\"),
    $(attr_text  postalCode \"1012 AB\"),
    $(attr_text  notes      \"Main office building\"),
    $(attr_int   area       2000),
    $(attr_point 4.9041     52.3676)
  }
}")
echo "  -> Building ID: $BUILDING_ID"

# ─── Create floors ────────────────────────────────────────────────────────────
for FLOOR_NUM in 1 2; do
  echo "Creating Floor $FLOOR_NUM..."
  FLOOR_ID=$(create_asset "{
    \"name\": \"Floor $FLOOR_NUM\",
    \"type\": \"FloorAsset\",
    \"realm\": \"$REALM\",
    \"parentId\": \"$BUILDING_ID\",
    \"attributes\": {
      $(attr_int floorLevel $FLOOR_NUM),
      $(attr_int area       800),
      $(attr_text notes     \"Office floor $FLOOR_NUM\"),
      $(attr_point 4.9041   52.3676)
    }
  }")
  echo "  -> Floor $FLOOR_NUM ID: $FLOOR_ID"

  IP_BASE="10.$FLOOR_NUM"
  OCTET=1

  # Offices on this floor
  for ROOM in "Office A" "Office B" "Meeting Room" "Server Room"; do
    SAFE_ROOM=$(echo "$ROOM" | tr ' ' '_')
    echo "  Creating room: $ROOM (Floor $FLOOR_NUM)..."

    ROOM_ID=$(create_asset "{
      \"name\": \"$ROOM\",
      \"type\": \"ThingAsset\",
      \"realm\": \"$REALM\",
      \"parentId\": \"$FLOOR_ID\",
      \"attributes\": {
        $(attr_text notes \"Office space – Floor $FLOOR_NUM\"),
        $(attr_point 4.9041 52.3676)
      }
    }")

    # ── Lighting ──────────────────────────────────────────────────────────
    LIGHT_ID=$(create_asset "{
      \"name\": \"$ROOM – Lighting\",
      \"type\": \"LightAsset\",
      \"realm\": \"$REALM\",
      \"parentId\": \"$ROOM_ID\",
      \"attributes\": {
        $(attr_bool onOff true),
        $(attr_num  brightness 80),
        $(attr_num  colorTemperature 4000),
        $(attr_text notes \"LED ceiling lights\"),
        $(attr_point 4.9041 52.3676)
      }
    }")
    echo "    -> Lighting: $LIGHT_ID"

    # ── HVAC ──────────────────────────────────────────────────────────────
    HVAC_ID=$(create_asset "{
      \"name\": \"$ROOM – HVAC\",
      \"type\": \"ThingAsset\",
      \"realm\": \"$REALM\",
      \"parentId\": \"$ROOM_ID\",
      \"attributes\": {
        $(attr_text notes    \"HVAC unit – ceiling mounted\"),
        $(attr_num  currentTemperature 22.1),
        $(attr_num  temperatureSetpoint 21.5),
        $(attr_num  humidity 48),
        $(attr_num  powerConsumption 1.2),
        $(attr_text hvacMode \"cooling\"),
        $(attr_text status   \"running\"),
        $(attr_point 4.9041 52.3676)
      }
    }")
    echo "    -> HVAC: $HVAC_ID"

    # ── Network Switch ────────────────────────────────────────────────────
    NET_ID=$(create_asset "{
      \"name\": \"$ROOM – Network Switch\",
      \"type\": \"ThingAsset\",
      \"realm\": \"$REALM\",
      \"parentId\": \"$ROOM_ID\",
      \"attributes\": {
        $(attr_text notes        \"24-port managed switch\"),
        $(attr_text manufacturer \"Cisco\"),
        $(attr_text model        \"Catalyst 2960-24TT\"),
        $(attr_text ipAddress    \"$IP_BASE.$OCTET\"),
        $(attr_int  activePorts  12),
        $(attr_int  totalPorts   24),
        $(attr_text uptime       \"42d 3h 17m\"),
        $(attr_text status       \"online\"),
        $(attr_point 4.9041 52.3676)
      }
    }")
    echo "    -> Network Switch: $NET_ID"
    OCTET=$((OCTET + 10))

    # ── Printer ───────────────────────────────────────────────────────────
    PRN_ID=$(create_asset "{
      \"name\": \"$ROOM – Printer\",
      \"type\": \"ThingAsset\",
      \"realm\": \"$REALM\",
      \"parentId\": \"$ROOM_ID\",
      \"attributes\": {
        $(attr_text notes        \"Network laser printer\"),
        $(attr_text manufacturer \"HP\"),
        $(attr_text model        \"LaserJet Pro M404dn\"),
        $(attr_text ipAddress    \"$IP_BASE.$OCTET\"),
        $(attr_text status       \"ready\"),
        $(attr_num  tonerLevel   74),
        $(attr_int  pagesPrinted 13842),
        $(attr_text paperLevel   \"OK\"),
        $(attr_point 4.9041 52.3676)
      }
    }")
    echo "    -> Printer: $PRN_ID"
    OCTET=$((OCTET + 10))

    echo "    Done: $ROOM"
  done
done

echo ""
echo "All mock data created!"
echo "Visit https://localhost and log in with admin / secret to explore the asset tree."
