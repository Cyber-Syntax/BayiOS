from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from bayios.adapters.db.models.campaigns import (
    Campaign,
    CampaignVersion,
    CampaignVersionProduct,
)


@dataclass(frozen=True)
class ActiveCampaignLink:
    """An active campaign version related to a product."""

    campaign: Campaign
    version: CampaignVersion
    link: CampaignVersionProduct


class CampaignRepository(Protocol):
    """Campaign aggregate persistence port.

    Campaign fields and product relations live in immutable versions; the
    campaign row only carries identity, archive state and the current pointer.
    """

    def add(self, campaign: Campaign) -> None: ...

    def add_version(self, version: CampaignVersion) -> None: ...

    def add_version_products(
        self, products: Sequence[CampaignVersionProduct]
    ) -> None: ...

    def get(self, campaign_id: uuid.UUID) -> Campaign | None: ...

    def get_for_update(self, campaign_id: uuid.UUID) -> Campaign | None: ...

    def get_version(self, version_id: uuid.UUID) -> CampaignVersion | None: ...

    def get_current_version(
        self, campaign_id: uuid.UUID
    ) -> CampaignVersion | None: ...

    def get_versions(self, campaign_id: uuid.UUID) -> Sequence[CampaignVersion]: ...

    def get_version_products(
        self, version_id: uuid.UUID
    ) -> Sequence[CampaignVersionProduct]: ...

    def get_version_products_for_versions(
        self, version_ids: Sequence[uuid.UUID]
    ) -> Mapping[uuid.UUID, Sequence[CampaignVersionProduct]]: ...

    def set_current_version(
        self, campaign_id: uuid.UUID, version_id: uuid.UUID
    ) -> None: ...

    def set_archived(self, campaign_id: uuid.UUID, archived: bool) -> None: ...

    def list(
        self,
        *,
        query: str | None = None,
        campaign_type: str | None = None,
        state: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        as_of: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[tuple[Campaign, CampaignVersion]], int]: ...

    def active_for_product(
        self, product_id: uuid.UUID, *, as_of: datetime
    ) -> Sequence[ActiveCampaignLink]: ...
