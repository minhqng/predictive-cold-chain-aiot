"""Storage baseline indexes for time-range, run, device and clockless telemetry (C-W05-02).

TimescaleDB constraint evaluation:
- In TimescaleDB, converting a table to a hypertable requires every UNIQUE constraint
  to include the partitioning time column.
- ColdGuard domain identity is strictly UNIQUE (device_id, boot_id, seq).
- In Schema 2 (Member A clockless serial frames), event time is NULL. TimescaleDB
  prohibits NULL time values in partitioning columns.
- Using backend_received_at as partition column would require it in the UNIQUE constraint
  (device_id, boot_id, seq, backend_received_at), which destroys deduplication because
  redeliveries arrive at different receive times.
- Manufacturing synthetic event times from uptime would violate physical measurement
  truth (Doc 01/02).
- Therefore, authoritative telemetry storage remains a justified indexed PostgreSQL
  baseline preserving UNIQUE (device_id, boot_id, seq) and accommodating clockless rows.

This revision adds:
- ix_telemetry_device_received_at: (device_id, backend_received_at DESC)
- ix_telemetry_run_received_at: (run_id, backend_received_at DESC)
- ix_telemetry_clockless: (device_id, backend_received_at DESC) WHERE time IS NULL
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_telemetry_device_received_at "
        "ON telemetry (device_id, backend_received_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_telemetry_run_received_at "
        "ON telemetry (run_id, backend_received_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_telemetry_clockless "
        "ON telemetry (device_id, backend_received_at DESC) "
        "WHERE time IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_telemetry_clockless")
    op.execute("DROP INDEX IF EXISTS ix_telemetry_run_received_at")
    op.execute("DROP INDEX IF EXISTS ix_telemetry_device_received_at")
