"""ColdGuard normalized telemetry + topic-mismatch evidence, revision 0003 (C-W03).

Creates the Doc 02 §14.2 normalized ``telemetry`` table for one
physical cooling branch and widens the ``telemetry_raw`` status guard
with ``REJECTED_TOPIC_MISMATCH`` (C-W03-02 evidence).

Raw/authority reconciliation (mission §9): ``telemetry_raw`` stays an
append-only delivery-attempt log with NO uniqueness constraint, so
this migration succeeds on valid W02 databases that already contain
repeated logical identities and preserves every historical row. The
canonical ``UNIQUE(device_id, boot_id, seq)`` lives on normalized
``telemetry`` only — the authoritative-sample authority. No backfill
fabricates normalized rows from historical raw deliveries: treating
every W02 raw row as physically validated would invent authority the
W02 pipeline never claimed. Post-upgrade deliveries normalize going
forward with ``raw_id`` provenance.

Timescale decision: regular PostgreSQL table with sound indexes, NOT
a hypertable. A hypertable requires every unique index to contain all
partitioning columns, which would force event time into the canonical
``(device_id, boot_id, seq)`` identity. Correctness of the specified
invariant wins over chunk partitioning at ~1 Hz / one device.

Identity columns are NOT NULL: PostgreSQL treats NULLs as distinct,
so nullable identity would let incomplete rows circumvent uniqueness.
Incomplete identities remain visible only in ``telemetry_raw``.

Run-metadata skeleton (Doc 04 W03): ``run_id`` provenance columns on
both raw and normalized rows carry the run association; no separate
experiment table is created here. The full ``experiments`` run
lifecycle (validity, pairing, controller provenance) belongs to W07
(Doc 05C §44) and would be premature orchestration machinery now.
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_OLD_STATUSES = (
    "RECEIVED_VALID",
    "RECEIVED_INVALID_SCHEMA",
    "RECEIVED_MALFORMED_JSON",
    "RECEIVED_OBSERVED",
)

_NEW_STATUSES = _OLD_STATUSES + ("REJECTED_TOPIC_MISMATCH",)


def _status_list(statuses: tuple[str, ...]) -> str:
    return ", ".join(f"'{status}'" for status in statuses)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE telemetry_raw "
        "DROP CONSTRAINT ck_telemetry_raw_ingest_status"
    )
    op.execute(
        "ALTER TABLE telemetry_raw ADD CONSTRAINT "
        "ck_telemetry_raw_ingest_status "
        f"CHECK (ingest_status IN ({_status_list(_NEW_STATUSES)}))"
    )
    op.execute(
        """
        CREATE TABLE telemetry (
            id BIGSERIAL PRIMARY KEY,
            time TIMESTAMPTZ NOT NULL,
            device_id TEXT NOT NULL,
            boot_id TEXT NOT NULL,
            seq BIGINT NOT NULL,
            run_id TEXT NULL,
            t1_c DOUBLE PRECISION NULL,
            t2_c DOUBLE PRECISION NULL,
            t3_c DOUBLE PRECISION NULL,
            t_air_c DOUBLE PRECISION NULL,
            rh_pct DOUBLE PRECISION NULL,
            door_state TEXT NOT NULL
                CONSTRAINT ck_telemetry_door_state
                CHECK (door_state IN ('OPEN', 'CLOSED', 'UNKNOWN')),
            cooling_voltage_v DOUBLE PRECISION NULL,
            cooling_current_a DOUBLE PRECISION NULL,
            cooling_power_w DOUBLE PRECISION NULL,
            cooling_energy_counter_wh DOUBLE PRECISION NULL,
            applied_cooling TEXT NOT NULL
                CONSTRAINT ck_telemetry_applied_cooling
                CHECK (applied_cooling IN ('ON', 'OFF')),
            applied_duty DOUBLE PRECISION NULL,
            thermal_quality TEXT NOT NULL
                CONSTRAINT ck_telemetry_thermal_quality
                CHECK (thermal_quality IN ('VALID', 'DEGRADED', 'INVALID')),
            environment_quality TEXT NOT NULL
                CONSTRAINT ck_telemetry_environment_quality
                CHECK (environment_quality IN ('VALID', 'DEGRADED', 'INVALID')),
            electrical_quality TEXT NOT NULL
                CONSTRAINT ck_telemetry_electrical_quality
                CHECK (electrical_quality IN ('VALID', 'DEGRADED', 'INVALID')),
            overall_quality TEXT NOT NULL
                CONSTRAINT ck_telemetry_overall_quality
                CHECK (overall_quality IN ('VALID', 'DEGRADED', 'INVALID')),
            device_mode TEXT NULL
                CONSTRAINT ck_telemetry_device_mode
                CHECK (device_mode IN (
                    'BOOT', 'SELF_TEST', 'ONLINE_NORMAL',
                    'ONLINE_DEGRADED', 'SAFE_LOCAL', 'FAULT_LOCKOUT')),
            hardware_config_id TEXT NOT NULL,
            firmware_version TEXT NOT NULL,
            calibration_id TEXT NULL,
            schema_version INTEGER NOT NULL,
            backend_received_at TIMESTAMPTZ NOT NULL,
            raw_id BIGINT NOT NULL REFERENCES telemetry_raw (id),
            CONSTRAINT uq_telemetry_identity
                UNIQUE (device_id, boot_id, seq)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_telemetry_run_id
            ON telemetry (run_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_telemetry_device_time
            ON telemetry (device_id, time)
        """
    )


def downgrade() -> None:
    # NOTE: restoring the W02 status guard fail-closed rejects a
    # database still holding REJECTED_TOPIC_MISMATCH rows (correct:
    # downgrading must not silently reclassify W03 evidence). A genuine
    # W02 database satisfies the guard by construction.
    op.execute("DROP INDEX IF EXISTS ix_telemetry_device_time")
    op.execute("DROP INDEX IF EXISTS ix_telemetry_run_id")
    op.execute("DROP TABLE IF EXISTS telemetry")
    op.execute(
        "ALTER TABLE telemetry_raw "
        "DROP CONSTRAINT ck_telemetry_raw_ingest_status"
    )
    op.execute(
        "ALTER TABLE telemetry_raw ADD CONSTRAINT "
        "ck_telemetry_raw_ingest_status "
        f"CHECK (ingest_status IN ({_status_list(_OLD_STATUSES)}))"
    )
