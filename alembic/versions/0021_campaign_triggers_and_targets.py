"""campaign triggers, category targets and one-time benefit rules

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DISCOUNT_TYPE_SQL = "('percent', 'fixed_amount', 'special_price', 'gift', 'info_only')"
BASE_PRICE_TYPE_SQL = "('regular', 'website_discounted', 'manual')"


def upgrade() -> None:
    op.add_column(
        "campaign_versions",
        sa.Column(
            "combines_with_others",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "campaign_versions",
        sa.Column("exclusion_group", sa.Text, nullable=True),
    )
    op.add_column(
        "campaign_versions",
        sa.Column("min_basket_total", sa.Numeric(12, 2), nullable=True),
    )
    op.create_check_constraint(
        "min_basket_total_non_negative",
        "campaign_versions",
        "min_basket_total IS NULL OR min_basket_total >= 0",
    )

    op.add_column(
        "campaign_version_products",
        sa.Column("category_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "campaign_version_products",
        sa.Column("discount_type", sa.Text, nullable=True),
    )
    op.add_column(
        "campaign_version_products",
        sa.Column("discount_value", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "campaign_version_products",
        sa.Column("base_price_type", sa.Text, nullable=True),
    )
    op.add_column(
        "campaign_version_products",
        sa.Column("applies_per_unit", sa.Boolean, nullable=True),
    )
    op.create_foreign_key(
        "fk_campaign_version_products_category_id",
        "campaign_version_products",
        "product_categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_campaign_version_products_category_id",
        "campaign_version_products",
        ["category_id"],
    )
    op.create_check_constraint(
        "product_or_category_not_both",
        "campaign_version_products",
        "product_id IS NULL OR category_id IS NULL",
    )
    op.create_check_constraint(
        "relation_discount_type_valid",
        "campaign_version_products",
        f"discount_type IS NULL OR discount_type IN {DISCOUNT_TYPE_SQL}",
    )
    op.create_check_constraint(
        "relation_base_price_type_valid",
        "campaign_version_products",
        "base_price_type IS NULL "
        f"OR base_price_type IN {BASE_PRICE_TYPE_SQL}",
    )
    op.create_check_constraint(
        "relation_discount_value_valid",
        "campaign_version_products",
        "(discount_type IS NULL AND discount_value IS NULL) "
        "OR (discount_type = 'percent' AND discount_value IS NOT NULL "
        "AND discount_value >= 0 AND discount_value <= 100) "
        "OR (discount_type IN ('fixed_amount', 'special_price') "
        "AND discount_value IS NOT NULL AND discount_value >= 0) "
        "OR (discount_type IN ('gift', 'info_only') "
        "AND discount_value IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_campaign_version_products_relation_discount_value_valid",
        "campaign_version_products",
        type_="check",
    )
    op.drop_constraint(
        "ck_campaign_version_products_relation_base_price_type_valid",
        "campaign_version_products",
        type_="check",
    )
    op.drop_constraint(
        "ck_campaign_version_products_relation_discount_type_valid",
        "campaign_version_products",
        type_="check",
    )
    op.drop_constraint(
        "ck_campaign_version_products_product_or_category_not_both",
        "campaign_version_products",
        type_="check",
    )
    op.drop_index(
        "ix_campaign_version_products_category_id",
        table_name="campaign_version_products",
    )
    op.drop_constraint(
        "fk_campaign_version_products_category_id",
        "campaign_version_products",
        type_="foreignkey",
    )
    op.drop_column("campaign_version_products", "applies_per_unit")
    op.drop_column("campaign_version_products", "base_price_type")
    op.drop_column("campaign_version_products", "discount_value")
    op.drop_column("campaign_version_products", "discount_type")
    op.drop_column("campaign_version_products", "category_id")

    op.drop_constraint(
        "ck_campaign_versions_min_basket_total_non_negative",
        "campaign_versions",
        type_="check",
    )
    op.drop_column("campaign_versions", "min_basket_total")
    op.drop_column("campaign_versions", "exclusion_group")
    op.drop_column("campaign_versions", "combines_with_others")
