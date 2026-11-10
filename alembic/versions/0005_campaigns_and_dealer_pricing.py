"""campaigns, campaign versions and dealer pricing

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(12, 2)
PERCENT = sa.Numeric(5, 2)

CAMPAIGN_TYPE_SQL = (
    "('general', 'product_discount', 'bundle', 'gift', 'coupon', 'special')"
)
DISCOUNT_TYPE_SQL = "('percent', 'fixed_amount', 'special_price', 'gift', 'info_only')"
BASE_PRICE_TYPE_SQL = "('regular', 'website_discounted', 'manual')"
RELATION_TYPE_SQL = "('qualifying', 'benefit', 'gift', 'related')"


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
    op.create_table(
        "campaigns",
        _uuid_pk(),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "is_archived", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        _ts("created_at"),
        _ts("updated_at"),
        sa.Column("created_by_name", sa.Text(), nullable=True),
        sa.Column("created_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campaigns")),
    )
    op.create_index(op.f("ix_campaigns_is_archived"), "campaigns", ["is_archived"])

    op.create_table(
        "campaign_versions",
        _uuid_pk(),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("campaign_type", sa.Text(), nullable=False),
        _ts("starts_at", default_now=False),
        _ts("ends_at", default_now=False),
        sa.Column(
            "base_price_type",
            sa.Text(),
            server_default=sa.text("'regular'"),
            nullable=False,
        ),
        sa.Column("discount_type", sa.Text(), nullable=False),
        sa.Column("discount_value", MONEY, nullable=True),
        sa.Column("gift_description", sa.Text(), nullable=True),
        sa.Column(
            "gift_optional", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("gift_yes_base_price_type", sa.Text(), nullable=True),
        sa.Column("gift_no_base_price_type", sa.Text(), nullable=True),
        sa.Column("employee_note", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.Column("created_by_name", sa.Text(), nullable=True),
        sa.Column("created_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campaign_versions")),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            name=op.f("fk_campaign_versions_campaign_id_campaigns"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "campaign_id",
            "version_no",
            name=op.f("uq_campaign_versions_campaign_id_version_no"),
        ),
        sa.CheckConstraint(
            "version_no > 0", name=op.f("ck_campaign_versions_version_no_positive")
        ),
        sa.CheckConstraint(
            "char_length(trim(name)) > 0",
            name=op.f("ck_campaign_versions_name_not_empty"),
        ),
        sa.CheckConstraint(
            "ends_at >= starts_at", name=op.f("ck_campaign_versions_date_range_valid")
        ),
        sa.CheckConstraint(
            f"campaign_type IN {CAMPAIGN_TYPE_SQL}",
            name=op.f("ck_campaign_versions_campaign_type_valid"),
        ),
        sa.CheckConstraint(
            f"base_price_type IN {BASE_PRICE_TYPE_SQL}",
            name=op.f("ck_campaign_versions_base_price_type_valid"),
        ),
        sa.CheckConstraint(
            f"discount_type IN {DISCOUNT_TYPE_SQL}",
            name=op.f("ck_campaign_versions_discount_type_valid"),
        ),
        sa.CheckConstraint(
            "(discount_type = 'percent' AND discount_value IS NOT NULL "
            "AND discount_value >= 0 AND discount_value <= 100) "
            "OR (discount_type IN ('fixed_amount', 'special_price') "
            "AND discount_value IS NOT NULL AND discount_value >= 0) "
            "OR (discount_type IN ('gift', 'info_only') AND discount_value IS NULL)",
            name=op.f("ck_campaign_versions_discount_value_valid"),
        ),
        sa.CheckConstraint(
            f"gift_yes_base_price_type IS NULL "
            f"OR gift_yes_base_price_type IN {BASE_PRICE_TYPE_SQL}",
            name=op.f("ck_campaign_versions_gift_yes_base_price_type_valid"),
        ),
        sa.CheckConstraint(
            f"gift_no_base_price_type IS NULL "
            f"OR gift_no_base_price_type IN {BASE_PRICE_TYPE_SQL}",
            name=op.f("ck_campaign_versions_gift_no_base_price_type_valid"),
        ),
        sa.CheckConstraint(
            "(campaign_type <> 'gift' AND discount_type <> 'gift') "
            "OR (gift_description IS NOT NULL "
            "AND char_length(trim(gift_description)) > 0)",
            name=op.f("ck_campaign_versions_gift_description_required"),
        ),
        sa.CheckConstraint(
            "NOT gift_optional OR (gift_description IS NOT NULL "
            "AND char_length(trim(gift_description)) > 0)",
            name=op.f("ck_campaign_versions_optional_gift_requires_description"),
        ),
    )
    op.create_index(
        op.f("ix_campaign_versions_campaign_id"), "campaign_versions", ["campaign_id"]
    )
    op.create_index(
        op.f("ix_campaign_versions_dates"), "campaign_versions", ["starts_at", "ends_at"]
    )

    op.create_table(
        "campaign_version_products",
        _uuid_pk(),
        sa.Column("campaign_version_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("product_name_snapshot", sa.Text(), nullable=False),
        sa.Column(
            "relation_type",
            sa.Text(),
            server_default=sa.text("'related'"),
            nullable=False,
        ),
        sa.Column("quantity_required", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campaign_version_products")),
        sa.ForeignKeyConstraint(
            ["campaign_version_id"],
            ["campaign_versions.id"],
            name=op.f(
                "fk_campaign_version_products_campaign_version_id_campaign_versions"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_campaign_version_products_product_id_products"),
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "campaign_version_id",
            "product_id",
            "relation_type",
            name=op.f("uq_campaign_version_products_product_relation"),
        ),
        sa.UniqueConstraint(
            "campaign_version_id",
            "relation_type",
            "product_name_snapshot",
            name=op.f("uq_campaign_version_products_relation_name"),
        ),
        sa.CheckConstraint(
            "char_length(trim(product_name_snapshot)) > 0",
            name=op.f("ck_campaign_version_products_product_name_snapshot_not_empty"),
        ),
        sa.CheckConstraint(
            f"relation_type IN {RELATION_TYPE_SQL}",
            name=op.f("ck_campaign_version_products_relation_type_valid"),
        ),
        sa.CheckConstraint(
            "quantity_required IS NULL OR quantity_required > 0",
            name=op.f("ck_campaign_version_products_quantity_required_positive"),
        ),
    )
    op.create_index(
        op.f("ix_campaign_version_products_campaign_version_id"),
        "campaign_version_products",
        ["campaign_version_id"],
    )
    op.create_index(
        op.f("ix_campaign_version_products_product_id"),
        "campaign_version_products",
        ["product_id"],
    )

    op.create_table(
        "dealer_pricing",
        _uuid_pk(),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("cash_floor_price", MONEY, nullable=True),
        sa.Column("card_floor_price", MONEY, nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.Column("updated_by_name", sa.Text(), nullable=True),
        sa.Column("updated_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dealer_pricing")),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_dealer_pricing_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "product_id", name=op.f("uq_dealer_pricing_product_id")
        ),
        sa.CheckConstraint(
            "cash_floor_price IS NULL OR cash_floor_price >= 0",
            name=op.f("ck_dealer_pricing_cash_floor_price_non_negative"),
        ),
        sa.CheckConstraint(
            "card_floor_price IS NULL OR card_floor_price >= 0",
            name=op.f("ck_dealer_pricing_card_floor_price_non_negative"),
        ),
    )

    op.create_table(
        "dealer_pricing_history",
        _uuid_pk(),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("old_cash_floor", MONEY, nullable=True),
        sa.Column("new_cash_floor", MONEY, nullable=True),
        sa.Column("old_card_floor", MONEY, nullable=True),
        sa.Column("new_card_floor", MONEY, nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("changed_at"),
        sa.Column("changed_by_name", sa.Text(), nullable=True),
        sa.Column("changed_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dealer_pricing_history")),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_dealer_pricing_history_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "old_cash_floor IS NULL OR old_cash_floor >= 0",
            name=op.f("ck_dealer_pricing_history_old_cash_floor_non_negative"),
        ),
        sa.CheckConstraint(
            "new_cash_floor IS NULL OR new_cash_floor >= 0",
            name=op.f("ck_dealer_pricing_history_new_cash_floor_non_negative"),
        ),
        sa.CheckConstraint(
            "old_card_floor IS NULL OR old_card_floor >= 0",
            name=op.f("ck_dealer_pricing_history_old_card_floor_non_negative"),
        ),
        sa.CheckConstraint(
            "new_card_floor IS NULL OR new_card_floor >= 0",
            name=op.f("ck_dealer_pricing_history_new_card_floor_non_negative"),
        ),
    )
    op.create_index(
        op.f("ix_dealer_pricing_history_product_id_changed_at"),
        "dealer_pricing_history",
        ["product_id", "changed_at"],
    )

    op.create_table(
        "dealer_discount_settings",
        _uuid_pk(),
        sa.Column(
            "setting_key",
            sa.Text(),
            server_default=sa.text("'default'"),
            nullable=False,
        ),
        sa.Column(
            "default_percent", PERCENT, server_default=sa.text("10.00"), nullable=False
        ),
        _ts("updated_at"),
        sa.Column("updated_by_name", sa.Text(), nullable=True),
        sa.Column("updated_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dealer_discount_settings")),
        sa.UniqueConstraint(
            "setting_key", name=op.f("uq_dealer_discount_settings_setting_key")
        ),
        sa.CheckConstraint(
            "default_percent >= 0 AND default_percent <= 100",
            name=op.f("ck_dealer_discount_settings_default_percent_range"),
        ),
    )

    op.create_table(
        "dealer_discount_setting_history",
        _uuid_pk(),
        sa.Column("dealer_discount_setting_id", sa.Uuid(), nullable=False),
        sa.Column("old_percent", PERCENT, nullable=False),
        sa.Column("new_percent", PERCENT, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("changed_at"),
        sa.Column("changed_by_name", sa.Text(), nullable=True),
        sa.Column("changed_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_dealer_discount_setting_history")
        ),
        sa.ForeignKeyConstraint(
            ["dealer_discount_setting_id"],
            ["dealer_discount_settings.id"],
            name=op.f(
                "fk_dealer_discount_setting_history_dealer_discount_setting_id_dealer_discount_settings"
            ),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "old_percent >= 0 AND old_percent <= 100",
            name=op.f("ck_dealer_discount_setting_history_old_percent_range"),
        ),
        sa.CheckConstraint(
            "new_percent >= 0 AND new_percent <= 100",
            name=op.f("ck_dealer_discount_setting_history_new_percent_range"),
        ),
    )
    op.create_index(
        op.f("ix_dealer_discount_setting_history_setting_id_changed_at"),
        "dealer_discount_setting_history",
        ["dealer_discount_setting_id", "changed_at"],
    )

    # Circular FK is added after both tables exist.
    op.create_foreign_key(
        "fk_campaigns_current_version_id",
        "campaigns",
        "campaign_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_campaigns_current_version_id", "campaigns", type_="foreignkey"
    )
    op.drop_index(
        op.f("ix_dealer_discount_setting_history_setting_id_changed_at"),
        table_name="dealer_discount_setting_history",
    )
    op.drop_table("dealer_discount_setting_history")
    op.drop_table("dealer_discount_settings")
    op.drop_index(
        op.f("ix_dealer_pricing_history_product_id_changed_at"),
        table_name="dealer_pricing_history",
    )
    op.drop_table("dealer_pricing_history")
    op.drop_table("dealer_pricing")
    op.drop_index(
        op.f("ix_campaign_version_products_product_id"),
        table_name="campaign_version_products",
    )
    op.drop_index(
        op.f("ix_campaign_version_products_campaign_version_id"),
        table_name="campaign_version_products",
    )
    op.drop_table("campaign_version_products")
    op.drop_index(
        op.f("ix_campaign_versions_dates"), table_name="campaign_versions"
    )
    op.drop_index(
        op.f("ix_campaign_versions_campaign_id"), table_name="campaign_versions"
    )
    op.drop_table("campaign_versions")
    op.drop_index(op.f("ix_campaigns_is_archived"), table_name="campaigns")
    op.drop_table("campaigns")
