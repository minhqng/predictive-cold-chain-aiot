# Predictive Cold-Chain AIoT System

**Codename:** `ColdGuard` (project/course codename).

ColdGuard is an experimental predictive cold-chain AIoT testbed: multi-point
thermal sensing observes a small controlled chamber, telemetry flows over MQTT
into a backend with a Digital Twin, an XGBoost model produces predictive
thermal-risk warnings, a safety-bounded policy may trigger thermoelectric
intervention, and every intervention is to be verified against independent
electrical and thermal evidence.

## Current Status

`C-W02 — MQTT ingestion and raw persistence` (Member C). What actually
runs: the W01 three-service Compose stack, now with an authenticated
Mosquitto profile (per-principal password file provisioned by
`infra/mosquitto/provision-dev.sh`, device-scoped ACL, anonymous
denied, TLS-ready structure without deployed TLS), a deterministic
synthetic device (`backend/src/coldguard_backend/simulator.py`
publishing telemetry/event/state/health with canonical QoS/retain), a
real backend MQTT subscriber running inside the FastAPI process
(`mqtt_consumer.py`, single consumer, fail-fast auth errors, DB commit
as the durability boundary), and the `telemetry_raw` evidence table
(migration `0002`: exact wire text, JSONB projection, SHA-256,
preliminary status, diagnostics; valid and malformed payloads
retained). Proven by a 1,000-message Mosquitto→backend→PostgreSQL run
with no unexplained application-level loss (`backend/scripts/proof_1000.py`).
No normalized telemetry, dedup enforcement, Digital Twin, prediction,
or control exists yet; those start in W03+.

## Backend Architecture (Member C, W01)

One deployable modular FastAPI monolith. Real modules today:

```text
backend/src/coldguard_backend/
├── main.py        # api: FastAPI app, GET /health + MQTT consumer lifespan
├── config.py      # configuration: profiles, env precedence, validation
├── contracts.py   # wire contracts: Telemetry / Command validation
├── simulator.py   # synthetic device: deterministic finite-run publisher
├── mqtt_consumer.py # ingestion: real subscriber → telemetry_raw
├── raw_store.py   # persistence: classification + durable raw writes
└── migrations/   # Alembic revisions 0001 (baseline) + 0002 (telemetry_raw)
```

Future logical boundaries (not yet packages; see Doc 05C weeks 02+):

```text
ingestion → twin → experiments → prediction → policy adapter
→ commands → api → observability
```

Dependency direction stays: policy adapter never redefines control
decisions (Member D), ingestion never makes ML/control own the
database, and the backend never owns physical measurement semantics
(Member A).

## MQTT / Contract Handoff

Canonical topics (Doc 02): `coldguard/{device_id}/telemetry`,
`.../event`, `.../state`, `.../command`, `.../command_ack`, `.../health`.
Telemetry QoS 1 (duplicates possible; dedup key is
`device_id + boot_id + seq`, enforced in W03 — W02 keeps duplicate
deliveries as separate observable raw rows), commands QoS 1 with
`retain=false` and payload `expires_at`. A command request is not an
execution; an ACK is not physical success; a PUBACK is not a DB commit.

Broker access (provision first, then start):

```bash
infra/mosquitto/provision-dev.sh   # salted-hash passwd file, git-ignored
docker compose -f infra/compose.yaml --env-file infra/.env.example up -d --build
```

Principals: `device-coldguard-001` publishes its own
telemetry/event/state/command_ack/health and reads its command;
`backend-ingest` subscribes device data only and cannot publish.
Anonymous access is denied; the device cannot publish commands or
foreign namespaces. Listener stays on `127.0.0.1:1883` (dev-safe);
TLS is structure-ready, not deployed.

Synthetic-to-raw workflow (real broker → real consumer → real DB):

```bash
(cd backend && uv run --locked alembic -c alembic.ini upgrade head)
(cd backend && uv run --locked --extra test python \
  -m coldguard_backend.simulator --boot-id boot-manual-001 \
  --run-id CG-MANUAL-001 --count 10)
(cd backend && DATABASE_URL=... MQTT_HOST=localhost \
  uv run --locked --extra test python scripts/proof_1000.py)
```

Raw statuses are preliminary W02 evidence (`RECEIVED_VALID` means
wire-shape valid, not a validated physical sample): `RECEIVED_VALID` /
`RECEIVED_INVALID_SCHEMA` / `RECEIVED_MALFORMED_JSON` /
`RECEIVED_OBSERVED` (non-telemetry families, validation deferred).

- Member A (firmware): topics above plus
  `backend/fixtures/telemetry_v0.json` and `command_v0.json` for field
  semantics and device identity.
- Member B (data): provisional measurement fields, quality/missing
  representation and run/hardware/calibration identity in the telemetry
  fixture; wire names differ deliberately from future normalized DB
  names.
- Member D (control): command shape, provenance/expiry fields and the
  policy-adapter boundary; device-side safety enforcement stays with
  firmware.

## Configuration Profiles

`COLDGUARD_PROFILE` is one of `dev`, `integration`, `experiment`
(anything else is rejected). Host runtimes default to `localhost`
services; inside Compose the backend uses service names (`postgres`,
`mosquitto`) via `infra/compose.yaml` overrides. The committed
`.env.example` starts the stack without an untracked `.env`; real
secrets must never be committed.

## Backend Migrations

From `backend/` (uses `DATABASE_URL` when set, else validated config):

```bash
uv run --locked alembic -c alembic.ini upgrade head
uv run --locked alembic -c alembic.ini current   # expect: 0002 (head)
```

Timescale extension ownership stays with
`infra/postgres/init/001_extensions.sql` (`CREATE EXTENSION IF NOT
EXISTS`); migrations never manage extension-owned objects.

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
