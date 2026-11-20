"""offer pricing v2 snapshots and totals

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "offers",
        sa.Column(
            "pricing_version",
            sa.Text,
            nullable=False,
            server_default=sa.text("'legacy'"),
        ),
    )
    for column in (
        "regular_total",
        "oliz_total",
        "company_discount_total",
        "cost_total",
    ):
        op.add_column(
            "offers",
            sa.Column(
                column,
                sa.Numeric(12, 2),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    op.create_check_constraint(
        "pricing_version_valid",
        "offers",
        "pricing_version IN ('legacy', 'v2')",
    )

    op.add_column(
        "offer_items",
        sa.Column("company_discount_source", sa.Text, nullable=True),
    )
    for column in (
        "company_discount_amount",
        "company_share_amount",
        "campaign_discount_amount",
        "campaign_base_price",
        "campaign_price",
    ):
        op.add_column(
            "offer_items",
            sa.Column(column, sa.Numeric(12, 2), nullable=True),
        )
    op.create_check_constraint(
        "company_discount_source_valid",
        "offer_items",
        "company_discount_source IS NULL "
        "OR company_discount_source IN ('campaign', 'oliz', 'none')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_offer_items_company_discount_source_valid"),
        "offer_items",
        type_="check",
    )
    for column in (
        "campaign_price",
        "campaign_base_price",
        "campaign_discount_amount",
        "company_share_amount",
        "company_discount_amount",
        "company_discount_source",
    ):
        op.drop_column("offer_items", column)
    op.drop_constraint(
        op.f("ck_offers_pricing_version_valid"),
        "offers",
        type_="check",
    )
    for column in (
        "cost_total",
        "company_discount_total",
        "oliz_total",
        "regular_total",
        "pricing_version",
    ):
        op.drop_column("offers", column)
