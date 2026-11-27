"""offer card and cash dealer discounts

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "offers",
        sa.Column(
            "dealer_discount_cash_percent",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("10.00"),
        ),
    )
    op.add_column(
        "offer_items",
        sa.Column(
            "dealer_discount_cash_percent",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("10.00"),
        ),
    )
    op.execute(
        "UPDATE offers SET dealer_discount_cash_percent = dealer_discount_percent"
    )
    op.execute(
        "UPDATE offer_items SET dealer_discount_cash_percent = dealer_discount_percent"
    )
    op.create_check_constraint(
        "dealer_discount_cash_range",
        "offers",
        "dealer_discount_cash_percent >= 0 "
        "AND dealer_discount_cash_percent <= 100",
    )
    op.create_check_constraint(
        "dealer_discount_cash_range",
        "offer_items",
        "dealer_discount_cash_percent >= 0 "
        "AND dealer_discount_cash_percent <= 100",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_offer_items_dealer_discount_cash_range"),
        "offer_items",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_offers_dealer_discount_cash_range"),
        "offers",
        type_="check",
    )
    op.drop_column("offer_items", "dealer_discount_cash_percent")
    op.drop_column("offers", "dealer_discount_cash_percent")
