"""Keep credential hashes and user state in the application's persistent database."""

import sqlalchemy as sa
from alembic import op

revision = "0003_shared_credentials"
down_revision = "0002_outbox_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "credential_users",
        sa.Column("workspace_id", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.String(128), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "credential_tokens",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["credential_users.workspace_id", "credential_users.user_id"],
        ),
    )
    op.create_index("ix_credential_token_user", "credential_tokens", ["workspace_id", "user_id"])


def downgrade():
    op.drop_index("ix_credential_token_user", table_name="credential_tokens")
    op.drop_table("credential_tokens")
    op.drop_table("credential_users")
