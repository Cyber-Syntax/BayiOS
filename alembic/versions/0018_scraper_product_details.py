"""scraper product id, details and id history

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("external_id", sa.Text, nullable=True))
    op.add_column("products", sa.Column("details", JSONB, nullable=True))
    op.add_column("products", sa.Column("source_url", sa.Text, nullable=True))
    op.add_column(
        "products",
        sa.Column(
            "kind",
            sa.Text,
            nullable=False,
            server_default=sa.text("'product'"),
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "scraped_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.drop_constraint(
        op.f("uq_products_name_normalized"), "products", type_="unique"
    )
    op.create_index(
        "ix_products_name_normalized", "products", ["name_normalized"]
    )
    op.create_index(
        "uq_products_external_id", "products", ["external_id"], unique=True
    )
    op.create_check_constraint(
        "external_id_not_empty",
        "products",
        "external_id IS NULL OR char_length(external_id) > 0",
    )
    op.create_check_constraint(
        "kind_valid",
        "products",
        "kind IN ('product', 'warranty', 'explicit')",
    )

    op.create_table(
        "product_external_id_history",
        sa.Column(
            "id",
            sa.Uuid,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "product_id",
            sa.Uuid,
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "external_id", name="uq_product_external_id_history_external_id"
        ),
    )
    op.create_index(
        "ix_product_external_id_history_product_id",
        "product_external_id_history",
        ["product_id"],
    )

    op.drop_constraint(
        op.f("ck_product_import_batches_file_type_valid"),
        "product_import_batches",
        type_="check",
    )
    op.create_check_constraint(
        "file_type_valid",
        "product_import_batches",
        "file_type IN ('csv', 'xlsx', 'json')",
    )

    op.drop_constraint(
        op.f("ck_product_price_history_source_valid"),
        "product_price_history",
        type_="check",
    )
    op.create_check_constraint(
        "source_valid",
        "product_price_history",
        "source IN ('csv_import', 'scraper_import', 'manual', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_product_price_history_source_valid"),
        "product_price_history",
        type_="check",
    )
    op.create_check_constraint(
        "source_valid",
        "product_price_history",
        "source IN ('csv_import', 'manual', 'other')",
    )

    op.drop_constraint(
        op.f("ck_product_import_batches_file_type_valid"),
        "product_import_batches",
        type_="check",
    )
    op.create_check_constraint(
        "file_type_valid",
        "product_import_batches",
        "file_type IN ('csv', 'xlsx')",
    )

    op.drop_index(
        "ix_product_external_id_history_product_id",
        table_name="product_external_id_history",
    )
    op.drop_table("product_external_id_history")

    op.drop_constraint(
        op.f("ck_products_kind_valid"), "products", type_="check"
    )
    op.drop_constraint(
        op.f("ck_products_external_id_not_empty"), "products", type_="check"
    )
    op.drop_index("uq_products_external_id", table_name="products")
    op.drop_index("ix_products_name_normalized", table_name="products")
    op.create_unique_constraint(
        op.f("uq_products_name_normalized"), "products", ["name_normalized"]
    )

    op.drop_column("products", "scraped_at")
    op.drop_column("products", "kind")
    op.drop_column("products", "source_url")
    op.drop_column("products", "details")
    op.drop_column("products", "external_id")
