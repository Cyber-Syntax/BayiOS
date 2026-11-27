"""stock count quick mode, cancellation and reversal metadata

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stock_count_sessions",
        sa.Column("mode", sa.Text(), nullable=False, server_default=sa.text("'category'")),
    )
    op.create_check_constraint(
        "mode_valid",
        "stock_count_sessions",
        "mode IN ('category', 'quick')",
    )
    op.add_column(
        "stock_count_sessions",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "stock_count_sessions",
        sa.Column("cancelled_by_name", sa.Text(), nullable=True),
    )
    op.add_column(
        "stock_count_sessions",
        sa.Column("cancelled_by_device", sa.Text(), nullable=True),
    )
    op.add_column(
        "stock_count_sessions",
        sa.Column("cancel_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "stock_count_sessions",
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stock_count_sessions", "reversed_at")
    op.drop_column("stock_count_sessions", "cancel_reason")
    op.drop_column("stock_count_sessions", "cancelled_by_device")
    op.drop_column("stock_count_sessions", "cancelled_by_name")
    op.drop_column("stock_count_sessions", "cancelled_at")
    op.drop_constraint(
        "ck_stock_count_sessions_mode_valid",
        "stock_count_sessions",
        type_="check",
    )
    op.drop_column("stock_count_sessions", "mode")
