"""allow bank-independent chippin rates without product group

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_GROUP_SQL = "('klima', 'tv', 'other')"


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_commission_rates_product_group_valid"),
        "commission_rates",
        type_="check",
    )
    op.alter_column(
        "commission_rates",
        "product_group",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.create_check_constraint(
        op.f("ck_commission_rates_product_group_valid"),
        "commission_rates",
        f"product_group IS NULL OR product_group IN {PRODUCT_GROUP_SQL}",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE commission_rates SET product_group = 'other' "
        "WHERE product_group IS NULL"
    )
    op.drop_constraint(
        op.f("ck_commission_rates_product_group_valid"),
        "commission_rates",
        type_="check",
    )
    op.alter_column(
        "commission_rates",
        "product_group",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.create_check_constraint(
        op.f("ck_commission_rates_product_group_valid"),
        "commission_rates",
        f"product_group IN {PRODUCT_GROUP_SQL}",
    )
