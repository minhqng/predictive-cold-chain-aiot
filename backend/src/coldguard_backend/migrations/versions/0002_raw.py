"""ColdGuard raw-ingestion table, revision 0002 (C-W02-04).

Creates ``telemetry_raw``: immutable per-delivery MQTT evidence backing
the raw-before-derived principle (Doc 02 section 13). Every received
device-data message lands here with topic, receive time, exact wire
text, parsed JSON projection (nullable: malformed input has none),
SHA-256 of the exact bytes, preliminary ingest status with diagnostics,
and best-effort provenance. Identity/provenance columns are nullable
so malformed rows survive instead of disappearing.

Deliberately absent (owned by later slices, see module docstring of
``coldguard_backend.raw_store``):

* ``UNIQUE(device_id, boot_id, seq)`` enforcement — C-W03-04. W02 keeps
  duplicate QoS 1 deliveries as separate observable rows.
* Timescale hypertable conversion — a later slice; creating one now
  would be premature W03/W05 scope.
* Normalized telemetry / twin / command / experiment tables.

Status values are pinned by a CHECK constraint so no writer can invent
a silent new terminal state.
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_STATUSES = (
    "RECEIVED_VALID",
    "RECEIVED_INVALID_SCHEMA",
    "RECEIVED_MALFORMED_JSON",
    "RECEIVED_OBSERVED",
)


def upgrade() -> None:
    status_list = ", ".join(f"'{status}'" for status in _STATUSES)
    op.execute(
        f"""
        CREATE TABLE telemetry_raw (
            id BIGSERIAL PRIMARY KEY,
            device_id TEXT NULL,
            boot_id TEXT NULL,
            seq BIGINT NULL,
            topic TEXT NOT NULL,
            schema_version INTEGER NULL,
            captured_at TIMESTAMPTZ NULL,
            backend_received_at TIMESTAMPTZ NOT NULL,
            raw_payload TEXT NOT NULL,
            raw_json JSONB NULL,
            payload_sha256 VARCHAR(64) NOT NULL,
            ingest_status TEXT NOT NULL
                CONSTRAINT ck_telemetry_raw_ingest_status
                CHECK (ingest_status IN ({status_list})),
            validation_errors JSONB NULL,
            run_id TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_telemetry_raw_identity
            ON telemetry_raw (device_id, boot_id, seq)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_telemetry_raw_run_id
            ON telemetry_raw (run_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_telemetry_raw_ingest_status
            ON telemetry_raw (ingest_status)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_telemetry_raw_ingest_status")
    op.execute("DROP INDEX IF EXISTS ix_telemetry_raw_run_id")
    op.execute("DROP INDEX IF EXISTS ix_telemetry_raw_identity")
    op.execute("DROP TABLE IF EXISTS telemetry_raw")
