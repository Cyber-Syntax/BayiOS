from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol

from bayios.adapters.db.models.inventory import StockMovement
from bayios.adapters.db.models.products import Product
from bayios.adapters.db.models.reservations import (
    Reservation,
    ReservationItem,
    ReservationItemEvent,
    ReservationReminder,
)


class ReservationRepository(Protocol):
    """Reservation aggregate persistence port."""

    def add(self, reservation: Reservation) -> None: ...

    def add_item(self, item: ReservationItem) -> None: ...

    def add_items(self, items: Sequence[ReservationItem]) -> None: ...

    def get(self, reservation_id: uuid.UUID) -> Reservation | None: ...

    def get_items(self, reservation_id: uuid.UUID) -> Sequence[ReservationItem]: ...

    def get_items_for_reservations(
        self, reservation_ids: Sequence[uuid.UUID]
    ) -> Mapping[uuid.UUID, Sequence[ReservationItem]]: ...

    def get_item(self, item_id: uuid.UUID) -> ReservationItem | None: ...

    def lock_item(self, item_id: uuid.UUID) -> ReservationItem | None: ...

    def lock_product(self, product_id: uuid.UUID) -> Product | None: ...

    def delete_item(self, item: ReservationItem) -> None: ...

    def list(
        self,
        *,
        status: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
        now: datetime | None = None,
    ) -> tuple[Sequence[Reservation], int]: ...

    def list_reminders(
        self, *, due_before: datetime, limit: int = 50
    ) -> Sequence[Reservation]: ...

    def add_event(self, event: ReservationItemEvent) -> None: ...

    def get_events(self, reservation_id: uuid.UUID) -> Sequence[ReservationItemEvent]: ...

    def add_reminder(self, reminder: ReservationReminder) -> None: ...

    def get_reminders(
        self, reservation_id: uuid.UUID
    ) -> Sequence[ReservationReminder]: ...

    def open_quantity_by_product(
        self, product_ids: Sequence[uuid.UUID]
    ) -> Mapping[uuid.UUID, int]: ...

    def open_product_ids(
        self, product_ids: Sequence[uuid.UUID]
    ) -> set[uuid.UUID]: ...

    def find_stock_movement(self, idempotency_key: str) -> StockMovement | None: ...
