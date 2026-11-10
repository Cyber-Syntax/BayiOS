from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from bayios.adapters.db.models.base import MONEY, Base, uuid_pk

PERCENT = sa.Numeric(5, 2)

CAMPAIGN_TYPE_SQL = (
    "('general', 'product_discount', 'bundle', 'gift', 'coupon', 'special')"
)
DISCOUNT_TYPE_SQL = "('percent', 'fixed_amount', 'special_price', 'gift', 'info_only')"
BASE_PRICE_TYPE_SQL = "('regular', 'website_discounted', 'manual')"
RELATION_TYPE_SQL = "('qualifying', 'benefit', 'gift', 'related')"


class Campaign(Base):
    """Stable campaign identity; business fields live in immutable versions."""

    __tablename__ = "campaigns"
    __table_args__ = (
        sa.Index("ix_campaigns_is_archived", "is_archived"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # Circular reference to campaign_versions; the FK is added by ALTER in migration.
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey(
            "campaign_versions.id",
            use_alter=True,
            name="fk_campaigns_current_version_id",
            ondelete="SET NULL",
        )
    )
    is_archived: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    created_by_name: Mapped[str | None] = mapped_column(sa.Text)
    created_by_device: Mapped[str | None] = mapped_column(sa.Text)


class CampaignVersion(Base):
    """One immutable snapshot of campaign fields and product relations."""

    __tablename__ = "campaign_versions"
    __table_args__ = (
        sa.UniqueConstraint(
            "campaign_id",
            "version_no",
            name="uq_campaign_versions_campaign_id_version_no",
        ),
        sa.CheckConstraint("version_no > 0", name="version_no_positive"),
        sa.CheckConstraint("char_length(trim(name)) > 0", name="name_not_empty"),
        sa.CheckConstraint("ends_at >= starts_at", name="date_range_valid"),
        sa.CheckConstraint(
            f"campaign_type IN {CAMPAIGN_TYPE_SQL}", name="campaign_type_valid"
        ),
        sa.CheckConstraint(
            f"base_price_type IN {BASE_PRICE_TYPE_SQL}", name="base_price_type_valid"
        ),
        sa.CheckConstraint(
            f"discount_type IN {DISCOUNT_TYPE_SQL}", name="discount_type_valid"
        ),
        sa.CheckConstraint(
            "(discount_type = 'percent' AND discount_value IS NOT NULL "
            "AND discount_value >= 0 AND discount_value <= 100) "
            "OR (discount_type IN ('fixed_amount', 'special_price') "
            "AND discount_value IS NOT NULL AND discount_value >= 0) "
            "OR (discount_type IN ('gift', 'info_only') AND discount_value IS NULL)",
            name="discount_value_valid",
        ),
        sa.CheckConstraint(
            f"gift_yes_base_price_type IS NULL "
            f"OR gift_yes_base_price_type IN {BASE_PRICE_TYPE_SQL}",
            name="gift_yes_base_price_type_valid",
        ),
        sa.CheckConstraint(
            f"gift_no_base_price_type IS NULL "
            f"OR gift_no_base_price_type IN {BASE_PRICE_TYPE_SQL}",
            name="gift_no_base_price_type_valid",
        ),
        sa.CheckConstraint(
            "(campaign_type <> 'gift' AND discount_type <> 'gift') "
            "OR (gift_description IS NOT NULL "
            "AND char_length(trim(gift_description)) > 0)",
            name="gift_description_required",
        ),
        sa.CheckConstraint(
            "NOT gift_optional OR (gift_description IS NOT NULL "
            "AND char_length(trim(gift_description)) > 0)",
            name="optional_gift_requires_description",
        ),
        sa.Index("ix_campaign_versions_campaign_id", "campaign_id"),
        sa.Index("ix_campaign_versions_dates", "starts_at", "ends_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    version_no: Mapped[int] = mapped_column(sa.Integer)
    name: Mapped[str] = mapped_column(sa.Text)
    description: Mapped[str | None] = mapped_column(sa.Text)
    campaign_type: Mapped[str] = mapped_column(sa.Text)
    starts_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    base_price_type: Mapped[str] = mapped_column(
        sa.Text, server_default=sa.text("'regular'")
    )
    discount_type: Mapped[str] = mapped_column(sa.Text)
    discount_value: Mapped[Decimal | None] = mapped_column(MONEY)
    gift_description: Mapped[str | None] = mapped_column(sa.Text)
    gift_optional: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false())
    gift_yes_base_price_type: Mapped[str | None] = mapped_column(sa.Text)
    gift_no_base_price_type: Mapped[str | None] = mapped_column(sa.Text)
    employee_note: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    created_by_name: Mapped[str | None] = mapped_column(sa.Text)
    created_by_device: Mapped[str | None] = mapped_column(sa.Text)


class CampaignVersionProduct(Base):
    """Product relation inside a version; the name snapshot survives deletion."""

    __tablename__ = "campaign_version_products"
    __table_args__ = (
        sa.UniqueConstraint(
            "campaign_version_id",
            "product_id",
            "relation_type",
            name="uq_campaign_version_products_product_relation",
        ),
        sa.UniqueConstraint(
            "campaign_version_id",
            "relation_type",
            "product_name_snapshot",
            name="uq_campaign_version_products_relation_name",
        ),
        sa.CheckConstraint(
            "char_length(trim(product_name_snapshot)) > 0",
            name="product_name_snapshot_not_empty",
        ),
        sa.CheckConstraint(
            f"relation_type IN {RELATION_TYPE_SQL}", name="relation_type_valid"
        ),
        sa.CheckConstraint(
            "quantity_required IS NULL OR quantity_required > 0",
            name="quantity_required_positive",
        ),
        sa.Index(
            "ix_campaign_version_products_campaign_version_id",
            "campaign_version_id",
        ),
        sa.Index("ix_campaign_version_products_product_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    campaign_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("campaign_versions.id", ondelete="CASCADE")
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("products.id", ondelete="SET NULL")
    )
    product_name_snapshot: Mapped[str] = mapped_column(sa.Text)
    relation_type: Mapped[str] = mapped_column(
        sa.Text, server_default=sa.text("'related'")
    )
    quantity_required: Mapped[int | None] = mapped_column(sa.Integer)


class DealerPricing(Base):
    """Current product-specific cash/card floor prices."""

    __tablename__ = "dealer_pricing"
    __table_args__ = (
        sa.UniqueConstraint("product_id", name="uq_dealer_pricing_product_id"),
        sa.CheckConstraint(
            "cash_floor_price IS NULL OR cash_floor_price >= 0",
            name="cash_floor_price_non_negative",
        ),
        sa.CheckConstraint(
            "card_floor_price IS NULL OR card_floor_price >= 0",
            name="card_floor_price_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    product_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="CASCADE")
    )
    cash_floor_price: Mapped[Decimal | None] = mapped_column(MONEY)
    card_floor_price: Mapped[Decimal | None] = mapped_column(MONEY)
    note: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    updated_by_name: Mapped[str | None] = mapped_column(sa.Text)
    updated_by_device: Mapped[str | None] = mapped_column(sa.Text)


class DealerPricingHistory(Base):
    """Append-only record of a dealer floor price change."""

    __tablename__ = "dealer_pricing_history"
    __table_args__ = (
        sa.CheckConstraint(
            "old_cash_floor IS NULL OR old_cash_floor >= 0",
            name="old_cash_floor_non_negative",
        ),
        sa.CheckConstraint(
            "new_cash_floor IS NULL OR new_cash_floor >= 0",
            name="new_cash_floor_non_negative",
        ),
        sa.CheckConstraint(
            "old_card_floor IS NULL OR old_card_floor >= 0",
            name="old_card_floor_non_negative",
        ),
        sa.CheckConstraint(
            "new_card_floor IS NULL OR new_card_floor >= 0",
            name="new_card_floor_non_negative",
        ),
        sa.Index(
            "ix_dealer_pricing_history_product_id_changed_at",
            "product_id",
            "changed_at",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    product_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="CASCADE")
    )
    old_cash_floor: Mapped[Decimal | None] = mapped_column(MONEY)
    new_cash_floor: Mapped[Decimal | None] = mapped_column(MONEY)
    old_card_floor: Mapped[Decimal | None] = mapped_column(MONEY)
    new_card_floor: Mapped[Decimal | None] = mapped_column(MONEY)
    note: Mapped[str | None] = mapped_column(sa.Text)
    changed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    changed_by_name: Mapped[str | None] = mapped_column(sa.Text)
    changed_by_device: Mapped[str | None] = mapped_column(sa.Text)


class DealerDiscountSetting(Base):
    """The single global default dealer discount setting."""

    __tablename__ = "dealer_discount_settings"
    __table_args__ = (
        sa.UniqueConstraint(
            "setting_key", name="uq_dealer_discount_settings_setting_key"
        ),
        sa.CheckConstraint(
            "default_percent >= 0 AND default_percent <= 100",
            name="default_percent_range",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    setting_key: Mapped[str] = mapped_column(
        sa.Text, server_default=sa.text("'default'")
    )
    default_percent: Mapped[Decimal] = mapped_column(
        PERCENT, server_default=sa.text("10.00")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    updated_by_name: Mapped[str | None] = mapped_column(sa.Text)
    updated_by_device: Mapped[str | None] = mapped_column(sa.Text)


class DealerDiscountSettingHistory(Base):
    """Append-only record of the global default dealer discount change."""

    __tablename__ = "dealer_discount_setting_history"
    __table_args__ = (
        sa.CheckConstraint(
            "old_percent >= 0 AND old_percent <= 100", name="old_percent_range"
        ),
        sa.CheckConstraint(
            "new_percent >= 0 AND new_percent <= 100", name="new_percent_range"
        ),
        sa.Index(
            "ix_dealer_discount_setting_history_setting_id_changed_at",
            "dealer_discount_setting_id",
            "changed_at",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    dealer_discount_setting_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("dealer_discount_settings.id", ondelete="CASCADE")
    )
    old_percent: Mapped[Decimal] = mapped_column(PERCENT)
    new_percent: Mapped[Decimal] = mapped_column(PERCENT)
    note: Mapped[str | None] = mapped_column(sa.Text)
    changed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    changed_by_name: Mapped[str | None] = mapped_column(sa.Text)
    changed_by_device: Mapped[str | None] = mapped_column(sa.Text)
