from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from bayios.adapters.db.models.inventory import StockMovement
from bayios.adapters.db.models.products import Product
from bayios.adapters.db.models.reservations import (
    Reservation,
    ReservationItem,
    ReservationItemEvent,
    ReservationReminder,
)

_OPEN_LINE = (
    ReservationItem.quantity
    - ReservationItem.delivered_quantity
    - ReservationItem.cancelled_quantity
) > 0


class SqlAlchemyReservationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, reservation: Reservation) -> None:
        self._session.add(reservation)
        self._session.flush()

    def add_item(self, item: ReservationItem) -> None:
        self._session.add(item)
        self._session.flush()

    def add_items(self, items: Sequence[ReservationItem]) -> None:
        self._session.add_all(items)
        self._session.flush()

    def get(self, reservation_id: uuid.UUID) -> Reservation | None:
        return self._session.get(Reservation, reservation_id)

    def get_items(self, reservation_id: uuid.UUID) -> Sequence[ReservationItem]:
        return self._session.scalars(
            sa.select(ReservationItem)
            .where(ReservationItem.reservation_id == reservation_id)
            .order_by(ReservationItem.created_at, ReservationItem.id)
        ).all()

    def get_items_for_reservations(
        self, reservation_ids: Sequence[uuid.UUID]
    ) -> Mapping[uuid.UUID, Sequence[ReservationItem]]:
        if not reservation_ids:
            return {}
        rows = self._session.scalars(
            sa.select(ReservationItem)
            .where(ReservationItem.reservation_id.in_(reservation_ids))
            .order_by(ReservationItem.created_at, ReservationItem.id)
        ).all()
        grouped: dict[uuid.UUID, list[ReservationItem]] = {
            reservation_id: [] for reservation_id in reservation_ids
        }
        for row in rows:
            grouped.setdefault(row.reservation_id, []).append(row)
        return grouped

    def get_item(self, item_id: uuid.UUID) -> ReservationItem | None:
        return self._session.get(ReservationItem, item_id)

    def lock_item(self, item_id: uuid.UUID) -> ReservationItem | None:
        return self._session.scalar(
            sa.select(ReservationItem)
            .where(ReservationItem.id == item_id)
            .with_for_update()
        )

    def lock_product(self, product_id: uuid.UUID) -> Product | None:
        return self._session.scalar(
            sa.select(Product).where(Product.id == product_id).with_for_update()
        )

    def delete_item(self, item: ReservationItem) -> None:
        self._session.delete(item)
        self._session.flush()

    def list(
        self,
        *,
        status: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
        now: datetime | None = None,
    ) -> tuple[Sequence[Reservation], int]:
        stmt = sa.select(Reservation)
        count_stmt = sa.select(sa.func.count(Reservation.id))
        open_exists = sa.select(ReservationItem.id).where(
            ReservationItem.reservation_id == Reservation.id, _OPEN_LINE
        )
        delivered_exists = sa.select(ReservationItem.id).where(
            ReservationItem.reservation_id == Reservation.id,
            ReservationItem.delivered_quantity > 0,
        )
        any_line_exists = sa.select(ReservationItem.id).where(
            ReservationItem.reservation_id == Reservation.id
        )

        conditions = []
        if status == "open":
            conditions.append(sa.exists(open_exists))
        elif status == "delivered":
            conditions.append(~sa.exists(open_exists))
            conditions.append(sa.exists(delivered_exists))
        elif status == "cancelled":
            conditions.append(~sa.exists(open_exists))
            conditions.append(~sa.exists(delivered_exists))
            conditions.append(sa.exists(any_line_exists))
        elif status == "overdue":
            conditions.append(Reservation.reminder_status != "resolved")
            conditions.append(Reservation.reminder_due_at <= (now or sa.func.now()))

        if query and query.strip():
            clean = query.strip()
            conditions.append(Reservation.customer_name.ilike(f"%{clean}%"))

        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)

        total = self._session.scalar(count_stmt) or 0
        reservations = self._session.scalars(
            stmt.order_by(
                Reservation.reservation_date.desc(), Reservation.reservation_number.desc()
            )
            .limit(limit)
            .offset(offset)
        ).all()
        return reservations, total

    def list_reminders(
        self, *, due_before: datetime, limit: int = 50
    ) -> Sequence[Reservation]:
        return self._session.scalars(
            sa.select(Reservation)
            .where(
                Reservation.reminder_status != "resolved",
                Reservation.reminder_due_at <= due_before,
            )
            .order_by(Reservation.reminder_due_at)
            .limit(limit)
        ).all()

    def add_event(self, event: ReservationItemEvent) -> None:
        self._session.add(event)
        self._session.flush()

    def get_events(self, reservation_id: uuid.UUID) -> Sequence[ReservationItemEvent]:
        return self._session.scalars(
            sa.select(ReservationItemEvent)
            .join(
                ReservationItem,
                ReservationItemEvent.reservation_item_id == ReservationItem.id,
            )
            .where(ReservationItem.reservation_id == reservation_id)
            .order_by(ReservationItemEvent.event_at, ReservationItemEvent.id)
        ).all()

    def add_reminder(self, reminder: ReservationReminder) -> None:
        self._session.add(reminder)
        self._session.flush()

    def get_reminders(
        self, reservation_id: uuid.UUID
    ) -> Sequence[ReservationReminder]:
        return self._session.scalars(
            sa.select(ReservationReminder)
            .where(ReservationReminder.reservation_id == reservation_id)
            .order_by(ReservationReminder.created_at.desc())
        ).all()

    def open_quantity_by_product(
        self, product_ids: Sequence[uuid.UUID]
    ) -> Mapping[uuid.UUID, int]:
        if not product_ids:
            return {}
        rows = self._session.execute(
            sa.select(
                ReservationItem.product_id,
                sa.func.sum(
                    ReservationItem.quantity
                    - ReservationItem.delivered_quantity
                    - ReservationItem.cancelled_quantity
                ),
            )
            .where(
                ReservationItem.product_id.in_(product_ids),
                ReservationItem.product_id.is_not(None),
                _OPEN_LINE,
            )
            .group_by(ReservationItem.product_id)
        ).all()
        return {
            product_id: int(quantity)
            for product_id, quantity in rows
            if product_id is not None
        }

    def open_product_ids(
        self, product_ids: Sequence[uuid.UUID]
    ) -> set[uuid.UUID]:
        return set(self.open_quantity_by_product(product_ids))

    def find_stock_movement(self, idempotency_key: str) -> StockMovement | None:
        return self._session.scalar(
            sa.select(StockMovement).where(
                StockMovement.idempotency_key == idempotency_key
            )
        )
