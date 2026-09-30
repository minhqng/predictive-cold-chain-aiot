# Predictive Cold-Chain AIoT System

**Codename:** `ColdGuard` (project/course codename).

ColdGuard is an experimental predictive cold-chain AIoT testbed: multi-point
thermal sensing observes a small controlled chamber, telemetry flows over MQTT
into a backend with a Digital Twin, an XGBoost model produces predictive
thermal-risk warnings, a safety-bounded policy may trigger thermoelectric
intervention, and every intervention is to be verified against independent
electrical and thermal evidence.

## Current Status

`W01 — Repository Foundation / Technical Skeleton`. Only skeleton code exists:
a minimal ESP-IDF app entry, a FastAPI `/health` endpoint, importable ML and
control packages, and local Mosquitto/TimescaleDB Compose definitions. No
sensing, persistence, prediction, or control logic is implemented yet.

## Repository Layout

```text
├── README.md
├── .python-version  # shared Python minor-version request (3.12)
├── docs/          # 9 canonical project documents (sole authority)
├── firmware/      # Member A — ESP-IDF app skeleton
├── backend/       # Member C — FastAPI skeleton (coldguard_backend + uv.lock)
├── ml/            # Member B — ML package skeleton (coldguard_ml + uv.lock)
├── control/       # Member D — policy package skeleton (coldguard_control + uv.lock)
└── infra/         # Member C — local Mosquitto + TimescaleDB Compose
```

## Ownership

| Area | Owner |
|---|---|
| Embedded / Electrical / Thermal | Member A |
| AI / Experimental Data / Statistics | Member B |
| IoT Backend / Digital Twin / Persistence | Member C |
| Control / Safety / Security / Resilience | Member D |

`control/` is separate from `backend/` and `firmware/` so policy logic stays
testable without MQTT, PostgreSQL, GPIO, or hardware. Shared concerns (docs,
integration, experiments, evidence, governance) are team-owned.

## Canonical Documentation

`docs/` holds the 9 canonical files (`00`, `01`, `02`, `03`, `04`,
`05A`–`05D`) with precedence `00 → 01 → 02 → 03 → 04 → 05A/05B/05C/05D`.
Child docs may add detail but may not weaken parent correctness or gates.

## Commands

Each Python project (`backend/`, `ml/`, `control/`) pins its own
`uv.lock` (no root workspace). With `uv` installed:

```bash
(cd backend && uv sync --locked --extra test && uv run --locked --extra test pytest)
(cd ml && uv sync --locked --extra test && uv run --locked --extra test pytest)
(cd control && uv sync --locked --extra test && uv run --locked --extra test pytest)
```

Infrastructure (requires Docker):

```bash
docker compose -f infra/compose.yaml config
docker compose -f infra/compose.yaml --env-file infra/.env.example up -d
docker compose -f infra/compose.yaml --env-file infra/.env.example down
```

Firmware is verified with the official Espressif Docker image (local
ESP-IDF is not installed). The temporary copy keeps generated `build/`
and `sdkconfig` out of the repository:

```bash
rm -rf /tmp/coldguard-firmware-build && mkdir -p /tmp/coldguard-firmware-build && cp -r firmware/. /tmp/coldguard-firmware-build/
docker run --rm -v /tmp/coldguard-firmware-build:/project:z -w /project espressif/idf:v6.1 bash -c "idf.py set-target esp32s3 && idf.py build"
```
