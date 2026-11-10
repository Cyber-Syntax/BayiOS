from __future__ import annotations

import calendar
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

REMINDER_MONTHS = 13
SNOOZE_MONTHS = 1


class ReservationStatus(StrEnum):
    RESERVED = "reserved"
    DELIVERY_REQUESTED = "delivery_requested"
    DEPOT_READY = "depot_ready"
    SERVICE_ASSIGNED = "service_assigned"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class ReminderStatus(StrEnum):
    PENDING = "pending"
    SNOOZED = "snoozed"
    RESOLVED = "resolved"


ACTIVE_STATUSES: tuple[ReservationStatus, ...] = (
    ReservationStatus.RESERVED,
    ReservationStatus.DELIVERY_REQUESTED,
    ReservationStatus.DEPOT_READY,
    ReservationStatus.SERVICE_ASSIGNED,
)
TERMINAL_STATUSES: frozenset[ReservationStatus] = frozenset(
    {ReservationStatus.DELIVERED, ReservationStatus.CANCELLED}
)

SUMMARY_RESERVED = "Rezerve"
SUMMARY_PARTIAL = "Kısmi süreçte"
SUMMARY_DELIVERED = "Teslim edildi"
SUMMARY_CANCELLED = "İptal"
SUMMARY_PARTIALLY_CANCELLED = "Kısmen iptal"
SUMMARY_EMPTY = "Boş"


@dataclass(frozen=True)
class StockPosition:
    physical: int
    open_reservation: int


@dataclass(frozen=True)
class ReservationSummary:
    total_quantity: int
    delivered_quantity: int
    cancelled_quantity: int
    open_quantity: int
    label: str

    @property
    def is_open(self) -> bool:
        return self.open_quantity > 0


@dataclass(frozen=True)
class ReservationItem:
    """A quantity-bearing reservation line with independent delivery progress.

    The status tracks the operational phase of the line; delivered and cancelled
    quantities track the closed part of the quantity independently. Status changes
    never touch physical stock; only ``deliver`` does.
    """

    product_id: str | None
    quantity: int
    delivered_quantity: int = 0
    cancelled_quantity: int = 0
    status: ReservationStatus = ReservationStatus.RESERVED
    product_name: str = ""

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")
        if self.delivered_quantity < 0 or self.cancelled_quantity < 0:
            raise ValueError("Delivered and cancelled quantities must be non-negative")
        if self.delivered_quantity + self.cancelled_quantity > self.quantity:
            raise ValueError("Delivered and cancelled quantities exceed quantity")

    @property
    def open_quantity(self) -> int:
        return self.quantity - self.delivered_quantity - self.cancelled_quantity

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def is_removable(self) -> bool:
        return self.delivered_quantity == 0 and self.cancelled_quantity == 0

    def ensure_removable(self) -> None:
        if not self.is_removable:
            raise ValueError(
                "A line with delivered or cancelled quantity cannot be removed"
            )

    def change_quantity(self, new_quantity: int) -> ReservationItem:
        if new_quantity <= 0:
            raise ValueError("Quantity must be positive")
        closed_quantity = self.delivered_quantity + self.cancelled_quantity
        if new_quantity < closed_quantity:
            raise ValueError(
                "Quantity cannot be below delivered and cancelled quantities"
            )
        return replace(self, quantity=new_quantity)

    def deliver(
        self,
        quantity: int,
        physical_stock: int,
        idempotency_key: str,
        processed_idempotency_keys: frozenset[str] = frozenset(),
        low_stock_reason: str | None = None,
    ) -> DeliveryOutcome:
        if idempotency_key in processed_idempotency_keys:
            return DeliveryOutcome(
                item=self,
                physical_stock=physical_stock,
                processed_idempotency_keys=processed_idempotency_keys,
            )
        if self.is_terminal:
            raise ValueError("Terminal reservation line cannot be delivered")
        if quantity <= 0:
            raise ValueError("Delivery quantity must be positive")
        if quantity > self.open_quantity:
            raise ValueError("Delivery quantity exceeds open quantity")
        low_stock = quantity > physical_stock
        if low_stock and not low_stock_reason:
            raise ValueError("A reason is required when physical stock is insufficient")

        delivered_quantity = self.delivered_quantity + quantity
        status = (
            ReservationStatus.DELIVERED
            if self.open_quantity == quantity
            else self.status
        )
        return DeliveryOutcome(
            item=replace(
                self,
                delivered_quantity=delivered_quantity,
                status=status,
            ),
            physical_stock=physical_stock - quantity,
            processed_idempotency_keys=processed_idempotency_keys | {idempotency_key},
            warning="Physical stock is insufficient" if low_stock else None,
            reason=low_stock_reason,
        )

    def cancel(self, quantity: int) -> ReservationItem:
        if self.is_terminal:
            raise ValueError("Terminal reservation line cannot be cancelled")
        if quantity <= 0:
            raise ValueError("Cancellation quantity must be positive")
        if quantity > self.open_quantity:
            raise ValueError("Cancellation quantity exceeds open quantity")
        cancelled_quantity = self.cancelled_quantity + quantity
        status = (
            ReservationStatus.CANCELLED
            if self.open_quantity == quantity
            else self.status
        )
        return replace(
            self,
            cancelled_quantity=cancelled_quantity,
            status=status,
        )


@dataclass(frozen=True)
class DeliveryOutcome:
    item: ReservationItem
    physical_stock: int
    processed_idempotency_keys: frozenset[str]
    warning: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class Reservation:
    items: tuple[ReservationItem, ...]

    def open_quantity_for(self, product_id: str) -> int:
        return sum(
            item.open_quantity
            for item in self.items
            if item.product_id == product_id
        )

    @property
    def summary(self) -> ReservationSummary:
        return summarize_reservation(self.items)


def transition_item(item: ReservationItem, target: ReservationStatus) -> ReservationItem:
    """Move an active line to another active phase without touching stock.

    Intermediate phases are optional: an employee may jump forward and may step
    back until the line is delivered or cancelled. Terminal statuses are produced
    only by ``deliver`` and ``cancel``.
    """
    if item.status in TERMINAL_STATUSES:
        raise ValueError(
            f"Terminal reservation line cannot change status: {item.status}"
        )
    if target in TERMINAL_STATUSES:
        raise ValueError(f"{target} must be produced by deliver or cancel")
    if target not in ACTIVE_STATUSES:
        raise ValueError(f"Invalid reservation target status: {target}")
    if target is item.status:
        raise ValueError(f"Reservation line is already {target}")
    return replace(item, status=target)


def add_reservation_line(
    items: Sequence[ReservationItem],
    item: ReservationItem,
) -> tuple[ReservationItem, ...]:
    """Append a line, refusing a second line for the same product."""
    if item.product_id is not None and any(
        existing.product_id == item.product_id for existing in items
    ):
        raise ValueError("Product already exists in the reservation")
    return (*items, item)


def remove_reservation_line(
    items: Sequence[ReservationItem],
    product_id: str,
) -> tuple[ReservationItem, ...]:
    """Remove a line only while it has no delivered or cancelled quantity."""
    target = next(
        (existing for existing in items if existing.product_id == product_id), None
    )
    if target is None:
        raise ValueError("Reservation line not found")
    target.ensure_removable()
    return tuple(existing for existing in items if existing is not target)


def summarize_reservation(
    items: Sequence[ReservationItem],
) -> ReservationSummary:
    total_quantity = sum(item.quantity for item in items)
    delivered_quantity = sum(item.delivered_quantity for item in items)
    cancelled_quantity = sum(item.cancelled_quantity for item in items)
    open_quantity = sum(item.open_quantity for item in items)

    if not items:
        label = SUMMARY_EMPTY
    elif open_quantity == 0:
        if cancelled_quantity == total_quantity:
            label = SUMMARY_CANCELLED
        elif delivered_quantity == total_quantity:
            label = SUMMARY_DELIVERED
        else:
            label = SUMMARY_PARTIALLY_CANCELLED
    elif delivered_quantity or cancelled_quantity or any(
        item.status is not ReservationStatus.RESERVED for item in items
    ):
        label = SUMMARY_PARTIAL
    else:
        label = SUMMARY_RESERVED

    return ReservationSummary(
        total_quantity=total_quantity,
        delivered_quantity=delivered_quantity,
        cancelled_quantity=cancelled_quantity,
        open_quantity=open_quantity,
        label=label,
    )


def add_months(moment: datetime, months: int) -> datetime:
    """Calendar month arithmetic that clamps the day to the target month's end."""
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return moment.replace(year=year, month=month, day=min(moment.day, last_day))


def initial_reminder_due(reservation_date: datetime) -> datetime:
    """Default 13-month reminder due date (1 year 1 month)."""
    return add_months(reservation_date, REMINDER_MONTHS)


def default_snooze_due(reference: datetime) -> datetime:
    """Default snooze target: one calendar month after the reference moment."""
    return add_months(reference, SNOOZE_MONTHS)


def is_reservation_resolved(items: Sequence[ReservationItem]) -> bool:
    """A reservation is resolved when no line keeps an open quantity."""
    return bool(items) and all(item.open_quantity == 0 for item in items)


def next_reminder_status(
    current: ReminderStatus,
    items: Sequence[ReservationItem],
) -> ReminderStatus:
    """Resolve finished reservations and reopen them when a line is added again."""
    if not items:
        return current
    if is_reservation_resolved(items):
        return ReminderStatus.RESOLVED
    if current is ReminderStatus.RESOLVED:
        return ReminderStatus.PENDING
    return current
