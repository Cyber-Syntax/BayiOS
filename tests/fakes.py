from __future__ import annotations

import uuid
from collections.abc import Sequence
from types import TracebackType
from typing import Self

from bayios.adapters.db.models.inventory import (
    StockCountItem,
    StockCountSession,
    StockMovement,
)
from bayios.adapters.db.models.products import (
    Product,
    ProductCategory,
    ProductImportBatch,
    ProductPriceHistory,
)
from bayios.adapters.db.models.reservations import (
    Reservation,
    ReservationItem,
    ReservationItemEvent,
    ReservationReminder,
)
from bayios.domain.products import normalize_product_name


class FakeProductRepository:
    def __init__(self) -> None:
        self.products: dict[uuid.UUID, Product] = {}
        self.categories: dict[uuid.UUID, ProductCategory] = {}
        self.price_history: list[ProductPriceHistory] = []
        self.stock_movements: list[StockMovement] = []
        self.import_batches: list[ProductImportBatch] = []

    def search(
        self,
        query: str | None = None,
        category_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
        only_archived: bool = False,
    ) -> tuple[Sequence[Product], int]:
        results = list(self.products.values())
        if only_archived:
            results = [p for p in results if getattr(p, "is_archived", False)]
        elif not include_archived:
            results = [p for p in results if not getattr(p, "is_archived", False)]

        if category_id is not None:
            results = [p for p in results if p.category_id == category_id]

        if query and query.strip():
            normalized = normalize_product_name(query)
            clean = query.strip().lower()
            results = [
                p
                for p in results
                if normalized in p.name_normalized or clean in p.name.lower()
            ]
        results.sort(key=lambda p: p.name)
        total = len(results)
        return results[offset : offset + limit], total

    def get_by_id(self, product_id: uuid.UUID) -> Product | None:
        return self.products.get(product_id)

    def get_by_ids(self, product_ids: Sequence[uuid.UUID]) -> Sequence[Product]:
        target = set(product_ids)
        return [p for p in self.products.values() if p.id in target]

    def set_archived(self, product_ids: Sequence[uuid.UUID], archived: bool = True) -> int:
        count = 0
        for pid in product_ids:
            if pid in self.products:
                self.products[pid].is_archived = archived
                count += 1
        return count

    def delete_products(self, product_ids: Sequence[uuid.UUID]) -> int:
        target = set(product_ids)
        self.price_history = [h for h in self.price_history if h.product_id not in target]
        self.stock_movements = [m for m in self.stock_movements if m.product_id not in target]
        count = 0
        for pid in list(self.products.keys()):
            if pid in target:
                del self.products[pid]
                count += 1
        return count

    def set_category(
        self, product_ids: Sequence[uuid.UUID], category_id: uuid.UUID | None
    ) -> int:
        count = 0
        for product_id in product_ids:
            product = self.products.get(product_id)
            if product is not None:
                product.category_id = category_id
                count += 1
        return count

    def get_by_normalized_name(self, normalized_name: str) -> Product | None:
        for p in self.products.values():
            if p.name_normalized == normalized_name:
                return p
        return None

    def get_by_normalized_names(self, names: Sequence[str]) -> dict[str, Product]:
        target = set(names)
        return {
            p.name_normalized: p
            for p in self.products.values()
            if p.name_normalized in target
        }

    def add(self, product: Product) -> None:
        self.products[product.id] = product

    def get_all(self) -> Sequence[Product]:
        results = list(self.products.values())
        results.sort(key=lambda p: p.name)
        return results

    def list_by_category(
        self,
        category_id: uuid.UUID | None,
        include_archived: bool = False,
    ) -> Sequence[Product]:
        results = [
            product
            for product in self.products.values()
            if (category_id is None or product.category_id == category_id)
            and (include_archived or not product.is_archived)
        ]
        results.sort(key=lambda p: p.name)
        return results

    def search_by_category(
        self,
        category_id: uuid.UUID | None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
    ) -> tuple[Sequence[Product], int]:
        results = [
            product
            for product in self.products.values()
            if (category_id is None or product.category_id == category_id)
            and (include_archived or not product.is_archived)
        ]
        if query and query.strip():
            normalized = normalize_product_name(query)
            clean = query.strip().lower()
            results = [
                product
                for product in results
                if normalized in product.name_normalized or clean in product.name.lower()
            ]
        results.sort(key=lambda p: p.name)
        total = len(results)
        return results[offset : offset + limit], total

    def get_categories(self) -> Sequence[ProductCategory]:
        return sorted(self.categories.values(), key=lambda category: category.name)

    def get_category(self, category_id: uuid.UUID) -> ProductCategory | None:
        return self.categories.get(category_id)

    def get_category_by_name(self, name: str) -> ProductCategory | None:
        for category in self.categories.values():
            if category.name == name:
                return category
        return None

    def add_category(self, category: ProductCategory) -> None:
        self.categories[category.id] = category

    def get_price_history(self, product_id: uuid.UUID) -> Sequence[ProductPriceHistory]:
        return [h for h in self.price_history if h.product_id == product_id]

    def get_stock_movements(self, product_id: uuid.UUID) -> Sequence[StockMovement]:
        return [m for m in self.stock_movements if m.product_id == product_id]

    def add_price_history(self, history: ProductPriceHistory) -> None:
        self.price_history.append(history)

    def add_stock_movement(self, movement: StockMovement) -> None:
        self.stock_movements.append(movement)

    def create_import_batch(self, batch: ProductImportBatch) -> None:
        self.import_batches.append(batch)

    def get_import_batch_by_checksum(self, checksum: str) -> ProductImportBatch | None:
        for b in reversed(self.import_batches):
            if b.source_checksum == checksum:
                return b
        return None


class FakeStockCountRepository:
    def __init__(self, products: FakeProductRepository) -> None:
        self._products = products
        self.sessions: dict[uuid.UUID, StockCountSession] = {}
        self.items: dict[uuid.UUID, list[StockCountItem]] = {}
        self._next_number = 1

    def add_session(self, session: StockCountSession) -> None:
        if getattr(session, "count_number", None) is None:
            session.count_number = self._next_number
            self._next_number += 1
        self.sessions[session.id] = session

    def add_items(self, items: Sequence[StockCountItem]) -> None:
        for item in items:
            self.items.setdefault(item.session_id, []).append(item)

    def get_session(self, session_id: uuid.UUID) -> StockCountSession | None:
        return self.sessions.get(session_id)

    def get_items(self, session_id: uuid.UUID) -> Sequence[StockCountItem]:
        return sorted(
            self.items.get(session_id, []), key=lambda item: item.product_name
        )

    def list_sessions(self, limit: int = 20) -> Sequence[StockCountSession]:
        sessions = sorted(
            self.sessions.values(), key=lambda session: session.started_at, reverse=True
        )
        return sessions[:limit]

    def delete_item(self, item: StockCountItem) -> None:
        bucket = self.items.get(item.session_id, [])
        if item in bucket:
            bucket.remove(item)

    def stock_version(self, category_id: uuid.UUID | None) -> int:
        if category_id is None:
            return len(self._products.stock_movements)
        product_ids = {
            product.id
            for product in self._products.products.values()
            if product.category_id == category_id
        }
        return sum(
            1
            for movement in self._products.stock_movements
            if movement.product_id in product_ids
        )


class FakeReservationRepository:
    def __init__(self, products: FakeProductRepository) -> None:
        self._products = products
        self.reservations: dict[uuid.UUID, Reservation] = {}
        self.items: dict[uuid.UUID, list[ReservationItem]] = {}
        self.events: list[ReservationItemEvent] = []
        self.reminders: list[ReservationReminder] = []
        self._next_number = 1

    def add(self, reservation: Reservation) -> None:
        if getattr(reservation, "reservation_number", None) is None:
            reservation.reservation_number = self._next_number
            self._next_number += 1
        self.reservations[reservation.id] = reservation

    def add_item(self, item: ReservationItem) -> None:
        self.items.setdefault(item.reservation_id, []).append(item)

    def add_items(self, items: Sequence[ReservationItem]) -> None:
        for item in items:
            self.add_item(item)

    def get(self, reservation_id: uuid.UUID) -> Reservation | None:
        return self.reservations.get(reservation_id)

    def get_items(self, reservation_id: uuid.UUID) -> Sequence[ReservationItem]:
        return sorted(
            self.items.get(reservation_id, []),
            key=lambda item: (item.product_name_snapshot, str(item.id)),
        )

    def get_items_for_reservations(
        self, reservation_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, Sequence[ReservationItem]]:
        return {
            reservation_id: self.get_items(reservation_id)
            for reservation_id in reservation_ids
        }

    def get_item(self, item_id: uuid.UUID) -> ReservationItem | None:
        for bucket in self.items.values():
            for item in bucket:
                if item.id == item_id:
                    return item
        return None

    def lock_item(self, item_id: uuid.UUID) -> ReservationItem | None:
        return self.get_item(item_id)

    def lock_product(self, product_id: uuid.UUID) -> Product | None:
        return self._products.get_by_id(product_id)

    def delete_item(self, item: ReservationItem) -> None:
        bucket = self.items.get(item.reservation_id, [])
        if item in bucket:
            bucket.remove(item)
        self.events = [
            event
            for event in self.events
            if event.reservation_item_id != item.id
        ]

    def list(
        self,
        *,
        status: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
        now=None,
    ) -> tuple[Sequence[Reservation], int]:
        from datetime import UTC, datetime

        reference = now or datetime.now(UTC)
        results = sorted(
            self.reservations.values(),
            key=lambda reservation: (
                reservation.reservation_date,
                reservation.reservation_number,
            ),
            reverse=True,
        )

        def line_bucket(reservation: Reservation) -> list[ReservationItem]:
            return self.items.get(reservation.id, [])

        def has_open(reservation: Reservation) -> bool:
            return any(
                item.quantity - item.delivered_quantity - item.cancelled_quantity > 0
                for item in line_bucket(reservation)
            )

        if status == "open":
            results = [reservation for reservation in results if has_open(reservation)]
        elif status == "delivered":
            results = [
                reservation
                for reservation in results
                if not has_open(reservation)
                and any(item.delivered_quantity > 0 for item in line_bucket(reservation))
            ]
        elif status == "cancelled":
            results = [
                reservation
                for reservation in results
                if not has_open(reservation)
                and not any(
                    item.delivered_quantity > 0 for item in line_bucket(reservation)
                )
                and bool(line_bucket(reservation))
            ]
        elif status == "overdue":
            results = [
                reservation
                for reservation in results
                if reservation.reminder_status != "resolved"
                and reservation.reminder_due_at <= reference
            ]

        if query and query.strip():
            clean = query.strip().lower()
            results = [
                reservation
                for reservation in results
                if clean in reservation.customer_name.lower()
            ]
        total = len(results)
        return results[offset : offset + limit], total

    def list_reminders(
        self, *, due_before, limit: int = 50
    ) -> Sequence[Reservation]:
        results = [
            reservation
            for reservation in self.reservations.values()
            if reservation.reminder_status != "resolved"
            and reservation.reminder_due_at <= due_before
        ]
        results.sort(key=lambda reservation: reservation.reminder_due_at)
        return results[:limit]

    def add_event(self, event: ReservationItemEvent) -> None:
        self.events.append(event)

    def get_events(self, reservation_id: uuid.UUID) -> Sequence[ReservationItemEvent]:
        item_ids = {item.id for item in self.items.get(reservation_id, [])}
        return [event for event in self.events if event.reservation_item_id in item_ids]

    def add_reminder(self, reminder: ReservationReminder) -> None:
        self.reminders.append(reminder)

    def get_reminders(
        self, reservation_id: uuid.UUID
    ) -> Sequence[ReservationReminder]:
        return [
            reminder
            for reminder in reversed(self.reminders)
            if reminder.reservation_id == reservation_id
        ]

    def open_quantity_by_product(
        self, product_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        target = set(product_ids)
        totals: dict[uuid.UUID, int] = {}
        for bucket in self.items.values():
            for item in bucket:
                if item.product_id not in target:
                    continue
                open_quantity = (
                    item.quantity - item.delivered_quantity - item.cancelled_quantity
                )
                if open_quantity > 0:
                    totals[item.product_id] = (
                        totals.get(item.product_id, 0) + open_quantity
                    )
        return totals

    def open_product_ids(self, product_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        return set(self.open_quantity_by_product(product_ids))

    def find_stock_movement(self, idempotency_key: str):
        for movement in self._products.stock_movements:
            if movement.idempotency_key == idempotency_key:
                return movement
        return None


class FakeUnitOfWork:
    def __init__(self, repo: FakeProductRepository | None = None) -> None:
        self.products = repo or FakeProductRepository()
        self.stock_counts = FakeStockCountRepository(self.products)
        self.reservations = FakeReservationRepository(self.products)
        self.committed = False
        self.rolled_back = False
        self._initial_state: tuple[object, ...] | None = None

    def _state(self) -> tuple[object, ...]:
        products = tuple(
            sorted(
                (
                    str(p.id),
                    p.name,
                    p.name_normalized,
                    getattr(p, "is_archived", None),
                    getattr(p, "physical_stock", None),
                    getattr(p, "regular_price", None),
                    getattr(p, "website_discounted_price", None),
                    getattr(p, "cost_price", None),
                )
                for p in self.products.products.values()
            )
        )
        return (
            products,
            len(self.products.price_history),
            len(self.products.stock_movements),
            len(self.products.import_batches),
            tuple(
                sorted(
                    (str(session.id), session.status, session.stock_version)
                    for session in self.stock_counts.sessions.values()
                )
            ),
            tuple(
                sorted(
                    (
                        str(item.id),
                        str(item.session_id),
                        item.system_quantity,
                        item.counted_quantity,
                        item.difference,
                    )
                    for bucket in self.stock_counts.items.values()
                    for item in bucket
                )
            ),
            tuple(
                sorted(
                    (
                        str(reservation.id),
                        reservation.customer_name,
                        reservation.reminder_status,
                        str(reservation.reminder_due_at),
                    )
                    for reservation in self.reservations.reservations.values()
                )
            ),
            tuple(
                sorted(
                    (
                        str(item.id),
                        str(item.reservation_id),
                        str(item.product_id),
                        item.product_name_snapshot,
                        item.quantity,
                        item.delivered_quantity,
                        item.cancelled_quantity,
                        item.status,
                    )
                    for bucket in self.reservations.items.values()
                    for item in bucket
                )
            ),
            len(self.reservations.events),
            len(self.reservations.reminders),
        )

    def __enter__(self) -> Self:
        self.committed = False
        self.rolled_back = False
        self._initial_state = self._state()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rollback()
        elif not self.committed and self._initial_state != self._state():
            raise AssertionError(
                "UnitOfWork exited with uncommitted writes; call uow.commit()"
            )

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True
