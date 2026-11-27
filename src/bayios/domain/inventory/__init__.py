from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum


class MovementType(StrEnum):
    CSV_UPDATE = "csv_update"
    DELIVERY_OUT = "delivery_out"
    STOCK_COUNT_ADJUSTMENT = "stock_count_adjustment"
    REVERSAL = "reversal"


class StockStatus(StrEnum):
    """Single source of truth for the 0-is-out-of-stock rule."""

    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    NEGATIVE = "negative"


STOCK_STATUS_LABELS: Mapping[StockStatus, str] = {
    StockStatus.IN_STOCK: "Stokta",
    StockStatus.OUT_OF_STOCK: "Stok yok",
    StockStatus.NEGATIVE: "Stok düzeltmesi gerekli",
}


def stock_status(quantity: int) -> StockStatus:
    """0 means out of stock; negative stock stays visible as a correction need."""
    if quantity > 0:
        return StockStatus.IN_STOCK
    if quantity == 0:
        return StockStatus.OUT_OF_STOCK
    return StockStatus.NEGATIVE


@dataclass(frozen=True)
class StockMovement:
    product_id: str
    movement_type: MovementType
    quantity_delta: int
    quantity_before: int
    quantity_after: int
    created_at: datetime
    actor_name: str | None


@dataclass(frozen=True)
class StockSummary:
    physical: int
    open_reservation: int


@dataclass(frozen=True)
class CountSession:
    category_id: str
    snapshots: Mapping[str, int]
    stock_version: int
    opened_at: datetime
    completed: bool = False
    completed_at: datetime | None = None
    actor_name: str | None = None
    adjustments: Mapping[str, int] = field(default_factory=dict)
    movements: tuple[StockMovement, ...] = ()
    counted_count: int = 0
    skipped_count: int = 0
    total_difference: int = 0

    @classmethod
    def open(
        cls,
        category_id: str,
        quantities: Mapping[str, int],
        stock_version: int,
        opened_at: datetime,
    ) -> CountSession:
        return cls(
            category_id=category_id,
            snapshots=dict(quantities),
            stock_version=stock_version,
            opened_at=opened_at,
        )


@dataclass(frozen=True)
class CountCompletion:
    session: CountSession
    adjustments: dict[str, int]
    actor_name: str | None
    movements: tuple[StockMovement, ...] = ()
    counted_count: int = 0
    skipped_count: int = 0
    total_difference: int = 0


@dataclass(frozen=True)
class CountReversal:
    movements: tuple[StockMovement, ...]


def complete_count_session(
    session: CountSession,
    counted_quantities: Mapping[str, int],
    current_quantities: Mapping[str, int],
    actor_name: str | None,
    *,
    completed_at: datetime,
) -> CountCompletion:
    """Apply entered counts, ignoring blank/zero and uncounted lines.

    Only products with a positive counted quantity may change stock. A zero or
    missing value means "not counted" and never zeroes the existing stock.
    """
    if session.completed:
        return CountCompletion(
            session=session,
            adjustments=dict(session.adjustments),
            actor_name=session.actor_name,
            movements=session.movements,
            counted_count=session.counted_count,
            skipped_count=session.skipped_count,
            total_difference=session.total_difference,
        )
    unknown = set(counted_quantities) - set(session.snapshots)
    if unknown:
        raise ValueError("Sayılan miktarlar kategori anlık görüntüsünü kapsamalıdır.")

    applied: dict[str, int] = {}
    for product_id, quantity in counted_quantities.items():
        if quantity < 0:
            raise ValueError("Sayılan miktar negatif olamaz.")
        if quantity == 0:
            continue
        current = current_quantities.get(product_id)
        if current is None:
            raise ValueError("Sayımda güncel stoğu bulunmayan ürün var.")
        if current != session.snapshots[product_id]:
            raise ValueError(
                "Sayım açıldıktan sonra stok değişti. Farkları yenileyip tekrar kaydedin."
            )
        applied[product_id] = quantity

    adjustments = {
        product_id: quantity - current_quantities[product_id]
        for product_id, quantity in applied.items()
        if quantity != current_quantities[product_id]
    }
    movements = tuple(
        StockMovement(
            product_id=product_id,
            movement_type=MovementType.STOCK_COUNT_ADJUSTMENT,
            quantity_delta=quantity_delta,
            quantity_before=current_quantities[product_id],
            quantity_after=applied[product_id],
            created_at=completed_at,
            actor_name=actor_name,
        )
        for product_id, quantity_delta in adjustments.items()
    )
    total_difference = sum(adjustments.values())
    completed_session = replace(
        session,
        completed=True,
        completed_at=completed_at,
        actor_name=actor_name,
        adjustments=dict(adjustments),
        movements=movements,
        counted_count=len(applied),
        skipped_count=len(session.snapshots) - len(applied),
        total_difference=total_difference,
    )
    return CountCompletion(
        session=completed_session,
        adjustments=adjustments,
        actor_name=actor_name,
        movements=movements,
        counted_count=len(applied),
        skipped_count=len(session.snapshots) - len(applied),
        total_difference=total_difference,
    )


def reverse_count_session(
    session: CountSession,
    applied_movements: tuple[StockMovement, ...],
    current_quantities: Mapping[str, int],
    actor_name: str | None,
    *,
    reversed_at: datetime,
) -> CountReversal:
    """Build compensating movements for a completed count.

    Refuses to overwrite stock that changed after the count was applied.
    """
    if not session.completed:
        raise ValueError("Yalnızca tamamlanmış sayım geri alınabilir.")
    reversals: list[StockMovement] = []
    for movement in applied_movements:
        if movement.quantity_delta == 0:
            continue
        current = current_quantities.get(movement.product_id)
        if current is None:
            raise ValueError("Sayımda güncel stoğu bulunmayan ürün var.")
        if current != movement.quantity_after:
            raise ValueError(
                "Sayımdan sonra stok değişti; bu sayım geri alınamaz. Önce stoğu kontrol edin."
            )
        reversals.append(
            StockMovement(
                product_id=movement.product_id,
                movement_type=MovementType.REVERSAL,
                quantity_delta=-movement.quantity_delta,
                quantity_before=current,
                quantity_after=current - movement.quantity_delta,
                created_at=reversed_at,
                actor_name=actor_name,
            )
        )
    return CountReversal(movements=tuple(reversals))
