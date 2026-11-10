from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Protocol

from bayios.adapters.db.models.campaigns import (
    DealerDiscountSetting,
    DealerDiscountSettingHistory,
    DealerPricing,
    DealerPricingHistory,
)


class DealerPricingRepository(Protocol):
    """Product dealer floor price and global default discount persistence port."""

    def get(self, product_id: uuid.UUID) -> DealerPricing | None: ...

    def get_many(
        self, product_ids: Sequence[uuid.UUID]
    ) -> Mapping[uuid.UUID, DealerPricing]: ...

    def get_for_update(self, product_id: uuid.UUID) -> DealerPricing | None: ...

    def add(self, pricing: DealerPricing) -> None: ...

    def add_history(self, history: DealerPricingHistory) -> None: ...

    def get_history(
        self, product_id: uuid.UUID, limit: int = 50
    ) -> Sequence[DealerPricingHistory]: ...

    def get_setting(self) -> DealerDiscountSetting | None: ...

    def get_setting_for_update(self) -> DealerDiscountSetting | None: ...

    def add_setting(self, setting: DealerDiscountSetting) -> None: ...

    def add_setting_history(self, history: DealerDiscountSettingHistory) -> None: ...

    def get_setting_history(
        self, setting_id: uuid.UUID, limit: int = 50
    ) -> Sequence[DealerDiscountSettingHistory]: ...
