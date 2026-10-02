"""AI analysis: case analyses and vulnerability indicators.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column[sa.DateTime]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "case_analyses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("redacted_input", sa.Text(), nullable=True),
        sa.Column("suggested_category", sa.String(32), nullable=True),
        sa.Column("summary", sa.String(400), nullable=True),
        sa.Column("suggested_priority", sa.String(32), nullable=True),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        _created_at(),
    )
    op.create_index("ix_case_analyses_tenant_id", "case_analyses", ["tenant_id"])
    op.create_index("ix_case_analyses_case_id", "case_analyses", ["case_id"])

    op.create_table(
        "vulnerability_indicators",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), sa.ForeignKey("case_analyses.id"), nullable=True),
        sa.Column("indicator_type", sa.String(32), nullable=False),
        sa.Column("driver", sa.String(32), nullable=False),
        sa.Column("evidence_quote", sa.Text(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("decided_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
    )
    op.create_index(
        "ix_vulnerability_indicators_tenant_id", "vulnerability_indicators", ["tenant_id"]
    )
    op.create_index("ix_vulnerability_indicators_case_id", "vulnerability_indicators", ["case_id"])


def downgrade() -> None:
    op.drop_table("vulnerability_indicators")
    op.drop_table("case_analyses")
