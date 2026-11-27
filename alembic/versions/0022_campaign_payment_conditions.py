"""campaign payment conditions

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "campaign_versions",
        sa.Column("payment_conditions", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("campaign_versions", "payment_conditions")
