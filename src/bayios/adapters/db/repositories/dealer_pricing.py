from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from bayios.adapters.db.models.campaigns import (
    DealerDiscountSetting,
    DealerDiscountSettingHistory,
    DealerPricing,
    DealerPricingHistory,
)

DEFAULT_SETTING_KEY = "default"


class SqlAlchemyDealerPricingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, product_id: uuid.UUID) -> DealerPricing | None:
        return self._session.scalar(
            sa.select(DealerPricing).where(DealerPricing.product_id == product_id)
        )

    def get_many(
        self, product_ids: Sequence[uuid.UUID]
    ) -> Mapping[uuid.UUID, DealerPricing]:
        if not product_ids:
            return {}
        rows = self._session.scalars(
            sa.select(DealerPricing).where(DealerPricing.product_id.in_(product_ids))
        ).all()
        return {row.product_id: row for row in rows}

    def get_for_update(self, product_id: uuid.UUID) -> DealerPricing | None:
        return self._session.scalar(
            sa.select(DealerPricing)
            .where(DealerPricing.product_id == product_id)
            .with_for_update()
        )

    def add(self, pricing: DealerPricing) -> None:
        self._session.add(pricing)
        self._session.flush()

    def add_history(self, history: DealerPricingHistory) -> None:
        self._session.add(history)

    def get_history(
        self, product_id: uuid.UUID, limit: int = 50
    ) -> Sequence[DealerPricingHistory]:
        return self._session.scalars(
            sa.select(DealerPricingHistory)
            .where(DealerPricingHistory.product_id == product_id)
            .order_by(DealerPricingHistory.changed_at.desc())
            .limit(limit)
        ).all()

    def get_setting(self) -> DealerDiscountSetting | None:
        return self._session.scalar(
            sa.select(DealerDiscountSetting).where(
                DealerDiscountSetting.setting_key == DEFAULT_SETTING_KEY
            )
        )

    def get_setting_for_update(self) -> DealerDiscountSetting | None:
        return self._session.scalar(
            sa.select(DealerDiscountSetting)
            .where(DealerDiscountSetting.setting_key == DEFAULT_SETTING_KEY)
            .with_for_update()
        )

    def add_setting(self, setting: DealerDiscountSetting) -> None:
        self._session.add(setting)
        self._session.flush()

    def add_setting_history(
        self, history: DealerDiscountSettingHistory
    ) -> None:
        self._session.add(history)

    def get_setting_history(
        self, setting_id: uuid.UUID, limit: int = 50
    ) -> Sequence[DealerDiscountSettingHistory]:
        return self._session.scalars(
            sa.select(DealerDiscountSettingHistory)
            .where(DealerDiscountSettingHistory.dealer_discount_setting_id == setting_id)
            .order_by(DealerDiscountSettingHistory.changed_at.desc())
            .limit(limit)
        ).all()
