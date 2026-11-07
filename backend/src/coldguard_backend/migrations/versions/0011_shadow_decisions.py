"""Persist hypothetical policy decisions separately from executable commands."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shadow_decisions",
        sa.Column("decision_id", sa.Text, primary_key=True),
        sa.Column("prediction_id", sa.Text, sa.ForeignKey("predictions.prediction_id"), nullable=False, unique=True),
        sa.Column("policy_version", sa.Text, nullable=False),
        sa.Column("would_command", JSONB(none_as_null=True)),
        sa.Column("reason_code", sa.Text),
        sa.Column("reason_detail", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("feature_names", JSONB, nullable=False),
        sa.Column("feature_values", JSONB, nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_duration_ms", sa.Float, nullable=False),
        sa.Column("payload_sha256", sa.Text, nullable=False),
        sa.CheckConstraint(
            "status IN ('EVALUATED', 'SKIPPED_STALE') AND (status = 'EVALUATED' OR would_command IS NULL)",
            name="ck_shadow_decisions_status",
        ),
        sa.CheckConstraint(
            "(would_command IS NULL OR jsonb_typeof(would_command) = 'object') "
            "AND policy_duration_ms >= 0 AND payload_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_shadow_decisions_evidence",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(feature_names) = 'array' AND jsonb_typeof(feature_values) = 'array' "
            "AND jsonb_array_length(feature_names) = jsonb_array_length(feature_values) "
            "AND jsonb_array_length(feature_names) > 0",
            name="ck_shadow_decisions_features",
        ),
    )
    op.execute("""
        CREATE TRIGGER shadow_decisions_immutable BEFORE UPDATE ON shadow_decisions
        FOR EACH ROW EXECUTE FUNCTION deny_prediction_evidence_update();
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            LOCK TABLE shadow_decisions IN ACCESS EXCLUSIVE MODE;
            IF EXISTS (SELECT 1 FROM shadow_decisions) THEN
                RAISE EXCEPTION 'revision 0011 downgrade refused: shadow evidence exists';
            END IF;
        END
        $$;
    """)
    op.drop_table("shadow_decisions")
