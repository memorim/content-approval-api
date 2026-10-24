"""Add durable delivery attempts and leases to existing outbox events."""

import sqlalchemy as sa

from alembic import op

revision = "0002_outbox_delivery"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "outbox_events", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")
    )
    for name in ["next_attempt_at", "lease_until", "dead_at", "published_at"]:
        op.add_column("outbox_events", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.add_column("outbox_events", sa.Column("lease_token", sa.String(36), nullable=True))
    op.add_column("outbox_events", sa.Column("last_error", sa.String(80), nullable=True))
    op.create_index(
        "ix_outbox_delivery_due", "outbox_events", ["published", "dead_at", "next_attempt_at"]
    )


def downgrade():
    op.drop_index("ix_outbox_delivery_due", table_name="outbox_events")
    with op.batch_alter_table("outbox_events") as batch:
        for name in [
            "published_at",
            "dead_at",
            "last_error",
            "lease_token",
            "lease_until",
            "next_attempt_at",
            "attempts",
        ]:
            batch.drop_column(name)
