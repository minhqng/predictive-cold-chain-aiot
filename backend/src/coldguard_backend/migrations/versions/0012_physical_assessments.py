"""Guard command provenance and persist independently signed physical assessments."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_PREVIOUS_VERIFICATION = "'NONE','PENDING','ELECTRICAL_VERIFIED','THERMAL_VERIFIED','VERIFIED','FAILED_VERIFICATION'"


def upgrade() -> None:
    op.drop_constraint("ck_commands_verification_status", "commands", type_="check")
    op.create_check_constraint(
        "ck_commands_verification_status", "commands",
        f"verification_status IN ({_PREVIOUS_VERIFICATION},'EXECUTED')",
    )
    op.create_table(
        "physical_assessments",
        sa.Column("assessment_id", sa.Text, primary_key=True),
        sa.Column("command_id", sa.Text, sa.ForeignKey("commands.command_id"), nullable=False),
        sa.Column("authority_id", sa.Text, nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claim", JSONB, nullable=False),
        sa.Column("claim_sha256", sa.Text, nullable=False),
        sa.Column("signature_sha256", sa.Text, nullable=False),
        sa.CheckConstraint(
            "stage IN ('EXECUTED','ELECTRICAL_VERIFIED','THERMAL_VERIFIED','VERIFIED','FAILED_VERIFICATION')",
            name="ck_physical_assessment_stage",
        ),
    )
    op.create_index(
        "ix_physical_assessments_command", "physical_assessments",
        ["command_id", "assessed_at", "assessment_id"],
    )
    op.execute("""
        CREATE TRIGGER physical_assessments_immutable BEFORE UPDATE ON physical_assessments
        FOR EACH ROW EXECUTE FUNCTION deny_prediction_evidence_update();
    """)
    op.create_table(
        "policy_approvals",
        sa.Column("command_id", sa.Text, sa.ForeignKey("commands.command_id"), primary_key=True),
        sa.Column("authority_id", sa.Text, nullable=False),
        sa.Column("policy_version", sa.Text, nullable=False),
        sa.Column("command_sha256", sa.Text, nullable=False),
        sa.Column("signature_sha256", sa.Text, nullable=False),
        sa.Column("model_spec", JSONB, nullable=False),
        sa.Column("model_spec_sha256", sa.Text, nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "command_sha256 ~ '^[0-9a-f]{64}$' AND signature_sha256 ~ '^[0-9a-f]{64}$' "
            "AND model_spec_sha256 ~ '^[0-9a-f]{64}$'", name="ck_policy_approval_hashes",
        ),
    )
    op.execute("""
        CREATE TRIGGER policy_approvals_immutable BEFORE UPDATE ON policy_approvals
        FOR EACH ROW EXECUTE FUNCTION deny_prediction_evidence_update();
    """)
    columns = (
        "command_id", "device_id", "run_id", "schema_version", "created_at", "expires_at",
        "controller_id", "policy_version", "prediction_id", "reason_code", "action_cooling",
        "action_duty", "payload_sha256", "expected_twin_version",
    )
    old = ", ".join(f"OLD.{column}" for column in columns)
    new = ", ".join(f"NEW.{column}" for column in columns)
    op.execute(f"""
        CREATE FUNCTION guard_command_provenance() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF ROW({old}) IS DISTINCT FROM ROW({new}) THEN
                RAISE EXCEPTION 'command provenance is immutable';
            END IF;
            RETURN NEW;
        END
        $$;
    """)
    op.execute("""
        CREATE TRIGGER commands_provenance_immutable BEFORE UPDATE ON commands
        FOR EACH ROW EXECUTE FUNCTION guard_command_provenance();
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            LOCK TABLE commands, physical_assessments, policy_approvals IN ACCESS EXCLUSIVE MODE;
            IF EXISTS (SELECT 1 FROM commands WHERE verification_status = 'EXECUTED') THEN
                RAISE EXCEPTION 'revision 0012 downgrade refused: execution evidence exists';
            END IF;
            IF EXISTS (SELECT 1 FROM physical_assessments) THEN
                RAISE EXCEPTION 'revision 0012 downgrade refused: physical assessment evidence exists';
            END IF;
            IF EXISTS (SELECT 1 FROM policy_approvals) THEN
                RAISE EXCEPTION 'revision 0012 downgrade refused: policy approval evidence exists';
            END IF;
        END
        $$;
    """)
    op.execute("DROP TRIGGER commands_provenance_immutable ON commands")
    op.execute("DROP FUNCTION guard_command_provenance()")
    op.drop_table("policy_approvals")
    op.drop_table("physical_assessments")
    op.drop_constraint("ck_commands_verification_status", "commands", type_="check")
    op.create_check_constraint(
        "ck_commands_verification_status", "commands",
        f"verification_status IN ({_PREVIOUS_VERIFICATION})",
    )
