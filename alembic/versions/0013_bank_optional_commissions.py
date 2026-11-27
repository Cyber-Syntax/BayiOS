"""bank-optional commissions, category caps and canonical names

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-18
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WHITESPACE = re.compile(r"\s+")
_TURKISH = str.maketrans({"I": "ı", "İ": "i"})


def _normalize(raw: str) -> str:
    normalized = unicodedata.normalize("NFKC", raw or "").strip()
    normalized = _WHITESPACE.sub(" ", normalized)
    return normalized.translate(_TURKISH).lower()


def _backfill_normalized(
    table: str, merge_refs: tuple[tuple[str, str], ...]
) -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(f"SELECT id, name FROM {table} ORDER BY created_at, id")
    ).mappings().all()
    seen: dict[str, uuid.UUID] = {}
    for row in rows:
        key = _normalize(str(row["name"]))
        if not key:
            key = str(row["id"])
        if key in seen:
            keep = seen[key]
            for ref_table, ref_column in merge_refs:
                connection.execute(
                    sa.text(
                        f"UPDATE {ref_table} SET {ref_column} = :keep "
                        f"WHERE {ref_column} = :dupe"
                    ),
                    {"keep": keep, "dupe": row["id"]},
                )
            connection.execute(
                sa.text(f"DELETE FROM {table} WHERE id = :id"),
                {"id": row["id"]},
            )
            continue
        seen[key] = row["id"]
        connection.execute(
            sa.text(f"UPDATE {table} SET name_normalized = :key WHERE id = :id"),
            {"key": key, "id": row["id"]},
        )


def upgrade() -> None:
    connection = op.get_bind()

    op.add_column("banks", sa.Column("name_normalized", sa.Text(), nullable=True))
    op.add_column(
        "product_categories",
        sa.Column("name_normalized", sa.Text(), nullable=True),
    )
    op.add_column(
        "commission_limits",
        sa.Column("category_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_commission_limits_category_id_product_categories"),
        "commission_limits",
        "product_categories",
        ["category_id"],
        ["id"],
        ondelete="CASCADE",
    )

    _backfill_normalized(
        "banks",
        (
            ("commission_rates", "bank_id"),
            ("commission_limits", "bank_id"),
            ("offers", "bank_id"),
        ),
    )
    _backfill_normalized(
        "product_categories",
        (
            ("products", "category_id"),
            ("commission_limits", "category_id"),
        ),
    )

    op.alter_column("banks", "name_normalized", nullable=False)
    op.alter_column("product_categories", "name_normalized", nullable=False)
    op.create_unique_constraint(
        op.f("uq_banks_name_normalized"), "banks", ["name_normalized"]
    )
    op.create_unique_constraint(
        op.f("uq_product_categories_name_normalized"),
        "product_categories",
        ["name_normalized"],
    )
    op.create_check_constraint(
        op.f("ck_product_categories_name_normalized_not_empty"),
        "product_categories",
        "char_length(name_normalized) > 0",
    )

    op.drop_constraint(
        op.f("ck_product_categories_commission_group_valid"),
        "product_categories",
        type_="check",
    )
    connection.execute(
        sa.text(
            "UPDATE product_categories SET commission_group = 'other' "
            "WHERE commission_group = 'tv'"
        )
    )
    op.create_check_constraint(
        op.f("ck_product_categories_commission_group_valid"),
        "product_categories",
        "commission_group IN ('klima', 'other')",
    )

    op.drop_constraint(
        op.f("ck_commission_rates_product_group_valid"),
        "commission_rates",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_commission_rates_channel_bank_consistency"),
        "commission_rates",
        type_="check",
    )
    tv_rates = connection.execute(
        sa.text("SELECT * FROM commission_rates WHERE product_group = 'tv'")
    ).mappings().all()
    for rate in tv_rates:
        conflict = connection.execute(
            sa.text(
                "SELECT 1 FROM commission_rates "
                "WHERE period_id = :period_id AND channel = :channel "
                "AND bank_id IS NOT DISTINCT FROM :bank_id "
                "AND product_group = 'other' "
                "AND amount_tier IS NOT DISTINCT FROM :amount_tier "
                "AND installment_count = :installment_count "
                "AND id <> :id"
            ),
            {
                "period_id": rate["period_id"],
                "channel": rate["channel"],
                "bank_id": rate["bank_id"],
                "amount_tier": rate["amount_tier"],
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
                rate["channel"],
                str(rate["bank_id"]) if rate["bank_id"] else "-",
                "other",
                rate["amount_tier"] or "-",
                str(rate["installment_count"]),
            )
        )
        connection.execute(
            sa.text(
                "UPDATE commission_rates SET product_group = 'other', "
                "scope_key = :scope_key WHERE id = :id"
            ),
            {"scope_key": scope_key, "id": rate["id"]},
        )
    op.create_check_constraint(
        op.f("ck_commission_rates_product_group_valid"),
        "commission_rates",
        "product_group IS NULL OR product_group IN ('klima', 'other')",
    )
    op.create_check_constraint(
        op.f("ck_commission_rates_channel_bank_consistency"),
        "commission_rates",
        "(channel = 'chippin' AND bank_id IS NULL) OR channel IN ('pos', 'odero')",
    )

    op.drop_constraint(
        op.f("ck_commission_limits_product_group_valid"),
        "commission_limits",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_commission_limits_scope_not_empty"),
        "commission_limits",
        type_="check",
    )
    tv_limits = connection.execute(
        sa.text("SELECT * FROM commission_limits WHERE product_group = 'tv'")
    ).mappings().all()
    tv_categories = connection.execute(
        sa.text(
            "SELECT id FROM product_categories "
            "WHERE name_normalized LIKE '%tv%' "
            "OR name_normalized LIKE '%televizyon%'"
        )
    ).scalars().all()
    for limit in tv_limits:
        for category_id in tv_categories:
            scope_key = "|".join(
                (
                    limit["channel"] or "-",
                    "-",
                    "-",
                    str(category_id),
                    limit["card_type"] or "-",
                )
            )
            exists = connection.execute(
                sa.text(
                    "SELECT 1 FROM commission_limits "
                    "WHERE period_id = :period_id AND scope_key = :scope_key"
                ),
                {"period_id": limit["period_id"], "scope_key": scope_key},
            ).first()
            if exists is not None:
                continue
            connection.execute(
                sa.text(
                    "INSERT INTO commission_limits "
                    "(id, period_id, channel, bank_id, product_group, category_id, "
                    "card_type, max_installments, scope_key) "
                    "VALUES (gen_random_uuid(), :period_id, :channel, NULL, NULL, "
                    ":category_id, :card_type, :max_installments, :scope_key)"
                ),
                {
                    "period_id": limit["period_id"],
                    "channel": limit["channel"],
                    "category_id": category_id,
                    "card_type": limit["card_type"],
                    "max_installments": limit["max_installments"],
                    "scope_key": scope_key,
                },
            )
        connection.execute(
            sa.text("DELETE FROM commission_limits WHERE id = :id"),
            {"id": limit["id"]},
        )
    op.create_check_constraint(
        op.f("ck_commission_limits_product_group_valid"),
        "commission_limits",
        "product_group IS NULL OR product_group IN ('klima', 'other')",
    )
    op.create_check_constraint(
        op.f("ck_commission_limits_category_limit_bank_null"),
        "commission_limits",
        "category_id IS NULL OR bank_id IS NULL",
    )
    op.create_check_constraint(
        op.f("ck_commission_limits_scope_not_empty"),
        "commission_limits",
        "channel IS NOT NULL OR bank_id IS NOT NULL "
        "OR product_group IS NOT NULL OR category_id IS NOT NULL "
        "OR card_type IS NOT NULL",
    )

    op.add_column(
        "offers", sa.Column("bank_name_snapshot", sa.Text(), nullable=True)
    )
    op.add_column("offers", sa.Column("commission_source", sa.Text(), nullable=True))
    connection.execute(
        sa.text(
            "UPDATE offers SET bank_name_snapshot = banks.name "
            "FROM banks WHERE offers.bank_id = banks.id"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE offers SET commission_source = CASE "
            "WHEN commission_percent_snapshot IS NULL THEN 'none' "
            "WHEN bank_id IS NULL THEN 'general' "
            "ELSE 'bank_specific' END"
        )
    )
    op.drop_constraint(
        op.f("ck_offers_bank_required_for_bank_channel"),
        "offers",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_offers_commission_source_valid"),
        "offers",
        "commission_source IS NULL "
        "OR commission_source IN ('bank_specific', 'general', 'none')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_offers_commission_source_valid"), "offers", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_offers_bank_required_for_bank_channel"),
        "offers",
        "channel IS NULL OR channel = 'chippin' OR bank_id IS NOT NULL",
    )
    op.drop_column("offers", "commission_source")
    op.drop_column("offers", "bank_name_snapshot")

    op.drop_constraint(
        op.f("ck_commission_limits_scope_not_empty"),
        "commission_limits",
        type_="check",
    )
    op.execute("DELETE FROM commission_limits WHERE category_id IS NOT NULL")
    op.drop_constraint(
        op.f("ck_commission_limits_category_limit_bank_null"),
        "commission_limits",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_commission_limits_product_group_valid"),
        "commission_limits",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_commission_limits_product_group_valid"),
        "commission_limits",
        "product_group IS NULL OR product_group IN ('klima', 'tv', 'other')",
    )
    op.create_check_constraint(
        op.f("ck_commission_limits_scope_not_empty"),
        "commission_limits",
        "channel IS NOT NULL OR bank_id IS NOT NULL "
        "OR product_group IS NOT NULL OR card_type IS NOT NULL",
    )
    op.drop_constraint(
        op.f("fk_commission_limits_category_id_product_categories"),
        "commission_limits",
        type_="foreignkey",
    )
    op.drop_column("commission_limits", "category_id")

    op.drop_constraint(
        op.f("ck_commission_rates_channel_bank_consistency"),
        "commission_rates",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_commission_rates_channel_bank_consistency"),
        "commission_rates",
        "(channel = 'chippin' AND bank_id IS NULL) "
        "OR (channel IN ('pos', 'odero') AND bank_id IS NOT NULL)",
    )
    op.drop_constraint(
        op.f("ck_commission_rates_product_group_valid"),
        "commission_rates",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_commission_rates_product_group_valid"),
        "commission_rates",
        "product_group IS NULL OR product_group IN ('klima', 'tv', 'other')",
    )

    op.drop_constraint(
        op.f("ck_product_categories_commission_group_valid"),
        "product_categories",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_product_categories_commission_group_valid"),
        "product_categories",
        "commission_group IN ('klima', 'tv', 'other')",
    )
    op.drop_constraint(
        op.f("ck_product_categories_name_normalized_not_empty"),
        "product_categories",
        type_="check",
    )
    op.drop_constraint(
        op.f("uq_product_categories_name_normalized"),
        "product_categories",
        type_="unique",
    )
    op.drop_column("product_categories", "name_normalized")
    op.drop_constraint(
        op.f("uq_banks_name_normalized"), "banks", type_="unique"
    )
    op.drop_column("banks", "name_normalized")
