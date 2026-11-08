# Platform soak and recovery

Use explicitly provisioned local test providers for the software proof.
Confirm PostgreSQL and Mosquitto are bound to loopback and belong to the test
before starting. Apply migrations to the dedicated PostgreSQL database.
Configure the backend MQTT subscriber and a device-scoped simulator identity.

## Paced software soak

From `backend/`, set the PostgreSQL and MQTT connection settings used by
`ColdGuardConfig`. Set `COLDGUARD_SOAK_DEVICE_USER` and
`COLDGUARD_SOAK_DEVICE_PASSWORD` to the disposable broker's device identity.
`COLDGUARD_SOAK_DEVICE_ID` defaults to `coldguard-001`. Keep the device topic
free of other senders while collecting process counters.

```sh
uv run --locked alembic upgrade head
uv run --locked python scripts/proof_platform_soak.py --samples 7201 --output software-soak.json
```

The script generates one sample per second and registers a software run with
no actuation. The default count spans two hours at the target cadence.
The report compares broker acknowledgements and backend receipt counters with
durable normalized records. It includes duplicates, invalid deliveries, DB
errors, sequence gaps, and receipt intervals. The simulator event clock
cannot establish transport latency or physical timing.

## Reconnect and restart

`MqttIngestConsumer.snapshot()` distinguishes process running state, broker
connection, and acknowledged subscriptions. On disconnect it clears broker
readiness. The consumer resubscribes on reconnect and does not change the
device's reported Twin based on the broker connection.

## Replay accounting

Every receipt remains in raw storage. The first normalized row for
`(device_id, boot_id, seq)` remains authoritative. A new row counts as
out of order when the normalization transaction can already see a larger
sequence number from the same device and boot. `replay` and `is_replay`
flags identify historical deliveries, including clockless buffered frames.
Explicit replay and out-of-order counts can overlap. Replay cannot advance the
reported Twin, and a boot change still requires trusted reconciliation.

Consumer snapshots expose `exact_duplicates`, `conflicts`, `out_of_order`,
and `explicit_replays` as process-local counts. Use the reconciliation script
or stored raw and normalized rows for durable accounting across restarts.

## Runtime observability

`GET /api/metrics` reports process-local counters and non-cumulative
duration buckets. Durations use a monotonic timer and measure backend
processing, including database and broker waits. The final bucket counts
durations greater than the last listed upper bound. Metrics have no
per-device labels and reset with the process.

Telemetry ingest, command publish and ACK processing log JSON event bodies
with available device, run, boot, sequence, command, prediction and evidence
IDs. The reason field uses a bounded outcome. Log events exclude raw
payloads and credentials. Set the backend logger to DEBUG for successful
telemetry receipt details.

`GET /api/commands/{command_id}/timing` reports database creation,
broker PUBACK recording and device ACK receipt times separately. It
identifies ACKs that arrived before PUBACK was recorded. Electrical and
thermal timing require trusted physical evidence and stay null without it.
Telemetry source clocks retain the existing timing-quality checks. A
timezone-aware device timestamp alone cannot establish transport latency.

## Outage resynchronization

Set `COLDGUARD_RECONCILE_COMMANDS=true` after migrations to reconcile command
history before the backend subscribes. Recovery records unresolved attempts
as unknown and expires due commands in PostgreSQL. The recovery path has no
publisher. An opt-in startup fails if the audit database is unavailable.

`GET /api/runtime/readiness` reports broker and subscription readiness
independently. `GET /api/devices/{device_id}/recovery` shows the reported boot
and sequence, the latest normalized observation, desired expiry, pending
attempt count, and the latest ACK receipt classification. The latest
observation may be a replay and cannot authorize a boot switch. Broker
connectivity cannot establish physical state or a device safety mode.

Pass the publisher readiness check to `AuthorizedCommandGateway`. When
the transport is unavailable, dispatch fails before creating intent. Database
failure also prevents sending because durable intent and attempt evidence
must commit first. A disconnected Paho command client does not reconnect or
replay its queue. A deliberate later dispatch requires a newly ready transport
and the normal policy, desired ownership and TTL checks.

To exercise a real restart, set `COLDGUARD_TEST_DATABASE_URL` to a disposable
database and `COLDGUARD_TEST_MOSQUITTO_EXE` to the broker executable with
`mosquitto_passwd` available alongside it. The test provisions an
authenticated private broker and restarts only its own process.

```sh
uv run --locked --extra test pytest -q tests/test_platform_reconnect.py
```

## Logical backup and restore drill

Keep archives in a restricted location. Supply database credentials through
the local PostgreSQL client configuration or a private password file. Use
the same supported PostgreSQL major and TimescaleDB extension version for
the drill. Create a new empty restore database on an explicitly disposable
provider.

```sh
pg_dump --format=custom --no-owner --no-acl --file=software.dump "$SOURCE_DB"
createdb "$RESTORE_DB"
psql -X -v ON_ERROR_STOP=1 -d "$RESTORE_DB" -c 'CREATE EXTENSION timescaledb;' -c 'SELECT timescaledb_pre_restore();'
pg_restore --exit-on-error --no-owner --no-acl -d "$RESTORE_DB" software.dump
psql -X -v ON_ERROR_STOP=1 -d "$RESTORE_DB" -c 'SELECT timescaledb_post_restore();'
```

Record the archive's SHA-256 and compare source and restored row counts and
representative data for `experiments`, `experiment_transitions`, `telemetry`,
`telemetry_raw`, `commands`, and `command_transitions`. Verify that normalized
samples reference the same raw IDs and payload digests. Verify the Alembic
revision. Keep the source database available until the comparison passes.

For the W12 baseline check, set `COLDGUARD_BACKUP_SOURCE_URL` and
`COLDGUARD_BACKUP_RESTORE_URL` to distinct disposable loopback PostgreSQL
databases. Pause writes while making the backup and comparing it with the
restore. Run the verifier from `backend/`.

```sh
uv run --locked python scripts/verify_restore.py --output restore-proof.json
```

The verifier streams primary-key-ordered rows and records each table's count
and SHA-256 in UTC. It covers raw payload and normalized provenance, run
manifests and transitions, command attempts, ACKs, and Twin state. It also
checks predictions and their inputs, shadow decisions, physical assessments,
and policy approvals from the revisions that introduce them. A mismatch
produces a nonzero exit code. Re-export the frozen S1 run set from both databases with the
same `--created-at` and backend commit, then compare the artifact SHA-256.

## Gate G2

Software results can verify the transport, storage, and restore path. Gate G2
also requires the physical, data, and reactive baseline evidence in Doc 04.
For a software-only rehearsal, leave physical acceptance pending.
