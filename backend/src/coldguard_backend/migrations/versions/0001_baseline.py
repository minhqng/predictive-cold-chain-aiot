"""ColdGuard migration baseline, revision 0001 (C-W01-04).

Zero-domain-table baseline: establishes real, verifiable Alembic history
without creating W02/W03 tables prematurely (no telemetry_raw,
normalized telemetry, device_twin, commands, predictions or experiments
tables here). Those arrive as later reviewed revisions owned by the
responsible slice.

Upgrade is a safe no-op that records the revision in ``alembic_version``.
Downgrade is a matching no-op: there is deliberately no destructive
downgrade behavior to test in W01.
"""

from __future__ import annotations

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Intentionally no domain tables in the W01 baseline.
    pass


def downgrade() -> None:
    # Nothing to drop; downgrade of the empty baseline is a no-op.
    pass
