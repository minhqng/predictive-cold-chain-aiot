"""Durable reconciliation admission boundary and legacy audit (W05-FIX-02).

Replaces the untrustworthy ``raw.id < min(normalized.raw_id)`` historical
heuristic with explicit, durable evidence:

* ``reconciliation_boundary`` records the instant from which the upgraded
  ingestion pipeline guarantees that every ``RECEIVED_VALID`` raw delivery
  yields a normalized sample or an explicit, observable failure. The
  migration stamps this with the upgrade transaction time. A raw delivery
  received at/after this instant that has no normalized identity is a
  provable normalization failure — never "historical".

* ``reconciliation_legacy_audit`` holds explicit per-row operator verdicts
  for deliveries received *before* the boundary, where row ordering alone
  cannot distinguish genuine pre-normalization (W02) evidence from a real
  normalization failure. Without an audit verdict such rows are reported as
  ``historical_unverified`` and fail reconciliation (fail closed); they are
  never silently promoted to confirmed historical.

No raw evidence is rewritten or backfilled. Downgrade drops only this
metadata, leaving raw and normalized telemetry untouched.
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reconciliation_boundary",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "normalization_active_since", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("basis", sa.Text, nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint("id = 1", name="ck_reconciliation_boundary_singleton"),
    )
    op.execute(
        "INSERT INTO reconciliation_boundary (id, normalization_active_since, basis) "
        "VALUES (1, statement_timestamp(), 'migration:0007')"
    )
    op.create_table(
        "reconciliation_legacy_audit",
        sa.Column(
            "raw_id",
            sa.BigInteger,
            sa.ForeignKey("telemetry_raw.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("verdict", sa.Text, nullable=False),
        sa.Column("basis", sa.Text, nullable=False),
        sa.Column("audited_by", sa.Text, nullable=False),
        sa.Column(
            "audited_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint(
            "verdict IN ('CONFIRMED_HISTORICAL', 'CONFIRMED_FAILURE')",
            name="ck_reconciliation_legacy_audit_verdict",
        ),
    )


def downgrade() -> None:
    op.drop_table("reconciliation_legacy_audit")
    op.drop_table("reconciliation_boundary")