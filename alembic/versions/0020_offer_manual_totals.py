"""offer manual cash/card total overrides

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "offers", sa.Column("cash_total_override", sa.Numeric(12, 2), nullable=True)
    )
    op.add_column(
        "offers", sa.Column("card_total_override", sa.Numeric(12, 2), nullable=True)
    )
    op.create_check_constraint(
        "cash_total_override_non_negative",
        "offers",
        "cash_total_override IS NULL OR cash_total_override >= 0",
    )
    op.create_check_constraint(
        "card_total_override_non_negative",
        "offers",
        "card_total_override IS NULL OR card_total_override >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_offers_card_total_override_non_negative", "offers", type_="check"
    )
    op.drop_constraint(
        "ck_offers_cash_total_override_non_negative", "offers", type_="check"
    )
    op.drop_column("offers", "card_total_override")
    op.drop_column("offers", "cash_total_override")
