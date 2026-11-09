from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum


class MovementType(StrEnum):
    CSV_UPDATE = "csv_update"
    DELIVERY_OUT = "delivery_out"
    STOCK_COUNT_ADJUSTMENT = "stock_count_adjustment"


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


def complete_count_session(
    session: CountSession,
    counted_quantities: Mapping[str, int],
    current_quantities: Mapping[str, int],
    current_version: int,
    actor_name: str | None,
    *,
    acknowledge_differences: bool = False,
    completed_at: datetime,
) -> CountCompletion:
    if session.completed:
        return CountCompletion(
            session=session,
            adjustments=dict(session.adjustments),
            actor_name=session.actor_name,
            movements=session.movements,
        )
    if current_version != session.stock_version:
        raise ValueError("Cannot complete stale count session")
    if set(counted_quantities) != set(session.snapshots):
        raise ValueError("Counted quantities must cover the category snapshot")

    adjustments = {
        product_id: counted_quantities[product_id] - current_quantities[product_id]
        for product_id in session.snapshots
        if counted_quantities[product_id] != current_quantities[product_id]
    }
    if adjustments and not acknowledge_differences:
        raise ValueError("difference review is required before completion")

    movements = tuple(
        StockMovement(
            product_id=product_id,
            movement_type=MovementType.STOCK_COUNT_ADJUSTMENT,
            quantity_delta=quantity_delta,
            quantity_before=current_quantities[product_id],
            quantity_after=counted_quantities[product_id],
            created_at=completed_at,
            actor_name=actor_name,
        )
        for product_id, quantity_delta in adjustments.items()
    )
    completed_session = replace(
        session,
        completed=True,
        completed_at=completed_at,
        actor_name=actor_name,
        adjustments=dict(adjustments),
        movements=movements,
    )
    return CountCompletion(
        session=completed_session,
        adjustments=adjustments,
        actor_name=actor_name,
        movements=movements,
    )
