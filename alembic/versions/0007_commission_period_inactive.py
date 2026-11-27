"""allow inactive commission periods

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_commission_periods_status_valid"),
        "commission_periods",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_commission_periods_status_valid"),
        "commission_periods",
        "status IN ('draft', 'active', 'inactive', 'archived')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_commission_periods_status_valid"),
        "commission_periods",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_commission_periods_status_valid"),
        "commission_periods",
        "status IN ('draft', 'active', 'archived')",
    )
