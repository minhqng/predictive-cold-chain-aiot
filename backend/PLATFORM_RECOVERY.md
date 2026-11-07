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

## Gate G2

Software results can verify the transport, storage, and restore path. Gate G2
also requires the physical, data, and reactive baseline evidence in Doc 04.
For a software-only rehearsal, leave physical acceptance pending.
