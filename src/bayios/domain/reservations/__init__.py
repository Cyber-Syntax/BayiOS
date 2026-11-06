from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class ReservationStatus(StrEnum):
    RESERVED = "reserved"
    DELIVERY_REQUESTED = "delivery_requested"
    DEPOT_READY = "depot_ready"
    SERVICE_ASSIGNED = "service_assigned"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class StockPosition:
    physical: int
    open_reservation: int

    @property
    def sellable(self) -> int:
        return max(0, self.physical - self.open_reservation)

    @property
    def supply_need(self) -> int:
        return max(0, self.open_reservation - self.physical)


@dataclass(frozen=True)
class ReservationItem:
    product_id: str
    quantity: int
    delivered_quantity: int = 0
    cancelled_quantity: int = 0
    status: ReservationStatus = ReservationStatus.RESERVED

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise ValueError("Quantity must be non-negative")
        if self.delivered_quantity < 0 or self.cancelled_quantity < 0:
            raise ValueError("Delivered and cancelled quantities must be non-negative")
        if self.delivered_quantity + self.cancelled_quantity > self.quantity:
            raise ValueError("Delivered and cancelled quantities exceed quantity")

    @property
    def open_quantity(self) -> int:
        return self.quantity - self.delivered_quantity - self.cancelled_quantity

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
        if quantity <= 0:
            raise ValueError("Delivery quantity must be positive")
        if self.status is not ReservationStatus.SERVICE_ASSIGNED:
            raise ValueError("Delivery requires SERVICE_ASSIGNED status")
        if quantity > self.open_quantity:
            raise ValueError("Delivery quantity exceeds open quantity")
        low_stock = quantity > physical_stock
        if low_stock and not low_stock_reason:
            raise ValueError("A reason is required when physical stock is insufficient")
        if physical_stock < 0:
            raise ValueError("Physical stock is insufficient")

        delivered_quantity = self.delivered_quantity + quantity
        status = (
            ReservationStatus.DELIVERED
            if self.open_quantity == quantity
            else ReservationStatus.SERVICE_ASSIGNED
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


def transition_item(item: ReservationItem, target: ReservationStatus) -> ReservationItem:
    transitions = {
        ReservationStatus.RESERVED: ReservationStatus.DELIVERY_REQUESTED,
        ReservationStatus.DELIVERY_REQUESTED: ReservationStatus.DEPOT_READY,
        ReservationStatus.DEPOT_READY: ReservationStatus.SERVICE_ASSIGNED,
    }
    if transitions.get(item.status) is not target:
        raise ValueError(f"Invalid reservation transition: {item.status} -> {target}")
    return replace(item, status=target)
