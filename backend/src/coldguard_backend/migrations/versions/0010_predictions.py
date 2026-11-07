"""Persist immutable predictions and ordered telemetry input provenance."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "predictions",
        sa.Column("prediction_id", sa.Text, primary_key=True),
        sa.Column("device_id", sa.Text, nullable=False),
        sa.Column("run_id", sa.Text, sa.ForeignKey("experiments.run_id")),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("model_sha256", sa.Text, nullable=False),
        sa.Column("feature_version", sa.Text, nullable=False),
        sa.Column("feature_schema_sha256", sa.Text, nullable=False),
        sa.Column("risk_score", sa.Float, nullable=False),
        sa.Column("horizon_sec", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latest_input_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fresh_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_sha256", sa.Text, nullable=False),
        sa.CheckConstraint(
            "model_sha256 ~ '^[0-9a-f]{64}$' AND feature_schema_sha256 ~ '^[0-9a-f]{64}$' "
            "AND payload_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_predictions_hashes",
        ),
        sa.CheckConstraint(
            "risk_score BETWEEN 0 AND 1 AND horizon_sec > 0", name="ck_predictions_risk_horizon",
        ),
        sa.CheckConstraint(
            "input_window_start <= latest_input_at AND latest_input_at <= input_window_end "
            "AND input_window_end <= created_at AND created_at <= recorded_at "
            "AND latest_input_at < fresh_until "
            "AND fresh_until <= latest_input_at + make_interval(secs => horizon_sec)",
            name="ck_predictions_timing",
        ),
    )
    op.create_index(
        "ix_predictions_device_current", "predictions",
        ["device_id", "latest_input_at", "created_at", "prediction_id"],
    )
    op.create_index(
        "ix_predictions_run_history", "predictions",
        ["run_id", "device_id", "recorded_at", "prediction_id"],
    )
    op.create_table(
        "prediction_inputs",
        sa.Column("prediction_id", sa.Text, sa.ForeignKey("predictions.prediction_id"), primary_key=True),
        sa.Column("ordinal", sa.Integer, primary_key=True),
        sa.Column("telemetry_id", sa.BigInteger, sa.ForeignKey("telemetry.id"), nullable=False),
        sa.CheckConstraint("ordinal >= 0", name="ck_prediction_inputs_ordinal"),
        sa.UniqueConstraint("prediction_id", "telemetry_id", name="uq_prediction_inputs_sample"),
    )
    op.execute("""
        CREATE FUNCTION deny_prediction_evidence_update() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'prediction evidence is immutable';
        END
        $$;
    """)
    for table in ("predictions", "prediction_inputs"):
        op.execute(f"""
            CREATE TRIGGER {table}_immutable BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION deny_prediction_evidence_update();
        """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            LOCK TABLE predictions, prediction_inputs IN ACCESS EXCLUSIVE MODE;
            IF EXISTS (SELECT 1 FROM predictions) THEN
                RAISE EXCEPTION 'revision 0010 downgrade refused: prediction evidence exists';
            END IF;
        END
        $$;
    """)
    op.drop_table("prediction_inputs")
    op.drop_table("predictions")
    op.execute("DROP FUNCTION deny_prediction_evidence_update()")
