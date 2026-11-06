import pytest

from bayios.domain.reservations import (
    Reservation,
    ReservationItem,
    ReservationStatus,
    StockPosition,
    transition_item,
)


def test_reservation_reduces_sellable_stock_but_not_physical_stock() -> None:
    position = StockPosition(physical=5, open_reservation=2)

    assert position.physical == 5
    assert position.open_reservation == 2
    assert position.sellable == 3


def test_multi_product_reservation_keeps_open_quantities_independent() -> None:
    reservation = Reservation(
        items=(
            ReservationItem(product_id="product-1", quantity=2),
            ReservationItem(product_id="product-2", quantity=4),
        )
    )

    assert reservation.open_quantity_for("product-1") == 2
    assert reservation.open_quantity_for("product-2") == 4


def test_cancelling_open_quantity_does_not_reduce_physical_stock() -> None:
    item = ReservationItem(product_id="product-1", quantity=2)

    cancelled = item.cancel(quantity=1)

    assert cancelled.open_quantity == 1
    assert cancelled.cancelled_quantity == 1
    assert cancelled.status is ReservationStatus.RESERVED


@pytest.mark.parametrize(
    "status",
    [
        ReservationStatus.DELIVERY_REQUESTED,
        ReservationStatus.DEPOT_READY,
        ReservationStatus.SERVICE_ASSIGNED,
    ],
)
def test_reservation_item_can_progress_without_changing_physical_stock(
    status: ReservationStatus,
) -> None:
    item = ReservationItem(product_id="product-1", quantity=2)

    progressed = item
    for next_status in (
        ReservationStatus.DELIVERY_REQUESTED,
        ReservationStatus.DEPOT_READY,
        ReservationStatus.SERVICE_ASSIGNED,
    ):
        progressed = transition_item(progressed, next_status)
        if next_status is status:
            break
    position = StockPosition(physical=5, open_reservation=2)

    assert progressed.status is status
    assert position.physical == 5


def test_delivery_decreases_physical_and_open_stock_once_per_idempotency_key() -> None:
    item = ReservationItem(
        product_id="product-1",
        quantity=2,
        delivered_quantity=0,
        status=ReservationStatus.SERVICE_ASSIGNED,
    )

    first = item.deliver(quantity=1, physical_stock=5, idempotency_key="delivery-1")
    retry = first.item.deliver(
        quantity=1,
        physical_stock=first.physical_stock,
        idempotency_key="delivery-1",
        processed_idempotency_keys=first.processed_idempotency_keys,
    )

    assert first.item.delivered_quantity == 1
    assert first.item.open_quantity == 1
    assert first.physical_stock == 4
    assert retry == first
