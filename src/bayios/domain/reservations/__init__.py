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
        return self.physical - self.open_reservation


@dataclass(frozen=True)
class ReservationItem:
    product_id: str
    quantity: int
    delivered_quantity: int = 0
    cancelled_quantity: int = 0
    status: ReservationStatus = ReservationStatus.RESERVED

    @property
    def open_quantity(self) -> int:
        return self.quantity - self.delivered_quantity - self.cancelled_quantity

    def deliver(
        self,
        quantity: int,
        physical_stock: int,
        idempotency_key: str,
        processed_idempotency_keys: frozenset[str] = frozenset(),
    ) -> DeliveryOutcome:
        if idempotency_key in processed_idempotency_keys:
            return DeliveryOutcome(
                item=self,
                physical_stock=physical_stock,
                processed_idempotency_keys=processed_idempotency_keys,
            )
        if quantity <= 0:
            raise ValueError("Delivery quantity must be positive")
        if quantity > self.open_quantity:
            raise ValueError("Delivery quantity exceeds open quantity")
        if quantity > physical_stock:
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
