"""klima odero tier optional and chippin bank-specific rows

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()

    op.drop_constraint(
        op.f("ck_commission_rates_odero_tier_consistency"),
        "commission_rates",
        type_="check",
    )
    klima_tier_rates = connection.execute(
        sa.text(
            "SELECT * FROM commission_rates "
            "WHERE channel = 'odero' AND product_group = 'klima' "
            "AND amount_tier IS NOT NULL"
        )
    ).mappings().all()
    for rate in klima_tier_rates:
        conflict = connection.execute(
            sa.text(
                "SELECT 1 FROM commission_rates "
                "WHERE period_id = :period_id AND channel = 'odero' "
                "AND bank_id IS NOT DISTINCT FROM :bank_id "
                "AND product_group = 'klima' AND amount_tier IS NULL "
                "AND installment_count = :installment_count "
                "AND id <> :id"
            ),
            {
                "period_id": rate["period_id"],
                "bank_id": rate["bank_id"],
                "installment_count": rate["installment_count"],
                "id": rate["id"],
            },
        ).first()
        if conflict is not None:
            connection.execute(
                sa.text("DELETE FROM commission_rates WHERE id = :id"),
                {"id": rate["id"]},
            )
            continue
        scope_key = "|".join(
            (
                "odero",
                str(rate["bank_id"]) if rate["bank_id"] else "-",
                "klima",
                "-",
                str(rate["installment_count"]),
            )
        )
        connection.execute(
            sa.text(
                "UPDATE commission_rates SET amount_tier = NULL, "
                "scope_key = :scope_key WHERE id = :id"
            ),
            {"scope_key": scope_key, "id": rate["id"]},
        )

    op.create_check_constraint(
        op.f("ck_commission_rates_odero_tier_consistency"),
        "commission_rates",
        "(channel = 'odero' AND product_group = 'klima' "
        "AND amount_tier IS NULL) "
        "OR (channel = 'odero' AND product_group = 'other' "
        "AND amount_tier IS NOT NULL) "
        "OR (channel <> 'odero' AND amount_tier IS NULL)",
    )

    op.drop_constraint(
        op.f("ck_commission_rates_channel_bank_consistency"),
        "commission_rates",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_commission_limits_chippin_bank_null"),
        "commission_limits",
        type_="check",
    )


def downgrade() -> None:
    connection = op.get_bind()

    connection.execute(
        sa.text(
            "DELETE FROM commission_limits "
            "WHERE channel = 'chippin' AND bank_id IS NOT NULL"
        )
    )
    op.create_check_constraint(
        op.f("ck_commission_limits_chippin_bank_null"),
        "commission_limits",
        "channel IS NULL OR channel <> 'chippin' OR bank_id IS NULL",
    )

    connection.execute(
        sa.text(
            "DELETE FROM commission_rates "
            "WHERE channel = 'chippin' AND bank_id IS NOT NULL"
        )
    )
    op.create_check_constraint(
        op.f("ck_commission_rates_channel_bank_consistency"),
        "commission_rates",
        "(channel = 'chippin' AND bank_id IS NULL) "
        "OR channel IN ('pos', 'odero')",
    )

    op.drop_constraint(
        op.f("ck_commission_rates_odero_tier_consistency"),
        "commission_rates",
        type_="check",
    )
    klima_rates = connection.execute(
        sa.text(
            "SELECT * FROM commission_rates "
            "WHERE channel = 'odero' AND product_group = 'klima' "
            "AND amount_tier IS NULL"
        )
    ).mappings().all()
    for rate in klima_rates:
        scope_key = "|".join(
            (
                "odero",
                str(rate["bank_id"]) if rate["bank_id"] else "-",
                "klima",
                "under_20000",
                str(rate["installment_count"]),
            )
        )
        connection.execute(
            sa.text(
                "UPDATE commission_rates SET amount_tier = 'under_20000', "
                "scope_key = :scope_key WHERE id = :id"
            ),
            {"scope_key": scope_key, "id": rate["id"]},
        )
    op.create_check_constraint(
        op.f("ck_commission_rates_odero_tier_consistency"),
        "commission_rates",
        "(channel = 'odero' AND amount_tier IS NOT NULL) "
        "OR (channel <> 'odero' AND amount_tier IS NULL)",
    )
