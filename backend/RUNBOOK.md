# Local digital-stack runbook

For an explicitly **owned local demo/rehearsal**, not a production deployment or
hardware session. Instructions are not execution evidence. Record the selected
checkout, provider ownership, dependency/image versions, commands and results in
a separate restricted rehearsal report. A native run does not prove Compose;
an agent's self-run does not prove another member's handover acceptance.

## Preflight and secrets

- Select a fresh clone and unique owned Compose project/provider namespace.
  Check that the intended loopback ports are free; never adopt or stop an
  unrelated PostgreSQL, broker, backend or Docker project.
- Provision the Python minor version and locked dependency cache in advance.
  For Compose, provision the pinned images and built backend image **before** the
  offline rehearsal. A missing image/cache is a blocker, not permission to fall
  back to a public provider or silently download during the demo.
- Retrieve local credentials from the operator's approved restricted storage.
  Configuration keys live in [`infra/.env.example`](../infra/.env.example) and
  [`ColdGuardConfig`](src/coldguard_backend/config.py). Keep real values in the
  untracked per-checkout environment/password files, never in reports or Git.
  Development placeholders are only for isolated disposable loopback fixtures.
- [`provision-dev.sh`](../infra/mosquitto/provision-dev.sh) provisions the two
  development device/ingest identities using the pinned image. Use it only in a
  fresh owned checkout with no existing `passwd`/`passwd.tmp`: it reprovisions
  files, so do not run it over someone else's credentials. Rotate existing
  credentials only with explicit operator approval. The command-publisher
  principal is separate and not provisioned/enabled by that development step.
- Keep public API access on trusted loopback. Run-registration/transition APIs
  are local operator surfaces, not authenticated public Internet APIs. Do not
  enable a command publisher, official authority or hardware during this drill.

## Start: Compose route

Requires a working Docker Compose v2 runtime and pre-staged images. The pinned
topology is [`infra/compose.yaml`](../infra/compose.yaml); commands below are the
documented route, **not a claim they ran on this machine**. `$PROJECT` is the
new owned project name; `infra/.env` is the private per-checkout configuration.
Run this as one Bash script/block with fail-fast enabled, not as independent
commands that continue after an error. Inspect the installed Compose help for
`up --wait/--wait-timeout`; a version without them is a setup blocker.

```sh
set -euo pipefail
docker compose --project-name "$PROJECT" -f infra/compose.yaml --env-file infra/.env config --quiet
# Images must already exist. Do not pull/build during an offline demo.
docker compose --project-name "$PROJECT" -f infra/compose.yaml --env-file infra/.env up -d --wait --wait-timeout 60 --pull never --no-build postgres mosquitto
# Install schema before starting acquisition/backend subscribers.
docker compose --project-name "$PROJECT" -f infra/compose.yaml --env-file infra/.env run --rm --no-deps backend .venv/bin/alembic -c alembic.ini upgrade head
docker compose --project-name "$PROJECT" -f infra/compose.yaml --env-file infra/.env up -d --pull never --no-build backend
docker compose --project-name "$PROJECT" -f infra/compose.yaml --env-file infra/.env ps
```

The bounded wait uses the PostgreSQL **TCP** readiness healthcheck, not the
temporary initialization socket. Any wait or authenticated Alembic failure stops
the block before backend/subscriber startup. Readiness alone is not credential
or schema validation; successful migration is still required. This documented
failure gate is not a substitute for a real clean Compose execution report.

The image includes `alembic.ini`, migration source and operator scripts. Frozen
export/build commands still run from the clean **host Git checkout**: the runtime
image intentionally does not contain `.git`, test fixtures or PostgreSQL client
binaries. Do not invent clean Git provenance inside that image.

If Docker/Compose/images are absent, mark clean Compose deployment **NOT RUN** and
use the separately owned native route below for the independent software work.
Do not install or reconfigure system services without authorization.

## Start: provisioned native/offline route

Use operator-provisioned PostgreSQL/TimescaleDB and authenticated Mosquitto on
explicit owned loopback ports. Set `DATABASE_URL` to the dedicated direct
`127.0.0.1` psycopg SQLAlchemy URL via the private environment. **Also set all five
`POSTGRES_*` keys — `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`
and `POSTGRES_PASSWORD` — to that same owned database.** HTTP, startup recovery
and migrations prefer `DATABASE_URL`; the MQTT and ACK workers use `ColdGuardConfig.database_url`,
derived from `POSTGRES_*`. Setting only `DATABASE_URL` leaves those workers on
their defaults, potentially a different server. Never rely on `localhost:5432`
fallback or change/adopt an unrelated provider to make startup pass.

Set backend MQTT host/port/ingest credentials from the same owned broker. The
configuration check below compares the API/worker URLs **without connecting**;
it does not establish provider ownership, which must already be verified. Run
the native block as one fail-fast Bash script/block. From `backend/`:

```sh
set -euo pipefail
mkdir -p ../evidence-out
uv sync --offline --locked --extra test
uv run --offline --locked python - <<'PY'
import os
from sqlalchemy.engine import make_url
from coldguard_backend.config import ColdGuardConfig
from coldguard_backend.main import _database_url

keys = ("DATABASE_URL", "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
if any(not os.environ.get(name, "").strip() for name in keys):
    raise SystemExit("Set explicit DATABASE_URL and all POSTGRES_* bindings before network access")
try:
    api = make_url(_database_url())
    workers = make_url(ColdGuardConfig.load().database_url)
except ValueError:
    raise SystemExit("Invalid database configuration; stop before network access") from None
if api.drivername != "postgresql+psycopg" or api.host != "127.0.0.1" or not api.port or not api.database or api.query:
    raise SystemExit("Select the explicit owned direct-loopback database before network access")
if api != make_url(os.environ["DATABASE_URL"]) or api != workers:
    raise SystemExit("API/migration and MQTT/ACK databases differ; stop before network access")
print("Database configuration correspondence checked (credentials not displayed)")
PY
uv run --offline --locked alembic -c alembic.ini upgrade head
uv run --offline --locked alembic -c alembic.ini current
uv run --offline --locked python scripts/check_stack.py --database-only --output ../evidence-out/schema-readiness.json
uv run --offline --locked uvicorn coldguard_backend.main:app --host 127.0.0.1 --port 8000
```

Start only the subscribers intended by the profile. For the ACK/recovery scenes,
set `COLDGUARD_MQTT_INGEST=true`, `COLDGUARD_MQTT_ACK_INGEST=true` and
`COLDGUARD_RECONCILE_COMMANDS=true` **after migrations**, before starting the
backend. Startup reconciliation records uncertainty/expiry; it is not a replay
publisher. Optional gateway/inference extras need their pre-provisioned locked
cache; an official model/authority is not required for the software-only drill.

## Health and logs

`GET /health` and the Compose backend healthcheck are **liveness only**. They do
not prove the DB is migrated or the MQTT subscriptions are ready. Use the host
checkout with its owned direct-loopback DB binding for the full required check:

```sh
uv run --offline --locked python scripts/check_stack.py --backend http://127.0.0.1:8000 --require-mqtt --require-ack --output ../evidence-out/runtime-readiness.json
```

[`check_stack.py`](scripts/check_stack.py) owns the checked schema inventory and
required readiness fields. It returns nonzero for NOT_READY, rejects ambiguous
origins, ignores proxies and refuses redirects. Existing reports are not
overwritten. Read-only schema/table checks are not a physical or security
certification. Use unique report names outside immutable packages.
Pre-create the owned report directory. Parent-relative operator output roots are
supported; internal artifact dot-navigation/device/alias names are still refused.
The host `DATABASE_URL` and backend's `DATABASE_URL`/`POSTGRES_*` must identify the
same owned DB: READY tests the explicitly supplied DB, but does not discover or
authenticate the correspondence automatically. Startup reconciliation is reported separately
and must be enabled for the recovery scene; it is not a generic READY gate.

```sh
docker compose --project-name "$PROJECT" -f infra/compose.yaml --env-file infra/.env logs --no-color --tail 100 backend mosquitto postgres
```

For native processes retain the stdout/stderr files from their owned launch
console. Separate startup/build logs from broker/backend incident artifacts.
Runtime metrics and structured log fields are documented in
[platform recovery](PLATFORM_RECOVERY.md#runtime-observability). Counters reset on
restart; reconcile durable DB histories rather than adding overlapping counters.
Keep credentials out of shareable logs; denied broker traffic may have no raw row.

## Broker auth/TLS and reconnect troubleshooting

The principal/topic authority is [`acl.conf`](../infra/mosquitto/acl.conf), with
anonymous access disabled by [`mosquitto.conf`](../infra/mosquitto/mosquitto.conf).
A device cannot publish commands; the ingest identity cannot publish. Never
"fix" an auth failure by enabling anonymous access or widening topic ACLs.

For an explicitly provisioned TLS rehearsal, use
[`mosquitto-tls.conf`](../infra/mosquitto/mosquitto-tls.conf) and the separate
[TLS/auth instructions](SECURITY_INFERENCE.md#tls-and-mqtt-identities). The server
certificate SAN must match `MQTT_HOST`; provision the CA and key privately,
configure the trusted CA bundle and TLS listener, and preserve hostname/trust
failures separately from MQTT auth/ACL denial. The default Compose file remains
the isolated non-TLS development profile; it does not silently enable TLS.

If readiness fails, check in order: owned PID/port → DB/schema → broker TCP/TLS →
credential refusal → SUBACK readiness → ingestion/reconciliation evidence.
Broker recovery clears/resets subscriptions; it does not prove a device mode or
physical SAFE_LOCAL. [Outage resynchronization](PLATFORM_RECOVERY.md#outage-resynchronization)
owns dispatch/expiry/boot/replay fences. Restart only the process/project you own.

## Backup and clean restore

Use matching PostgreSQL major/TimescaleDB versions and the host's approved
`pg_dump`/`pg_restore` paths. The exact archive/freeze route is in
[campaign operations](CAMPAIGNS.md#wave-block-archive-and-restore). Take the later
**post-freeze** backup to retain the immutable freeze record; keep the original
pre-freeze source archive and its distinct identity too.

Restore into a different empty owned DB with TimescaleDB pre-provisioned through
[`001_extensions.sql`](../infra/postgres/init/001_extensions.sql). **Do not migrate
the restore target first.** The restore verifier rejects existing application
tables, mismatched receipts/fingerprints and missing evidence. Retain the actual
restore report; an archive receipt alone says restore is not yet verified.
Rebuilding the [final JSON package](FINAL_DATA_PACKAGE.md) uses the unchanged
frozen/incident bytes, the same builder commit/time and the separately trusted
manifest anchors. Compare all retained table fingerprints and package bytes.

Never migrate an active frozen physical campaign as a routine demo repair.
Stop and follow the documented Doc03 emergency stop/restart/comparability rule.
Do not remove failed attempts or repair missing measurements to make a demo pass.

## Scenes and stop

Use a separately registered `SOFTWARE_SIMULATION` run and provisioned software
peer. `coldguard_backend.simulator` publishes only synthetic input; it is not a
hardware client. Show:

- live API/Twin **desired, reported and derived separately**; synthetic samples
  must not be promoted to authoritative reported physical state;
- `/api/runs/{run_id}/timeline` and the scoped event/telemetry pages;
- `/api/commands/{command_id}/timing` and the command trace: intent/PUBACK/ACK are
  distinct; an OFF intent-only rehearsal publishes no command;
- broker disconnect → NOT_READY → owned restart/resubscribe → renewed ingestion,
  without a fabricated boot, automatic uncertain-command replay or physical claim.

Use Ctrl+C in the owned native launch console for graceful stop. For the owned
Compose project use `stop` or `down` **without volume deletion**. Never kill all
matching processes or delete shared volumes/evidence. Snapshot completed
rehearsal artifacts before teardown.

For another-member handover, let that real member execute this route while C
observes. Record identity, commands, failures and any manual intervention.
An undocumented manual fix is a documentation defect to correct and rerun;
agent/self-run evidence cannot stand in for that independent human acceptance.
