from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol

from bayios.adapters.db.models.offers import Offer, OfferHistory, OfferItem


class OfferRepository(Protocol):
    def add(self, offer: Offer) -> None: ...

    def add_items(self, items: Sequence[OfferItem]) -> None: ...

    def get(self, offer_id: uuid.UUID) -> Offer | None: ...

    def get_for_update(self, offer_id: uuid.UUID) -> Offer | None: ...

    def get_items(self, offer_id: uuid.UUID) -> Sequence[OfferItem]: ...

    def delete_items(self, offer_id: uuid.UUID) -> None: ...

    def save(self, offer: Offer) -> None: ...

    def list(
        self,
        *,
        status: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Offer], int]: ...

    def add_history(self, history: OfferHistory) -> None: ...

    def get_history(self, offer_id: uuid.UUID) -> Sequence[OfferHistory]: ...

    def find_by_converted_reservation(
        self, reservation_id: uuid.UUID
    ) -> Offer | None: ...
