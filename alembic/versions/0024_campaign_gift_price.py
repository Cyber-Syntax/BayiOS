"""campaign gift price

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "campaign_version_products",
        sa.Column("gift_price", sa.Numeric(12, 2), nullable=True),
    )
    op.create_check_constraint(
        "gift_price_non_negative",
        "campaign_version_products",
        "gift_price IS NULL OR gift_price >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_campaign_version_products_gift_price_non_negative",
        "campaign_version_products",
        type_="check",
    )
    op.drop_column("campaign_version_products", "gift_price")
