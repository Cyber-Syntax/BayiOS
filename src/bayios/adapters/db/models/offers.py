from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bayios.adapters.db.models.base import MONEY, Base, uuid_pk
from bayios.adapters.db.models.commissions import PERCENT

OFFER_STATUS_SQL = "('draft', 'presented', 'accepted', 'lost', 'expired')"
PAYMENT_TYPE_SQL = "('cash', 'card')"
CHANNEL_SQL = "('pos', 'odero', 'chippin')"
CARD_TYPE_SQL = "('consumer', 'business')"


class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (
        sa.UniqueConstraint("offer_number"),
        sa.UniqueConstraint("converted_reservation_id"),
        sa.CheckConstraint(f"status IN {OFFER_STATUS_SQL}", name="status_valid"),
        sa.CheckConstraint(
            f"payment_type IN {PAYMENT_TYPE_SQL}", name="payment_type_valid"
        ),
        sa.CheckConstraint(
            f"channel IS NULL OR channel IN {CHANNEL_SQL}", name="channel_valid"
        ),
        sa.CheckConstraint(
            f"card_type IS NULL OR card_type IN {CARD_TYPE_SQL}",
            name="card_type_valid",
        ),
        sa.CheckConstraint(
            "installment_count IS NULL OR installment_count > 0",
            name="installment_count_positive",
        ),
        sa.CheckConstraint(
            "dealer_discount_percent >= 0 AND dealer_discount_percent <= 100",
            name="dealer_discount_range",
        ),
        sa.CheckConstraint(
            "commission_percent_snapshot IS NULL "
            "OR (commission_percent_snapshot >= 0 AND commission_percent_snapshot <= 100)",
            name="commission_percent_range",
        ),
        sa.CheckConstraint(
            "dealer_share_percent_snapshot >= 0 "
            "AND dealer_share_percent_snapshot <= 100",
            name="dealer_share_percent_range",
        ),
        sa.CheckConstraint(
            "cash_total >= 0 AND card_total >= 0 AND selected_total >= 0",
            name="totals_non_negative",
        ),
        sa.CheckConstraint(
            "(payment_type = 'cash') OR "
            "(channel IS NOT NULL AND installment_count IS NOT NULL)",
            name="card_payment_requires_channel",
        ),
        sa.CheckConstraint(
            "channel IS NULL OR channel = 'chippin' OR bank_id IS NOT NULL",
            name="bank_required_for_bank_channel",
        ),
        sa.Index("ix_offers_status", "status"),
        sa.Index("ix_offers_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    offer_number: Mapped[int] = mapped_column(
        sa.BigInteger, sa.Identity(always=True)
    )
    customer_name: Mapped[str | None] = mapped_column(sa.Text)
    customer_phone: Mapped[str | None] = mapped_column(sa.Text)
    status: Mapped[str] = mapped_column(
        sa.Text, server_default=sa.text("'draft'")
    )
    payment_type: Mapped[str] = mapped_column(
        sa.Text, server_default=sa.text("'cash'")
    )
    channel: Mapped[str | None] = mapped_column(sa.Text)
    bank_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("banks.id", ondelete="SET NULL")
    )
    installment_count: Mapped[int | None] = mapped_column(sa.Integer)
    card_type: Mapped[str | None] = mapped_column(sa.Text)
    dealer_discount_percent: Mapped[Decimal] = mapped_column(
        PERCENT, server_default=sa.text("10.00")
    )
    commission_period_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("commission_periods.id", ondelete="SET NULL")
    )
    commission_period_key_snapshot: Mapped[str | None] = mapped_column(sa.Text)
    commission_percent_snapshot: Mapped[Decimal | None] = mapped_column(PERCENT)
    commission_options_snapshot: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB
    )
    dealer_share_percent_snapshot: Mapped[Decimal] = mapped_column(
        PERCENT, server_default=sa.text("85.00")
    )
    cash_total: Mapped[Decimal] = mapped_column(
        MONEY, server_default=sa.text("0")
    )
    card_total: Mapped[Decimal] = mapped_column(
        MONEY, server_default=sa.text("0")
    )
    selected_total: Mapped[Decimal] = mapped_column(
        MONEY, server_default=sa.text("0")
    )
    note: Mapped[str | None] = mapped_column(sa.Text)
    follow_up_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    converted_reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("reservations.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    created_by_name: Mapped[str | None] = mapped_column(sa.Text)
    created_by_device: Mapped[str | None] = mapped_column(sa.Text)


class OfferItem(Base):
    __tablename__ = "offer_items"
    __table_args__ = (
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint("position >= 0", name="position_non_negative"),
        sa.CheckConstraint(
            "dealer_discount_percent >= 0 AND dealer_discount_percent <= 100",
            name="dealer_discount_range",
        ),
        sa.CheckConstraint(
            "regular_price_snapshot IS NULL OR regular_price_snapshot >= 0",
            name="regular_price_non_negative",
        ),
        sa.CheckConstraint(
            "website_price_snapshot IS NULL OR website_price_snapshot >= 0",
            name="website_price_non_negative",
        ),
        sa.CheckConstraint(
            "cost_price_snapshot IS NULL OR cost_price_snapshot >= 0",
            name="cost_price_non_negative",
        ),
        sa.CheckConstraint(
            "unit_price_cash IS NULL OR unit_price_cash >= 0",
            name="unit_price_cash_non_negative",
        ),
        sa.CheckConstraint(
            "unit_price_card IS NULL OR unit_price_card >= 0",
            name="unit_price_card_non_negative",
        ),
        sa.Index("ix_offer_items_offer_id", "offer_id"),
        sa.Index("ix_offer_items_product_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    offer_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("offers.id", ondelete="CASCADE")
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("products.id", ondelete="SET NULL")
    )
    product_name_snapshot: Mapped[str] = mapped_column(sa.Text)
    quantity: Mapped[int] = mapped_column(sa.Integer)
    regular_price_snapshot: Mapped[Decimal | None] = mapped_column(MONEY)
    website_price_snapshot: Mapped[Decimal | None] = mapped_column(MONEY)
    cost_price_snapshot: Mapped[Decimal | None] = mapped_column(MONEY)
    campaign_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("campaign_versions.id", ondelete="SET NULL")
    )
    campaign_name_snapshot: Mapped[str | None] = mapped_column(sa.Text)
    campaign_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    campaign_gift_present: Mapped[bool | None] = mapped_column(sa.Boolean)
    base_price_used: Mapped[Decimal | None] = mapped_column(MONEY)
    dealer_discount_percent: Mapped[Decimal] = mapped_column(PERCENT)
    suggested_cash_price: Mapped[Decimal | None] = mapped_column(MONEY)
    suggested_card_price: Mapped[Decimal | None] = mapped_column(MONEY)
    unit_price_cash: Mapped[Decimal | None] = mapped_column(MONEY)
    unit_price_card: Mapped[Decimal | None] = mapped_column(MONEY)
    line_total_cash: Mapped[Decimal | None] = mapped_column(MONEY)
    line_total_card: Mapped[Decimal | None] = mapped_column(MONEY)
    warning_text: Mapped[str | None] = mapped_column(sa.Text)
    position: Mapped[int] = mapped_column(sa.Integer, server_default=sa.text("0"))


class OfferHistory(Base):
    __tablename__ = "offer_history"
    __table_args__ = (
        sa.CheckConstraint(
            f"old_status IS NULL OR old_status IN {OFFER_STATUS_SQL}",
            name="old_status_valid",
        ),
        sa.CheckConstraint(
            f"new_status IN {OFFER_STATUS_SQL}", name="new_status_valid"
        ),
        sa.Index("ix_offer_history_offer_id", "offer_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    offer_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("offers.id", ondelete="CASCADE")
    )
    old_status: Mapped[str | None] = mapped_column(sa.Text)
    new_status: Mapped[str] = mapped_column(sa.Text)
    note: Mapped[str | None] = mapped_column(sa.Text)
    changed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    changed_by_name: Mapped[str | None] = mapped_column(sa.Text)
    changed_by_device: Mapped[str | None] = mapped_column(sa.Text)
