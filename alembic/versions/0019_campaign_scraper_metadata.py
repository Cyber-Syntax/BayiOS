"""campaign scraper metadata and JSON import

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "campaigns", sa.Column("external_id", sa.Text, nullable=True)
    )
    op.add_column(
        "campaigns", sa.Column("source_url", sa.Text, nullable=True)
    )
    op.create_index(
        "uq_campaigns_external_id",
        "campaigns",
        ["external_id"],
        unique=True,
    )

    op.add_column(
        "campaign_versions", sa.Column("conditions", JSONB, nullable=True)
    )
    op.add_column(
        "campaign_versions",
        sa.Column("source_category", sa.Text, nullable=True),
    )
    op.add_column(
        "campaign_versions",
        sa.Column("source_product_count", sa.Integer, nullable=True),
    )
    op.add_column(
        "campaign_versions",
        sa.Column(
            "scraped_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("campaign_versions", "scraped_at")
    op.drop_column("campaign_versions", "source_product_count")
    op.drop_column("campaign_versions", "source_category")
    op.drop_column("campaign_versions", "conditions")
    op.drop_index("uq_campaigns_external_id", table_name="campaigns")
    op.drop_column("campaigns", "source_url")
    op.drop_column("campaigns", "external_id")
