"""Accounts, saved views and reviewed response drafts."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("password_hash", sa.String(256), nullable=True))
    op.add_column(
        "users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "users", sa.Column("failed_logins", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    for name, columns, indexes in [
        (
            "login_sessions",
            [
                sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
                sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
                sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            ],
            ["user_id"],
        ),
        (
            "saved_views",
            [
                sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
                sa.Column("name", sa.String(80), nullable=False),
                sa.Column("filters", sa.JSON(), nullable=False),
            ],
            ["user_id"],
        ),
        (
            "response_drafts",
            [
                sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
                sa.Column("body", sa.Text(), nullable=False),
                sa.Column("provider", sa.String(32), nullable=False),
                sa.Column(
                    "created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False
                ),
                sa.Column(
                    "approved_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True
                ),
                sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
                sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            ],
            ["case_id"],
        ),
    ]:
        op.create_table(
            name,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            *columns,
        )
        for column in ["tenant_id", *indexes]:
            op.create_index(f"ix_{name}_{column}", name, [column])


def downgrade():
    for name in ["response_drafts", "saved_views", "login_sessions"]:
        op.drop_table(name)
    for name in ["locked_until", "failed_logins", "is_admin", "password_hash"]:
        op.drop_column("users", name)
