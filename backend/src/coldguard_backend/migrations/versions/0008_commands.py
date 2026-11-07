"""Durable command lifecycle, attempts, ACK evidence and transitions (C-W06-01).

Creates the Member C command path storage. Design invariants:

* ``commands.command_id`` is the immutable logical identity (PRIMARY KEY). A
  retry reuses it; a conflicting payload under the same id is rejected by the
  service via ``payload_sha256`` comparison, never silently overwritten.
* ``expires_at > created_at`` is database-enforced; out-of-range duty and
  unknown actions/statuses are CHECK-constrained so invalid intent cannot enter
  the executable path.
* Broker publish outcomes (``command_attempts``), device ACK receipts
  (``command_acks``, including unmatched/invalid/conflicting evidence) and
  lifecycle ``command_transitions`` are append-only audit rows. ACK evidence is
  retained even when it cannot be correlated (no foreign key on
  ``command_acks.command_id``), so forged/unmatched ACKs remain observable.
* No column records physical success as proven: ``verification_status`` starts
  at ``NONE`` and W06 software never advances it beyond ``NONE``. ACK acceptance
  is protocol evidence, not electrical/thermal verification (Doc 02 §32.2).

Downgrade drops only these tables; telemetry/twin/reconciliation are untouched.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

LIFECYCLE_STATES = (
    "CREATED", "VALIDATED", "PUBLISHED", "ACK_ACCEPTED", "ACK_REJECTED",
    "EXPIRED", "UNKNOWN", "PUBLISH_FAILED",
    "EXECUTED", "ELECTRICAL_VERIFIED", "THERMAL_VERIFIED", "VERIFIED",
    "FAILED_VERIFICATION",
)
VERIFICATION_STATES = (
    "NONE", "PENDING", "ELECTRICAL_VERIFIED", "THERMAL_VERIFIED", "VERIFIED",
    "FAILED_VERIFICATION",
)
ATTEMPT_OUTCOMES = ("PENDING", "PUBACK", "FAILED", "TIMEOUT", "UNKNOWN")
ACK_VALIDITY = (
    "VALID", "INVALID_SCHEMA", "MALFORMED_JSON", "TOPIC_MISMATCH", "UNMATCHED",
    "CONFLICT", "DUPLICATE", "LATE",
)


def _in(column: str, values) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    op.create_table(
        "commands",
        sa.Column("command_id", sa.Text, primary_key=True),
        sa.Column("device_id", sa.Text, nullable=False),
        sa.Column("run_id", sa.Text),
        sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("ack_at", sa.DateTime(timezone=True)),
        sa.Column("controller_id", sa.Text, nullable=False),
        sa.Column("policy_version", sa.Text, nullable=False),
        sa.Column("prediction_id", sa.Text),
        sa.Column("reason_code", sa.Text, nullable=False),
        sa.Column("action_cooling", sa.Text, nullable=False),
        sa.Column("action_duty", sa.Float),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("reject_reason", sa.Text),
        sa.Column(
            "verification_status", sa.Text, nullable=False, server_default="NONE"
        ),
        sa.Column("payload_sha256", sa.Text, nullable=False),
        sa.Column("expected_twin_version", sa.BigInteger),
        sa.Column("desired_twin_version", sa.BigInteger),
        sa.Column(
            "created_db_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_commands_expiry_after_created"),
        sa.CheckConstraint(_in("action_cooling", ("ON", "OFF")), name="ck_commands_action_cooling"),
        sa.CheckConstraint(
            "action_duty IS NULL OR (action_duty >= 0.0 AND action_duty <= 1.0)",
            name="ck_commands_action_duty",
        ),
        sa.CheckConstraint(_in("status", LIFECYCLE_STATES), name="ck_commands_status"),
        sa.CheckConstraint(
            _in("verification_status", VERIFICATION_STATES),
            name="ck_commands_verification_status",
        ),
    )
    op.create_index("ix_commands_device_status", "commands", ["device_id", "status"])
    op.create_index("ix_commands_status_expiry", "commands", ["status", "expires_at"])

    op.create_table(
        "command_attempts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "command_id",
            sa.Text,
            sa.ForeignKey("commands.command_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_no", sa.Integer, nullable=False),
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column("broker_reason", sa.Text),
        sa.Column("mqtt_mid", sa.Integer),
        sa.Column("payload_sha256", sa.Text, nullable=False),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(_in("outcome", ATTEMPT_OUTCOMES), name="ck_command_attempts_outcome"),
        sa.UniqueConstraint("command_id", "attempt_no", name="uq_command_attempts_command_no"),
    )

    op.create_table(
        "command_acks",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("command_id", sa.Text),
        sa.Column("topic_device_id", sa.Text, nullable=False),
        sa.Column("payload_device_id", sa.Text),
        sa.Column("boot_id", sa.Text),
        sa.Column("ack_seq", sa.BigInteger),
        sa.Column("device_status", sa.Text),
        sa.Column("reason_code", sa.Text),
        sa.Column("applied_cooling", sa.Text),
        sa.Column("applied_duty", sa.Float),
        sa.Column("device_mode", sa.Text),
        sa.Column("uptime_ms", sa.BigInteger),
        sa.Column("ack_time", sa.DateTime(timezone=True)),
        sa.Column("backend_received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", sa.Text, nullable=False),
        sa.Column("payload_sha256", sa.Text, nullable=False),
        sa.Column("validity", sa.Text, nullable=False),
        sa.Column("diagnostics", JSONB),
        sa.Column("time_sync_state", sa.Text),
        sa.Column("expiry_evaluable", sa.Boolean),
        sa.Column("output_stage", sa.Text),
        sa.Column("fault_code", sa.Text),
        sa.Column("reapplied", sa.Boolean),
        sa.Column("canonical_status", sa.Text),
        sa.Column(
            "received_db_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint(_in("validity", ACK_VALIDITY), name="ck_command_acks_validity"),
    )
    op.create_index("ix_command_acks_command", "command_acks", ["command_id"])
    op.create_index(
        "ix_command_acks_device_received",
        "command_acks",
        ["topic_device_id", "backend_received_at"],
    )

    op.create_table(
        "command_transitions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "command_id",
            sa.Text,
            sa.ForeignKey("commands.command_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.Text),
        sa.Column("to_status", sa.Text, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
    )
    op.create_index(
        "ix_command_transitions_command", "command_transitions", ["command_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_table("command_transitions")
    op.drop_table("command_acks")
    op.drop_table("command_attempts")
    op.drop_table("commands")