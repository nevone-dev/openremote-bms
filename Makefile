VENV       := .venv
PYTHON     := $(VENV)/bin/python3
PIP        := $(VENV)/bin/pip
UVICORN    := $(VENV)/bin/uvicorn
TICK       ?= 5
LOG_LEVEL  ?= INFO

# Keycloak / OR credentials
OR_BASE_URL ?= https://localhost
OR_REALM    ?= master
OR_USER     ?= admin
OR_PASS     ?= secret

SIM_PID  := /tmp/bms-sim.pid
SIM_LOG  := /tmp/bms-sim.log

.PHONY: help venv install up down logs seed auth-fix gateway-dev sim sim-start sim-stop sim-logs sim-status scenario status bootstrap clean

# ── Default target ─────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Smart-office BMS — development targets"
	@echo ""
	@echo "  First-time setup (run once on a fresh checkout)"
	@echo "    make bootstrap         up + auth-fix + seed  (all-in-one)"
	@echo ""
	@echo "  Stack (Docker Compose — proxy, keycloak, postgresql, manager, gateway)"
	@echo "    make up                Start stack; waits until gateway is healthy"
	@echo "    make down              Stop and remove containers"
	@echo "    make logs              Tail all container logs"
	@echo "    make status            Container status + gateway /health JSON"
	@echo ""
	@echo "  Setup steps (called automatically by bootstrap)"
	@echo "    make venv              Create .venv"
	@echo "    make install           Install Python deps into .venv"
	@echo "    make auth-fix          Enable direct-access grants on the Keycloak openremote client"
	@echo "    make seed              Populate OpenRemote with the mock asset tree"
	@echo ""
	@echo "  Gateway (GraphQL at http://localhost:8000/graphql)"
	@echo "    make gateway-dev       Run gateway outside Docker with hot-reload (dev only)"
	@echo "                           Note: 'make up' already starts the gateway in Docker"
	@echo ""
	@echo "  Simulator (writes live sensor data every TICK seconds)"
	@echo "    make sim               Run in foreground  [TICK=5] [LOG_LEVEL=INFO]"
	@echo "    make sim-start         Start in background (PID → $(SIM_PID))"
	@echo "    make sim-stop          Stop background simulator"
	@echo "    make sim-status        Show PID and last 5 log lines"
	@echo "    make sim-logs          Tail simulator log"
	@echo ""
	@echo "  Scenarios (apply a named building state for testing)"
	@echo "    make scenario SCENARIO=normal             Nominal working-day values"
	@echo "    make scenario SCENARIO=summer_heat        High temps, HVAC cooling"
	@echo "    make scenario SCENARIO=after_hours        Lights off, HVAC off, printers offline"
	@echo "    make scenario SCENARIO=energy_crisis      Lights max, extreme HVAC setpoints"
	@echo "    make scenario SCENARIO=printer_emergency  Office A toner=3%, status=error"
	@echo ""
	@echo "  Housekeeping"
	@echo "    make clean             Remove .venv and all __pycache__ directories"
	@echo ""

# ── Virtual environment ────────────────────────────────────────────────────────
venv:
	python3 -m venv $(VENV)
	@echo "Run 'make install' next."

install: venv
	$(PIP) install -q -r gateway/requirements.txt
	$(PIP) install -q websockets
	@echo "Dependencies installed."

# ── Docker stack ───────────────────────────────────────────────────────────────
up:
	docker compose up -d
	@echo "Waiting for gateway…"
	@for i in $$(seq 1 30); do \
		if curl -sf http://localhost:8000/health > /dev/null 2>&1; then \
			echo "Gateway ready → http://localhost:8000/graphql"; \
			echo "OpenRemote UI → https://localhost  (admin / secret)"; \
			break; \
		fi; \
		sleep 2; \
	done

down:
	docker compose down

logs:
	docker compose logs -f

status:
	@echo "=== Containers ==="
	@docker compose ps
	@echo ""
	@echo "=== Gateway health ==="
	@curl -sf http://localhost:8000/health | python3 -m json.tool || echo "Gateway not reachable"

# ── First-time setup ───────────────────────────────────────────────────────────
auth-fix:
	@echo "Enabling direct-access grants on the 'openremote' Keycloak client…"
	$(eval TOKEN := $(shell curl -sk -X POST $(OR_BASE_URL)/auth/realms/$(OR_REALM)/protocol/openid-connect/token \
		-d 'grant_type=password&client_id=admin-cli&username=$(OR_USER)&password=$(OR_PASS)' \
		| python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"))
	$(eval CLIENT_ID := $(shell curl -sk -H "Authorization: Bearer $(TOKEN)" \
		"$(OR_BASE_URL)/auth/admin/realms/$(OR_REALM)/clients?clientId=openremote" \
		| python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])"))
	@curl -sk -X PUT \
		-H "Authorization: Bearer $(TOKEN)" \
		-H "Content-Type: application/json" \
		"$(OR_BASE_URL)/auth/admin/realms/$(OR_REALM)/clients/$(CLIENT_ID)" \
		-d '{"directAccessGrantsEnabled": true}' \
		&& echo "Done."

seed: install
	$(PYTHON) seed.py

# ── Local gateway (outside Docker, hot-reload) ─────────────────────────────────
gateway-dev: install
	$(UVICORN) gateway.main:app --host 0.0.0.0 --port 8000 --reload

# ── Simulator ─────────────────────────────────────────────────────────────────
sim: install
	TICK_SECONDS=$(TICK) LOG_LEVEL=$(LOG_LEVEL) $(PYTHON) -m simulator.sim

sim-start: install
	@if [ -f $(SIM_PID) ] && kill -0 $$(cat $(SIM_PID)) 2>/dev/null; then \
		echo "Simulator already running (PID $$(cat $(SIM_PID)))"; \
	else \
		TICK_SECONDS=$(TICK) LOG_LEVEL=$(LOG_LEVEL) \
			nohup $(PYTHON) -m simulator.sim > $(SIM_LOG) 2>&1 & \
		echo $$! > $(SIM_PID); \
		echo "Simulator started (PID $$(cat $(SIM_PID)))  log → $(SIM_LOG)"; \
	fi

sim-stop:
	@if [ -f $(SIM_PID) ] && kill -0 $$(cat $(SIM_PID)) 2>/dev/null; then \
		kill $$(cat $(SIM_PID)) && rm -f $(SIM_PID); \
		echo "Simulator stopped."; \
	else \
		echo "Simulator is not running."; \
		rm -f $(SIM_PID); \
	fi

sim-logs:
	@tail -f $(SIM_LOG)

sim-status:
	@if [ -f $(SIM_PID) ] && kill -0 $$(cat $(SIM_PID)) 2>/dev/null; then \
		echo "Simulator running  PID=$$(cat $(SIM_PID))  log=$(SIM_LOG)"; \
		tail -5 $(SIM_LOG); \
	else \
		echo "Simulator is not running."; \
	fi

# ── Scenarios ─────────────────────────────────────────────────────────────────
SCENARIO ?= normal

scenario: install
	$(PYTHON) run_scenario.py $(SCENARIO)

# ── Full bootstrap (for a fresh checkout) ─────────────────────────────────────
bootstrap: up auth-fix seed
	@echo ""
	@echo "Bootstrap complete. Run 'make sim' to start the simulator."

# ── Housekeeping ──────────────────────────────────────────────────────────────
clean:
	rm -rf $(VENV)
	find . -type d -name __pycache__ -not -path './openremote_sdk/*' | xargs rm -rf
	@echo "Cleaned."
