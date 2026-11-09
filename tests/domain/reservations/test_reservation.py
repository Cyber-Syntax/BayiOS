import pytest

from bayios.domain.reservations import (
    Reservation,
    ReservationItem,
    ReservationStatus,
    StockPosition,
    transition_item,
)


def test_reservation_does_not_reduce_physical_stock() -> None:
    position = StockPosition(physical=5, open_reservation=2)

    assert position.physical == 5
    assert position.open_reservation == 2


def test_stock_position_reports_physical_and_open_reservation_only() -> None:
    position = StockPosition(physical=1, open_reservation=3)

    assert position.physical == 1
    assert position.open_reservation == 3


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


def test_delivery_requires_service_assignment() -> None:
    item = ReservationItem(product_id="product-1", quantity=1)

    with pytest.raises(ValueError, match="SERVICE_ASSIGNED"):
        item.deliver(quantity=1, physical_stock=1, idempotency_key="delivery-1")


def test_low_stock_delivery_requires_reason_and_records_warning() -> None:
    item = ReservationItem(
        product_id="product-1",
        quantity=2,
        status=ReservationStatus.SERVICE_ASSIGNED,
    )

    with pytest.raises(ValueError, match="reason"):
        item.deliver(quantity=2, physical_stock=1, idempotency_key="delivery-1")

    delivered = item.deliver(
        quantity=2,
        physical_stock=1,
        idempotency_key="delivery-1",
        low_stock_reason="Customer delivery approved",
    )

    assert delivered.warning == "Physical stock is insufficient"
    assert delivered.reason == "Customer delivery approved"


def test_reservation_item_rejects_invalid_quantity_invariant() -> None:
    with pytest.raises(ValueError, match="Delivered and cancelled"):
        ReservationItem(
            product_id="product-1",
            quantity=1,
            delivered_quantity=1,
            cancelled_quantity=1,
        )
