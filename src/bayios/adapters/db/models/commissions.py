from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from bayios.adapters.db.models.base import MONEY, Base, uuid_pk

PERCENT = sa.Numeric(5, 2)

CHANNEL_SQL = "('pos', 'odero', 'chippin')"
PRODUCT_GROUP_SQL = "('klima', 'tv', 'other')"
CARD_TYPE_SQL = "('consumer', 'business')"
STATUS_SQL = "('draft', 'active', 'inactive', 'archived')"
ODERO_TIER_SQL = "('under_20000', 'over_20000')"


class Bank(Base):
    __tablename__ = "banks"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(sa.Text, unique=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.true())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class CommissionPeriod(Base):
    __tablename__ = "commission_periods"
    __table_args__ = (
        sa.UniqueConstraint("period_key"),
        sa.CheckConstraint(f"status IN {STATUS_SQL}", name="status_valid"),
        sa.CheckConstraint("valid_until >= valid_from", name="date_range_valid"),
        sa.CheckConstraint(
            "char_length(period_key) = 7 AND substr(period_key, 5, 1) = '-'",
            name="period_key_format",
        ),
        sa.Index("ix_commission_periods_status", "status"),
        sa.Index("ix_commission_periods_dates", "valid_from", "valid_until"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    period_key: Mapped[str] = mapped_column(sa.Text)
    valid_from: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    status: Mapped[str] = mapped_column(sa.Text, server_default=sa.text("'draft'"))
    copied_from_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("commission_periods.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    created_by_name: Mapped[str | None] = mapped_column(sa.Text)
    created_by_device: Mapped[str | None] = mapped_column(sa.Text)


class CommissionRate(Base):
    __tablename__ = "commission_rates"
    __table_args__ = (
        sa.UniqueConstraint("period_id", "scope_key"),
        sa.CheckConstraint(f"channel IN {CHANNEL_SQL}", name="channel_valid"),
        sa.CheckConstraint(
            f"product_group IS NULL OR product_group IN {PRODUCT_GROUP_SQL}",
            name="product_group_valid",
        ),
        sa.CheckConstraint(
            f"amount_tier IS NULL OR amount_tier IN {ODERO_TIER_SQL}",
            name="amount_tier_valid",
        ),
        sa.CheckConstraint(
            "installment_count > 0", name="installment_count_positive"
        ),
        sa.CheckConstraint(
            "commission_percent >= 0 AND commission_percent <= 100",
            name="commission_percent_range",
        ),
        sa.CheckConstraint(
            "(channel = 'chippin' AND bank_id IS NULL) "
            "OR (channel IN ('pos', 'odero') AND bank_id IS NOT NULL)",
            name="channel_bank_consistency",
        ),
        sa.CheckConstraint(
            "(channel = 'odero' AND amount_tier IS NOT NULL) "
            "OR (channel <> 'odero' AND amount_tier IS NULL)",
            name="odero_tier_consistency",
        ),
        sa.Index("ix_commission_rates_period_id", "period_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    period_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("commission_periods.id", ondelete="CASCADE")
    )
    channel: Mapped[str] = mapped_column(sa.Text)
    bank_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("banks.id", ondelete="SET NULL")
    )
    product_group: Mapped[str | None] = mapped_column(sa.Text)
    amount_tier: Mapped[str | None] = mapped_column(sa.Text)
    installment_count: Mapped[int] = mapped_column(sa.Integer)
    commission_percent: Mapped[Decimal] = mapped_column(PERCENT)
    scope_key: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class CommissionLimit(Base):
    __tablename__ = "commission_limits"
    __table_args__ = (
        sa.UniqueConstraint("period_id", "scope_key"),
        sa.CheckConstraint(
            f"channel IS NULL OR channel IN {CHANNEL_SQL}", name="channel_valid"
        ),
        sa.CheckConstraint(
            f"product_group IS NULL OR product_group IN {PRODUCT_GROUP_SQL}",
            name="product_group_valid",
        ),
        sa.CheckConstraint(
            f"card_type IS NULL OR card_type IN {CARD_TYPE_SQL}",
            name="card_type_valid",
        ),
        sa.CheckConstraint(
            "max_installments > 0", name="max_installments_positive"
        ),
        sa.CheckConstraint(
            "channel IS NOT NULL OR bank_id IS NOT NULL "
            "OR product_group IS NOT NULL OR card_type IS NOT NULL",
            name="scope_not_empty",
        ),
        sa.CheckConstraint(
            "channel IS NULL OR channel <> 'chippin' OR bank_id IS NULL",
            name="chippin_bank_null",
        ),
        sa.Index("ix_commission_limits_period_id", "period_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    period_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("commission_periods.id", ondelete="CASCADE")
    )
    channel: Mapped[str | None] = mapped_column(sa.Text)
    bank_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("banks.id", ondelete="SET NULL")
    )
    product_group: Mapped[str | None] = mapped_column(sa.Text)
    card_type: Mapped[str | None] = mapped_column(sa.Text)
    max_installments: Mapped[int] = mapped_column(sa.Integer)
    scope_key: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    created_by_name: Mapped[str | None] = mapped_column(sa.Text)


class ProfitTarget(Base):
    __tablename__ = "profit_targets"
    __table_args__ = (
        sa.CheckConstraint(
            "scope_type IN ('global', 'product')", name="scope_type_valid"
        ),
        sa.CheckConstraint(
            "target_type IN ('percent', 'fixed_amount')", name="target_type_valid"
        ),
        sa.CheckConstraint("target_value >= 0", name="target_value_non_negative"),
        sa.CheckConstraint(
            "(scope_type = 'global' AND scope_id IS NULL) "
            "OR (scope_type = 'product' AND scope_id IS NOT NULL)",
            name="scope_consistency",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name="date_range_valid",
        ),
        sa.Index("ix_profit_targets_scope", "scope_type", "scope_id", "valid_from"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    scope_type: Mapped[str] = mapped_column(sa.Text)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid)
    target_type: Mapped[str] = mapped_column(sa.Text)
    target_value: Mapped[Decimal] = mapped_column(MONEY)
    valid_from: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    created_by_name: Mapped[str | None] = mapped_column(sa.Text)
    created_by_device: Mapped[str | None] = mapped_column(sa.Text)
