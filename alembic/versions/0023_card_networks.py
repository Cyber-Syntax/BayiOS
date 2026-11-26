"""bank card networks and offer card network

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "banks", sa.Column("card_networks", JSONB, nullable=True)
    )
    op.add_column(
        "offers", sa.Column("card_network", sa.Text, nullable=True)
    )


def downgrade() -> None:
    op.drop_column("offers", "card_network")
    op.drop_column("banks", "card_networks")
