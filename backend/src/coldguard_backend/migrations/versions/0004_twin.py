"""ColdGuard Digital Twin core table, revision 0004 (C-W04).

Creates ``device_twin`` (C-W04-01): materializes device state without
collapsing desired, reported, or derived domains (Doc 05C §41).

Invariants:
- reported_state is mutated ONLY from validated, committed telemetry
  (telemetry_raw + normalized telemetry).
- desired_state represents backend intent only; updates do not alter
  reported_state.
- derived_state represents computed state / model risk outputs (W14+).
- twin_version is a monotonically increasing sequence per device.
- last_boot_id and last_seq record the active reported sample provenance.
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE device_twin (
            device_id TEXT PRIMARY KEY,
            reported_state JSONB NOT NULL DEFAULT '{}'::jsonb,
            desired_state JSONB NOT NULL DEFAULT '{}'::jsonb,
            derived_state JSONB NOT NULL DEFAULT '{}'::jsonb,
            twin_version BIGINT NOT NULL DEFAULT 0
                CONSTRAINT ck_device_twin_version CHECK (twin_version >= 0),
            last_boot_id TEXT NULL,
            last_seq BIGINT NULL
                CONSTRAINT ck_device_twin_seq CHECK (last_seq IS NULL OR last_seq >= 0),
            reported_at TIMESTAMPTZ NULL,
            desired_at TIMESTAMPTZ NULL,
            derived_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_device_twin_updated_at
            ON device_twin (updated_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_device_twin_updated_at")
    op.execute("DROP TABLE IF EXISTS device_twin")
