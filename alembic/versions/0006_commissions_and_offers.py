"""commission periods, commission matrix and offers

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-11
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(12, 2)
PERCENT = sa.Numeric(5, 2)

CHANNEL_SQL = "('pos', 'odero', 'chippin')"
PRODUCT_GROUP_SQL = "('klima', 'tv', 'other')"
CARD_TYPE_SQL = "('consumer', 'business')"
PERIOD_STATUS_SQL = "('draft', 'active', 'archived')"
ODERO_TIER_SQL = "('under_20000', 'over_20000')"
OFFER_STATUS_SQL = "('draft', 'presented', 'accepted', 'lost', 'expired')"
PAYMENT_TYPE_SQL = "('cash', 'card')"


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
    )


def _ts(name: str, *, nullable: bool = False, default_now: bool = True) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.func.now() if default_now else None,
        nullable=nullable,
    )


def upgrade() -> None:
    op.add_column(
        "product_categories",
        sa.Column(
            "commission_group",
            sa.Text(),
            server_default=sa.text("'other'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_product_categories_commission_group_valid"),
        "product_categories",
        "commission_group IN ('klima', 'tv', 'other')",
    )
    op.execute(
        "UPDATE product_categories SET commission_group = 'klima' "
        "WHERE lower(name) LIKE '%klima%'"
    )
    op.execute(
        "UPDATE product_categories SET commission_group = 'tv' "
        "WHERE lower(name) LIKE '%tv%' OR lower(name) LIKE '%televizyon%'"
    )

    op.create_table(
        "banks",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_banks")),
        sa.UniqueConstraint("name", name=op.f("uq_banks_name")),
    )

    op.create_table(
        "commission_periods",
        _uuid_pk(),
        sa.Column("period_key", sa.Text(), nullable=False),
        _ts("valid_from", default_now=False),
        _ts("valid_until", default_now=False),
        sa.Column(
            "status", sa.Text(), server_default=sa.text("'draft'"), nullable=False
        ),
        sa.Column("copied_from_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.Column("created_by_name", sa.Text(), nullable=True),
        sa.Column("created_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_commission_periods")),
        sa.ForeignKeyConstraint(
            ["copied_from_id"],
            ["commission_periods.id"],
            name=op.f("fk_commission_periods_copied_from_id_commission_periods"),
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("period_key", name=op.f("uq_commission_periods_period_key")),
        sa.CheckConstraint(
            f"status IN {PERIOD_STATUS_SQL}",
            name=op.f("ck_commission_periods_status_valid"),
        ),
        sa.CheckConstraint(
            "valid_until >= valid_from",
            name=op.f("ck_commission_periods_date_range_valid"),
        ),
        sa.CheckConstraint(
            "char_length(period_key) = 7 AND substr(period_key, 5, 1) = '-'",
            name=op.f("ck_commission_periods_period_key_format"),
        ),
    )
    op.create_index(
        op.f("ix_commission_periods_status"), "commission_periods", ["status"]
    )
    op.create_index(
        op.f("ix_commission_periods_dates"),
        "commission_periods",
        ["valid_from", "valid_until"],
    )

    op.create_table(
        "commission_rates",
        _uuid_pk(),
        sa.Column("period_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("bank_id", sa.Uuid(), nullable=True),
        sa.Column("product_group", sa.Text(), nullable=False),
        sa.Column("amount_tier", sa.Text(), nullable=True),
        sa.Column("installment_count", sa.Integer(), nullable=False),
        sa.Column("commission_percent", PERCENT, nullable=False),
        sa.Column("scope_key", sa.Text(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_commission_rates")),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["commission_periods.id"],
            name=op.f("fk_commission_rates_period_id_commission_periods"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["bank_id"],
            ["banks.id"],
            name=op.f("fk_commission_rates_bank_id_banks"),
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "period_id",
            "scope_key",
            name=op.f("uq_commission_rates_period_id_scope_key"),
        ),
        sa.CheckConstraint(
            f"channel IN {CHANNEL_SQL}", name=op.f("ck_commission_rates_channel_valid")
        ),
        sa.CheckConstraint(
            f"product_group IN {PRODUCT_GROUP_SQL}",
            name=op.f("ck_commission_rates_product_group_valid"),
        ),
        sa.CheckConstraint(
            f"amount_tier IS NULL OR amount_tier IN {ODERO_TIER_SQL}",
            name=op.f("ck_commission_rates_amount_tier_valid"),
        ),
        sa.CheckConstraint(
            "installment_count > 0",
            name=op.f("ck_commission_rates_installment_count_positive"),
        ),
        sa.CheckConstraint(
            "commission_percent >= 0 AND commission_percent <= 100",
            name=op.f("ck_commission_rates_commission_percent_range"),
        ),
        sa.CheckConstraint(
            "(channel = 'chippin' AND bank_id IS NULL) "
            "OR (channel IN ('pos', 'odero') AND bank_id IS NOT NULL)",
            name=op.f("ck_commission_rates_channel_bank_consistency"),
        ),
        sa.CheckConstraint(
            "(channel = 'odero' AND amount_tier IS NOT NULL) "
            "OR (channel <> 'odero' AND amount_tier IS NULL)",
            name=op.f("ck_commission_rates_odero_tier_consistency"),
        ),
    )
    op.create_index(
        op.f("ix_commission_rates_period_id"), "commission_rates", ["period_id"]
    )

    op.create_table(
        "commission_limits",
        _uuid_pk(),
        sa.Column("period_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("bank_id", sa.Uuid(), nullable=True),
        sa.Column("product_group", sa.Text(), nullable=True),
        sa.Column("card_type", sa.Text(), nullable=True),
        sa.Column("max_installments", sa.Integer(), nullable=False),
        sa.Column("scope_key", sa.Text(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.Column("created_by_name", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_commission_limits")),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["commission_periods.id"],
            name=op.f("fk_commission_limits_period_id_commission_periods"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["bank_id"],
            ["banks.id"],
            name=op.f("fk_commission_limits_bank_id_banks"),
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "period_id",
            "scope_key",
            name=op.f("uq_commission_limits_period_id_scope_key"),
        ),
        sa.CheckConstraint(
            f"channel IS NULL OR channel IN {CHANNEL_SQL}",
            name=op.f("ck_commission_limits_channel_valid"),
        ),
        sa.CheckConstraint(
            f"product_group IS NULL OR product_group IN {PRODUCT_GROUP_SQL}",
            name=op.f("ck_commission_limits_product_group_valid"),
        ),
        sa.CheckConstraint(
            f"card_type IS NULL OR card_type IN {CARD_TYPE_SQL}",
            name=op.f("ck_commission_limits_card_type_valid"),
        ),
        sa.CheckConstraint(
            "max_installments > 0",
            name=op.f("ck_commission_limits_max_installments_positive"),
        ),
        sa.CheckConstraint(
            "channel IS NOT NULL OR bank_id IS NOT NULL "
            "OR product_group IS NOT NULL OR card_type IS NOT NULL",
            name=op.f("ck_commission_limits_scope_not_empty"),
        ),
        sa.CheckConstraint(
            "channel IS NULL OR channel <> 'chippin' OR bank_id IS NULL",
            name=op.f("ck_commission_limits_chippin_bank_null"),
        ),
    )
    op.create_index(
        op.f("ix_commission_limits_period_id"), "commission_limits", ["period_id"]
    )

    op.create_table(
        "profit_targets",
        _uuid_pk(),
        sa.Column("scope_type", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=True),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_value", MONEY, nullable=False),
        _ts("valid_from", default_now=False),
        _ts("valid_until", nullable=True, default_now=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.Column("created_by_name", sa.Text(), nullable=True),
        sa.Column("created_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profit_targets")),
        sa.CheckConstraint(
            "scope_type IN ('global', 'product')",
            name=op.f("ck_profit_targets_scope_type_valid"),
        ),
        sa.CheckConstraint(
            "target_type IN ('percent', 'fixed_amount')",
            name=op.f("ck_profit_targets_target_type_valid"),
        ),
        sa.CheckConstraint(
            "target_value >= 0",
            name=op.f("ck_profit_targets_target_value_non_negative"),
        ),
        sa.CheckConstraint(
            "(scope_type = 'global' AND scope_id IS NULL) "
            "OR (scope_type = 'product' AND scope_id IS NOT NULL)",
            name=op.f("ck_profit_targets_scope_consistency"),
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name=op.f("ck_profit_targets_date_range_valid"),
        ),
    )
    op.create_index(
        op.f("ix_profit_targets_scope"),
        "profit_targets",
        ["scope_type", "scope_id", "valid_from"],
    )

    op.create_table(
        "offers",
        _uuid_pk(),
        sa.Column(
            "offer_number",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("customer_name", sa.Text(), nullable=True),
        sa.Column("customer_phone", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.Text(), server_default=sa.text("'draft'"), nullable=False
        ),
        sa.Column(
            "payment_type",
            sa.Text(),
            server_default=sa.text("'cash'"),
            nullable=False,
        ),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("bank_id", sa.Uuid(), nullable=True),
        sa.Column("installment_count", sa.Integer(), nullable=True),
        sa.Column("card_type", sa.Text(), nullable=True),
        sa.Column(
            "dealer_discount_percent",
            PERCENT,
            server_default=sa.text("10.00"),
            nullable=False,
        ),
        sa.Column("commission_period_id", sa.Uuid(), nullable=True),
        sa.Column("commission_period_key_snapshot", sa.Text(), nullable=True),
        sa.Column("commission_percent_snapshot", PERCENT, nullable=True),
        sa.Column("cash_total", MONEY, server_default=sa.text("0"), nullable=False),
        sa.Column("card_total", MONEY, server_default=sa.text("0"), nullable=False),
        sa.Column(
            "selected_total", MONEY, server_default=sa.text("0"), nullable=False
        ),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("follow_up_at", nullable=True, default_now=False),
        sa.Column("converted_reservation_id", sa.Uuid(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.Column("created_by_name", sa.Text(), nullable=True),
        sa.Column("created_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offers")),
        sa.ForeignKeyConstraint(
            ["bank_id"],
            ["banks.id"],
            name=op.f("fk_offers_bank_id_banks"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["commission_period_id"],
            ["commission_periods.id"],
            name=op.f("fk_offers_commission_period_id_commission_periods"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["converted_reservation_id"],
            ["reservations.id"],
            name=op.f("fk_offers_converted_reservation_id_reservations"),
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("offer_number", name=op.f("uq_offers_offer_number")),
        sa.UniqueConstraint(
            "converted_reservation_id",
            name=op.f("uq_offers_converted_reservation_id"),
        ),
        sa.CheckConstraint(
            f"status IN {OFFER_STATUS_SQL}", name=op.f("ck_offers_status_valid")
        ),
        sa.CheckConstraint(
            f"payment_type IN {PAYMENT_TYPE_SQL}",
            name=op.f("ck_offers_payment_type_valid"),
        ),
        sa.CheckConstraint(
            f"channel IS NULL OR channel IN {CHANNEL_SQL}",
            name=op.f("ck_offers_channel_valid"),
        ),
        sa.CheckConstraint(
            f"card_type IS NULL OR card_type IN {CARD_TYPE_SQL}",
            name=op.f("ck_offers_card_type_valid"),
        ),
        sa.CheckConstraint(
            "installment_count IS NULL OR installment_count > 0",
            name=op.f("ck_offers_installment_count_positive"),
        ),
        sa.CheckConstraint(
            "dealer_discount_percent >= 0 AND dealer_discount_percent <= 100",
            name=op.f("ck_offers_dealer_discount_range"),
        ),
        sa.CheckConstraint(
            "commission_percent_snapshot IS NULL OR "
            "(commission_percent_snapshot >= 0 AND commission_percent_snapshot <= 100)",
            name=op.f("ck_offers_commission_percent_range"),
        ),
        sa.CheckConstraint(
            "cash_total >= 0 AND card_total >= 0 AND selected_total >= 0",
            name=op.f("ck_offers_totals_non_negative"),
        ),
        sa.CheckConstraint(
            "(payment_type = 'cash') OR "
            "(channel IS NOT NULL AND installment_count IS NOT NULL)",
            name=op.f("ck_offers_card_payment_requires_channel"),
        ),
        sa.CheckConstraint(
            "channel IS NULL OR channel = 'chippin' OR bank_id IS NOT NULL",
            name=op.f("ck_offers_bank_required_for_bank_channel"),
        ),
    )
    op.create_index(op.f("ix_offers_status"), "offers", ["status"])
    op.create_index(op.f("ix_offers_created_at"), "offers", ["created_at"])

    op.create_table(
        "offer_items",
        _uuid_pk(),
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("product_name_snapshot", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("regular_price_snapshot", MONEY, nullable=True),
        sa.Column("website_price_snapshot", MONEY, nullable=True),
        sa.Column("cost_price_snapshot", MONEY, nullable=True),
        sa.Column("campaign_version_id", sa.Uuid(), nullable=True),
        sa.Column("campaign_name_snapshot", sa.Text(), nullable=True),
        sa.Column("campaign_snapshot", JSONB(), nullable=True),
        sa.Column("campaign_gift_present", sa.Boolean(), nullable=True),
        sa.Column("base_price_used", MONEY, nullable=True),
        sa.Column("dealer_discount_percent", PERCENT, nullable=False),
        sa.Column("suggested_cash_price", MONEY, nullable=True),
        sa.Column("suggested_card_price", MONEY, nullable=True),
        sa.Column("unit_price_cash", MONEY, nullable=True),
        sa.Column("unit_price_card", MONEY, nullable=True),
        sa.Column("line_total_cash", MONEY, nullable=True),
        sa.Column("line_total_card", MONEY, nullable=True),
        sa.Column("warning_text", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offer_items")),
        sa.ForeignKeyConstraint(
            ["offer_id"],
            ["offers.id"],
            name=op.f("fk_offer_items_offer_id_offers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_offer_items_product_id_products"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_version_id"],
            ["campaign_versions.id"],
            name=op.f("fk_offer_items_campaign_version_id_campaign_versions"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "quantity > 0", name=op.f("ck_offer_items_quantity_positive")
        ),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_offer_items_position_non_negative")
        ),
        sa.CheckConstraint(
            "dealer_discount_percent >= 0 AND dealer_discount_percent <= 100",
            name=op.f("ck_offer_items_dealer_discount_range"),
        ),
        sa.CheckConstraint(
            "regular_price_snapshot IS NULL OR regular_price_snapshot >= 0",
            name=op.f("ck_offer_items_regular_price_non_negative"),
        ),
        sa.CheckConstraint(
            "website_price_snapshot IS NULL OR website_price_snapshot >= 0",
            name=op.f("ck_offer_items_website_price_non_negative"),
        ),
        sa.CheckConstraint(
            "cost_price_snapshot IS NULL OR cost_price_snapshot >= 0",
            name=op.f("ck_offer_items_cost_price_non_negative"),
        ),
        sa.CheckConstraint(
            "unit_price_cash IS NULL OR unit_price_cash >= 0",
            name=op.f("ck_offer_items_unit_price_cash_non_negative"),
        ),
        sa.CheckConstraint(
            "unit_price_card IS NULL OR unit_price_card >= 0",
            name=op.f("ck_offer_items_unit_price_card_non_negative"),
        ),
    )
    op.create_index(
        op.f("ix_offer_items_offer_id"), "offer_items", ["offer_id"]
    )
    op.create_index(
        op.f("ix_offer_items_product_id"), "offer_items", ["product_id"]
    )

    op.create_table(
        "offer_history",
        _uuid_pk(),
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("old_status", sa.Text(), nullable=True),
        sa.Column("new_status", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("changed_at"),
        sa.Column("changed_by_name", sa.Text(), nullable=True),
        sa.Column("changed_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offer_history")),
        sa.ForeignKeyConstraint(
            ["offer_id"],
            ["offers.id"],
            name=op.f("fk_offer_history_offer_id_offers"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"old_status IS NULL OR old_status IN {OFFER_STATUS_SQL}",
            name=op.f("ck_offer_history_old_status_valid"),
        ),
        sa.CheckConstraint(
            f"new_status IN {OFFER_STATUS_SQL}",
            name=op.f("ck_offer_history_new_status_valid"),
        ),
    )
    op.create_index(op.f("ix_offer_history_offer_id"), "offer_history", ["offer_id"])

    _seed_banks_and_limits()


def _seed_banks_and_limits() -> None:
    banks = (
        "Yapı Kredi",
        "Axess",
        "Garanti BBVA",
        "İş Bankası",
        "Akbank",
        "QNB",
        "Ziraat",
        "Halkbank",
        "Vakıfbank",
    )
    for name in banks:
        op.execute(
            sa.text("INSERT INTO banks (name) VALUES (:name)").bindparams(name=name)
        )

    now = datetime.now(UTC)
    start = datetime(now.year, now.month, 1, tzinfo=UTC)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=UTC)
    period_id = uuid.uuid4()
    op.execute(
        sa.text(
            "INSERT INTO commission_periods "
            "(id, period_key, valid_from, valid_until, status) "
            "VALUES (:id, :key, :start, :end, 'draft')"
        ).bindparams(
            id=period_id,
            key=f"{now.year:04d}-{now.month:02d}",
            start=start,
            end=end,
        )
    )
    bank_id = op.get_bind().execute(
        sa.text("SELECT id FROM banks WHERE name = 'Yapı Kredi'")
    ).scalar_one()

    limits = (
        ("pos", None, 8, "channel"),
        ("odero", None, 5, "channel"),
        ("chippin", None, 6, "channel"),
        ("pos", bank_id, 8, "bank"),
        ("odero", bank_id, 2, "bank"),
        ("klima", None, 10, "group"),
        ("tv", None, 4, "group"),
        ("other", None, 5, "group"),
        ("business", None, 2, "card"),
    )
    for value, scoped_bank, max_installments, scope in limits:
        channel = value if scope in ("channel", "bank") else None
        product_group = value if scope == "group" else None
        card_type = value if scope == "card" else None
        scope_key = f"{channel or '-'}|{scoped_bank or '-'}|{product_group or '-'}|{card_type or '-'}"
        op.execute(
            sa.text(
                "INSERT INTO commission_limits "
                "(id, period_id, channel, bank_id, product_group, card_type, max_installments, scope_key) "
                "VALUES (:id, :period_id, :channel, :bank_id, :product_group, :card_type, :max_installments, :scope_key)"
            ).bindparams(
                id=uuid.uuid4(),
                period_id=period_id,
                channel=channel,
                bank_id=scoped_bank,
                product_group=product_group,
                card_type=card_type,
                max_installments=max_installments,
                scope_key=scope_key,
            )
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_offer_history_offer_id"), table_name="offer_history")
    op.drop_table("offer_history")
    op.drop_index(op.f("ix_offer_items_product_id"), table_name="offer_items")
    op.drop_index(op.f("ix_offer_items_offer_id"), table_name="offer_items")
    op.drop_table("offer_items")
    op.drop_index(op.f("ix_offers_created_at"), table_name="offers")
    op.drop_index(op.f("ix_offers_status"), table_name="offers")
    op.drop_table("offers")
    op.drop_index(op.f("ix_profit_targets_scope"), table_name="profit_targets")
    op.drop_table("profit_targets")
    op.drop_index(
        op.f("ix_commission_limits_period_id"), table_name="commission_limits"
    )
    op.drop_table("commission_limits")
    op.drop_index(
        op.f("ix_commission_rates_period_id"), table_name="commission_rates"
    )
    op.drop_table("commission_rates")
    op.drop_index(
        op.f("ix_commission_periods_dates"), table_name="commission_periods"
    )
    op.drop_index(
        op.f("ix_commission_periods_status"), table_name="commission_periods"
    )
    op.drop_table("commission_periods")
    op.drop_table("banks")
    op.drop_constraint(
        op.f("ck_product_categories_commission_group_valid"),
        "product_categories",
        type_="check",
    )
    op.drop_column("product_categories", "commission_group")
