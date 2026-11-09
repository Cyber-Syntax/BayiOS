"""stock count sessions and items

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
    )


def _ts(name: str, *, nullable: bool = False, default_now: bool = True) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.func.now() if default_now else None,
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "stock_count_sessions",
        _uuid_pk(),
        sa.Column(
            "count_number", sa.BigInteger(), sa.Identity(always=True), nullable=False
        ),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'open'"), nullable=False),
        sa.Column(
            "stock_version", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("summary", JSONB(), nullable=True),
        _ts("started_at"),
        _ts("completed_at", nullable=True, default_now=False),
        sa.Column("created_by_name", sa.Text(), nullable=True),
        sa.Column("created_by_device", sa.Text(), nullable=True),
        sa.Column("completed_by_name", sa.Text(), nullable=True),
        sa.Column("completed_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_count_sessions")),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["product_categories.id"],
            name=op.f("fk_stock_count_sessions_category_id_product_categories"),
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "count_number", name=op.f("uq_stock_count_sessions_count_number")
        ),
        sa.CheckConstraint(
            "status IN ('open', 'review', 'completed', 'cancelled')",
            name=op.f("ck_stock_count_sessions_status_valid"),
        ),
    )
    op.create_index(
        op.f("ix_stock_count_sessions_category_id"),
        "stock_count_sessions",
        ["category_id"],
    )

    op.create_table(
        "stock_count_items",
        _uuid_pk(),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=False),
        sa.Column("system_quantity", sa.Integer(), nullable=False),
        sa.Column("counted_quantity", sa.Integer(), nullable=True),
        sa.Column("difference", sa.Integer(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_count_items")),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["stock_count_sessions.id"],
            name=op.f("fk_stock_count_items_session_id_stock_count_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_stock_count_items_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "session_id",
            "product_id",
            name=op.f("uq_stock_count_items_session_id"),
        ),
        sa.CheckConstraint(
            "counted_quantity IS NULL OR counted_quantity >= 0",
            name=op.f("ck_stock_count_items_counted_quantity_non_negative"),
        ),
        sa.CheckConstraint(
            "difference IS NULL OR counted_quantity IS NOT NULL",
            name=op.f("ck_stock_count_items_difference_requires_counted_quantity"),
        ),
    )
    op.create_index(
        op.f("ix_stock_count_items_session_id"),
        "stock_count_items",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_stock_count_items_session_id"), table_name="stock_count_items")
    op.drop_table("stock_count_items")
    op.drop_index(
        op.f("ix_stock_count_sessions_category_id"),
        table_name="stock_count_sessions",
    )
    op.drop_table("stock_count_sessions")
