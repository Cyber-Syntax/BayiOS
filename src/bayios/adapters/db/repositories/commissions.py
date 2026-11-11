from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from bayios.adapters.db.models.commissions import (
    Bank,
    CommissionLimit,
    CommissionPeriod,
    CommissionRate,
    ProfitTarget,
)
from bayios.adapters.db.models.products import ProductCategory


class SqlAlchemyCommissionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_period(self, period: CommissionPeriod) -> None:
        self._session.add(period)
        self._session.flush()

    def get_period(self, period_id: uuid.UUID) -> CommissionPeriod | None:
        return self._session.get(CommissionPeriod, period_id)

    def get_period_by_key(self, period_key: str) -> CommissionPeriod | None:
        return self._session.scalar(
            sa.select(CommissionPeriod).where(
                CommissionPeriod.period_key == period_key
            )
        )

    def get_active_period(self, as_of: datetime) -> CommissionPeriod | None:
        return self._session.scalar(
            sa.select(CommissionPeriod)
            .where(
                CommissionPeriod.status == "active",
                CommissionPeriod.valid_from <= as_of,
                CommissionPeriod.valid_until >= as_of,
            )
            .order_by(CommissionPeriod.valid_from.desc())
        )

    def list_periods(self, limit: int = 24) -> Sequence[CommissionPeriod]:
        return self._session.scalars(
            sa.select(CommissionPeriod)
            .order_by(CommissionPeriod.valid_from.desc())
            .limit(limit)
        ).all()

    def set_period_status(self, period_id: uuid.UUID, status: str) -> None:
        self._session.execute(
            sa.update(CommissionPeriod)
            .where(CommissionPeriod.id == period_id)
            .values(status=status, updated_at=sa.func.now())
        )
        self._session.flush()

    def delete_period(self, period_id: uuid.UUID) -> None:
        self._session.execute(
            sa.delete(CommissionPeriod).where(CommissionPeriod.id == period_id)
        )
        self._session.flush()

    def get_rates(self, period_id: uuid.UUID) -> Sequence[CommissionRate]:
        return self._session.scalars(
            sa.select(CommissionRate)
            .where(CommissionRate.period_id == period_id)
            .order_by(
                CommissionRate.channel,
                CommissionRate.product_group,
                CommissionRate.installment_count,
            )
        ).all()

    def get_rate(self, rate_id: uuid.UUID) -> CommissionRate | None:
        return self._session.get(CommissionRate, rate_id)

    def add_rate(self, rate: CommissionRate) -> None:
        self._session.add(rate)

    def update_rate(self, rate_id: uuid.UUID, commission_percent: Decimal) -> None:
        self._session.execute(
            sa.update(CommissionRate)
            .where(CommissionRate.id == rate_id)
            .values(commission_percent=commission_percent)
        )
        self._session.flush()

    def delete_rate(self, rate_id: uuid.UUID) -> None:
        self._session.execute(
            sa.delete(CommissionRate).where(CommissionRate.id == rate_id)
        )
        self._session.flush()

    def delete_rates(self, period_id: uuid.UUID) -> None:
        self._session.execute(
            sa.delete(CommissionRate).where(
                CommissionRate.period_id == period_id
            )
        )
        self._session.flush()

    def get_limits(self, period_id: uuid.UUID) -> Sequence[CommissionLimit]:
        return self._session.scalars(
            sa.select(CommissionLimit).where(
                CommissionLimit.period_id == period_id
            )
        ).all()

    def get_limit(self, limit_id: uuid.UUID) -> CommissionLimit | None:
        return self._session.get(CommissionLimit, limit_id)

    def add_limit(self, limit: CommissionLimit) -> None:
        self._session.add(limit)

    def update_limit(self, limit_id: uuid.UUID, max_installments: int) -> None:
        self._session.execute(
            sa.update(CommissionLimit)
            .where(CommissionLimit.id == limit_id)
            .values(max_installments=max_installments)
        )
        self._session.flush()

    def delete_limit(self, limit_id: uuid.UUID) -> None:
        self._session.execute(
            sa.delete(CommissionLimit).where(CommissionLimit.id == limit_id)
        )
        self._session.flush()

    def delete_limits(self, period_id: uuid.UUID) -> None:
        self._session.execute(
            sa.delete(CommissionLimit).where(
                CommissionLimit.period_id == period_id
            )
        )
        self._session.flush()

    def get_banks(self, active_only: bool = True) -> Sequence[Bank]:
        stmt = sa.select(Bank).order_by(Bank.name)
        if active_only:
            stmt = stmt.where(Bank.is_active.is_(True))
        return self._session.scalars(stmt).all()

    def add_bank(self, bank: Bank) -> None:
        self._session.add(bank)
        self._session.flush()

    def get_profit_target(
        self,
        *,
        scope_type: str,
        scope_id: uuid.UUID | None,
        as_of: datetime,
    ) -> ProfitTarget | None:
        return self._session.scalar(
            sa.select(ProfitTarget)
            .where(
                ProfitTarget.scope_type == scope_type,
                ProfitTarget.scope_id == scope_id,
                ProfitTarget.valid_from <= as_of,
                sa.or_(
                    ProfitTarget.valid_until.is_(None),
                    ProfitTarget.valid_until >= as_of,
                ),
            )
            .order_by(ProfitTarget.valid_from.desc())
        )

    def add_profit_target(self, target: ProfitTarget) -> None:
        self._session.add(target)

    def set_category_group(
        self, category_id: uuid.UUID, commission_group: str
    ) -> None:
        self._session.execute(
            sa.update(ProductCategory)
            .where(ProductCategory.id == category_id)
            .values(commission_group=commission_group)
        )
        self._session.flush()
