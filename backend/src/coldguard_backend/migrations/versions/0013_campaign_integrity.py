"""Freeze campaign namespaces and append run-close integrity evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("campaign_id", sa.Text, primary_key=True),
        sa.Column("data_class", sa.Text, nullable=False),
        sa.Column("namespace", JSONB, nullable=False),
        sa.Column("namespace_sha256", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("btrim(campaign_id) <> '' AND data_class IN ('SOFTWARE_SIMULATION','PHYSICAL')", name="ck_campaign_identity"),
        sa.CheckConstraint("jsonb_typeof(namespace) = 'object' AND namespace_sha256 ~ '^[0-9a-f]{64}$'", name="ck_campaign_namespace"),
    )
    op.create_table(
        "campaign_runs",
        sa.Column("run_id", sa.Text, sa.ForeignKey("experiments.run_id"), primary_key=True),
        sa.Column("campaign_id", sa.Text, sa.ForeignKey("campaigns.campaign_id"), nullable=False),
        sa.Column("pair_id", sa.Text, nullable=False),
        sa.Column("arm", sa.Text, nullable=False),
        sa.Column("frozen_run", JSONB, nullable=False),
        sa.UniqueConstraint("campaign_id", "pair_id", "arm", name="uq_campaign_pair_arm"),
        sa.UniqueConstraint("campaign_id", "run_id", name="uq_campaign_run"),
        sa.CheckConstraint("btrim(pair_id) <> '' AND arm IN ('A','B') AND jsonb_typeof(frozen_run) = 'object'", name="ck_campaign_run"),
    )
    op.create_table(
        "campaign_run_closures",
        sa.Column("closure_id", sa.Text, primary_key=True),
        sa.Column("campaign_id", sa.Text, nullable=False),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("report", JSONB, nullable=False),
        sa.Column("report_sha256", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id", "run_id"], ["campaign_runs.campaign_id", "campaign_runs.run_id"]),
        sa.UniqueConstraint("campaign_id", "run_id", "report_sha256", name="uq_campaign_close_report"),
        sa.CheckConstraint("report_sha256 ~ '^[0-9a-f]{64}$' AND btrim(reason) <> ''", name="ck_campaign_close"),
    )
    op.create_index("ix_campaign_close_run", "campaign_run_closures", ["campaign_id", "run_id", "recorded_at", "closure_id"])
    op.execute("""
        CREATE FUNCTION deny_campaign_evidence_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'campaign evidence is immutable; append a new assessment instead'; END $$;
        CREATE FUNCTION guard_campaign_run_identity() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM campaign_runs WHERE run_id = OLD.run_id) AND
               ROW(OLD.run_id,OLD.device_id,OLD.scenario_id,OLD.controller_id,OLD.pair_id,OLD.versions) IS DISTINCT FROM
               ROW(NEW.run_id,NEW.device_id,NEW.scenario_id,NEW.controller_id,NEW.pair_id,NEW.versions) THEN
                RAISE EXCEPTION 'campaign run identity and versions are frozen';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER experiments_campaign_identity BEFORE UPDATE ON experiments
        FOR EACH ROW EXECUTE FUNCTION guard_campaign_run_identity();
    """)
    for table in ("campaigns", "campaign_runs", "campaign_run_closures"):
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION deny_campaign_evidence_change()")


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            LOCK TABLE campaigns, campaign_runs, campaign_run_closures IN ACCESS EXCLUSIVE MODE;
            IF EXISTS (SELECT 1 FROM campaigns) THEN RAISE EXCEPTION 'revision 0013 downgrade refused: campaign evidence exists'; END IF;
        END $$;
    """)
    op.execute("DROP TRIGGER experiments_campaign_identity ON experiments")
    op.execute("DROP FUNCTION guard_campaign_run_identity()")
    op.drop_table("campaign_run_closures")
    op.drop_table("campaign_runs")
    op.drop_table("campaigns")
    op.execute("DROP FUNCTION deny_campaign_evidence_change()")
