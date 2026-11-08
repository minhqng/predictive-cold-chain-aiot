"""Persist immutable campaign freeze manifests and exact export bytes."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign_freezes", sa.Column("freeze_id", sa.Text, primary_key=True),
        sa.Column("campaign_id", sa.Text, sa.ForeignKey("campaigns.campaign_id"), nullable=False),
        sa.Column("dataset_id", sa.Text, nullable=False), sa.Column("request_sha256", sa.Text, nullable=False),
        sa.Column("manifest", JSONB, nullable=False), sa.Column("manifest_sha256", sa.Text, nullable=False),
        sa.Column("export_sha256", sa.Text, nullable=False), sa.Column("export_bytes", sa.LargeBinary, nullable=False),
        sa.Column("source_fingerprints", JSONB, nullable=False), sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("btrim(freeze_id) <> '' AND btrim(dataset_id) <> '' AND jsonb_typeof(manifest) = 'object'", name="ck_campaign_freeze_identity"),
        sa.CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$' AND manifest_sha256 ~ '^[0-9a-f]{64}$' AND export_sha256 ~ '^[0-9a-f]{64}$'", name="ck_campaign_freeze_hashes"),
    )
    op.create_index("ix_campaign_freezes_campaign", "campaign_freezes", ["campaign_id", "recorded_at", "freeze_id"])
    op.execute("CREATE TRIGGER campaign_freezes_immutable BEFORE UPDATE OR DELETE ON campaign_freezes FOR EACH ROW EXECUTE FUNCTION deny_campaign_evidence_change()")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        LOCK TABLE campaign_freezes IN ACCESS EXCLUSIVE MODE;
        IF EXISTS (SELECT 1 FROM campaign_freezes) THEN RAISE EXCEPTION 'revision 0014 downgrade refused: frozen evidence exists'; END IF;
        END $$;""")
    op.drop_table("campaign_freezes")
