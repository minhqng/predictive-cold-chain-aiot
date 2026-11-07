"""Persist independent device Twin domains and conservative boot fencing."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy rows have no durable live admission decision.
    op.add_column(
        "telemetry",
        sa.Column("twin_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "device_twin",
        sa.Column("device_id", sa.Text(), primary_key=True),
        sa.Column("reported_state", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("desired_state", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("derived_state", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("twin_version", sa.BigInteger(), nullable=False),
        sa.Column("last_boot_id", sa.Text()),
        sa.Column("last_seq", sa.BigInteger()),
        sa.Column("last_reported_at", sa.DateTime(timezone=True)),
        sa.Column("last_desired_at", sa.DateTime(timezone=True)),
        sa.Column("last_derived_at", sa.DateTime(timezone=True)),
        sa.Column("connectivity_state", sa.Text(), nullable=False, server_default="UNKNOWN"),
        sa.Column("device_mode", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("twin_version > 0", name="ck_device_twin_version"),
        sa.CheckConstraint(
            "(last_boot_id IS NULL AND last_seq IS NULL AND last_reported_at IS NULL) OR "
            "(last_boot_id IS NOT NULL AND last_seq IS NOT NULL AND last_seq >= 0 "
            "AND last_reported_at IS NOT NULL)",
            name="ck_device_twin_reported_identity",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reported_state) = 'object' AND "
            "jsonb_typeof(desired_state) = 'object' AND "
            "jsonb_typeof(derived_state) = 'object'",
            name="ck_device_twin_domains",
        ),
    )
    op.create_table(
        "device_twin_retired_boot",
        sa.Column(
            "device_id", sa.Text(), sa.ForeignKey("device_twin.device_id"), primary_key=True,
        ),
        sa.Column("boot_id", sa.Text(), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("device_twin_retired_boot")
    op.drop_table("device_twin")
    op.drop_column("telemetry", "twin_eligible")
