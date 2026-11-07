"""Persist experiment runs and their lifecycle history."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("run_id", sa.Text, primary_key=True),
        sa.Column("device_id", sa.Text, nullable=False),
        sa.Column("scenario_id", sa.Text, nullable=False),
        sa.Column("controller_id", sa.Text, nullable=False),
        sa.Column("pair_id", sa.Text),
        sa.Column("versions", JSONB, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "btrim(run_id) <> '' AND btrim(device_id) <> '' AND btrim(scenario_id) <> '' "
            "AND btrim(controller_id) <> '' AND (pair_id IS NULL OR btrim(pair_id) <> '')",
            name="ck_experiments_identity",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(versions) = 'object' AND versions <> '{}'::jsonb",
            name="ck_experiments_versions",
        ),
        sa.CheckConstraint(
            "status IN ('PLANNED', 'ARMED', 'RUNNING', 'COMPLETED_RAW', "
            "'VALIDITY_REVIEW', 'VALID', 'INVALID', 'ABORTED')",
            name="ck_experiments_status",
        ),
        sa.CheckConstraint(
            "(started_at IS NULL OR started_at >= created_at) AND "
            "(ended_at IS NULL OR ended_at >= coalesce(started_at, created_at)) AND "
            "(status NOT IN ('PLANNED', 'ARMED') OR started_at IS NULL) AND "
            "(status IN ('PLANNED', 'ARMED', 'ABORTED') OR started_at IS NOT NULL) AND "
            "((status IN ('COMPLETED_RAW', 'VALIDITY_REVIEW', 'VALID', 'INVALID', 'ABORTED'))"
            " = (ended_at IS NOT NULL))",
            name="ck_experiments_times",
        ),
    )
    op.create_index("ix_experiments_pair", "experiments", ["pair_id", "controller_id"])
    op.create_index("ix_experiments_device", "experiments", ["device_id", "created_at"])
    op.create_table(
        "experiment_transitions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Text, sa.ForeignKey("experiments.run_id"), nullable=False),
        sa.Column("from_status", sa.Text),
        sa.Column("to_status", sa.Text, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_experiment_transitions_run", "experiment_transitions", ["run_id", "id"])


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            LOCK TABLE experiments, experiment_transitions IN ACCESS EXCLUSIVE MODE;
            IF EXISTS (SELECT 1 FROM experiments) THEN
                RAISE EXCEPTION 'revision 0009 downgrade refused: run evidence exists';
            END IF;
        END
        $$;
    """)
    op.drop_table("experiment_transitions")
    op.drop_table("experiments")
