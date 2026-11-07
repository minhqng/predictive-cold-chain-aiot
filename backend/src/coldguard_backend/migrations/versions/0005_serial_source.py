"""Store clockless serial telemetry without inventing event time."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _quality_constraints(*, clockless: bool) -> None:
    for column in ("thermal_quality", "environment_quality", "electrical_quality", "overall_quality"):
        name = f"ck_telemetry_{column}"
        condition = f"{column} IN ('VALID', 'DEGRADED', 'INVALID')"
        if clockless:
            condition += f" OR (schema_version = 2 AND {column} = 'UNKNOWN')"
        op.drop_constraint(name, "telemetry", type_="check")
        op.create_check_constraint(name, "telemetry", condition)


def upgrade() -> None:
    op.add_column("telemetry", sa.Column("serial_source", JSONB))
    op.alter_column("telemetry", "time", nullable=True)
    _quality_constraints(clockless=True)
    op.create_check_constraint(
        "ck_telemetry_event_time",
        "telemetry",
        "(schema_version = 1 AND time IS NOT NULL AND serial_source IS NULL) OR "
        "(schema_version = 2 AND time IS NULL AND serial_source IS NOT NULL "
        "AND jsonb_typeof(serial_source) = 'object')",
    )


def downgrade() -> None:
    # PostgreSQL refuses this change when clockless samples still exist.
    # The migration transaction then preserves the schema and observations.
    op.alter_column("telemetry", "time", nullable=False)
    _quality_constraints(clockless=False)
    op.drop_constraint("ck_telemetry_event_time", "telemetry", type_="check")
    op.drop_column("telemetry", "serial_source")
