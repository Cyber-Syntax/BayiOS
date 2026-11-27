"""normalize zero Oliz prices to NULL

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Keep an audit trail before clearing the invalid zero prices.
    op.execute(
        """
        INSERT INTO product_price_history (
            id,
            product_id,
            field_name,
            old_value,
            new_value,
            source,
            changed_at,
            changed_by_name
        )
        SELECT
            gen_random_uuid(),
            id,
            'website_discounted_price',
            website_discounted_price,
            NULL,
            'other',
            now(),
            'Sistem'
        FROM products
        WHERE website_discounted_price = 0
        """
    )
    op.execute(
        "UPDATE products SET website_discounted_price = NULL "
        "WHERE website_discounted_price = 0"
    )
    op.execute(
        "UPDATE offer_items SET website_price_snapshot = NULL "
        "WHERE website_price_snapshot = 0"
    )
    op.create_check_constraint(
        "website_discounted_price_positive",
        "products",
        "website_discounted_price IS NULL OR website_discounted_price > 0",
    )
    op.create_check_constraint(
        "website_price_positive",
        "offer_items",
        "website_price_snapshot IS NULL OR website_price_snapshot > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_offer_items_website_price_positive"),
        "offer_items",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_products_website_discounted_price_positive"),
        "products",
        type_="check",
    )
