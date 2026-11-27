"""offer commission options and dealer share snapshots

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERCENT = sa.Numeric(5, 2)


def upgrade() -> None:
    op.add_column(
        "offers",
        sa.Column("commission_options_snapshot", JSONB(), nullable=True),
    )
    op.add_column(
        "offers",
        sa.Column(
            "dealer_share_percent_snapshot",
            PERCENT,
            server_default=sa.text("85.00"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_offers_dealer_share_percent_range"),
        "offers",
        "dealer_share_percent_snapshot >= 0 AND dealer_share_percent_snapshot <= 100",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_offers_dealer_share_percent_range"), "offers", type_="check"
    )
    op.drop_column("offers", "dealer_share_percent_snapshot")
    op.drop_column("offers", "commission_options_snapshot")
