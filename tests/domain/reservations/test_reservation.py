from datetime import UTC, datetime

import pytest

from bayios.domain.reservations import (
    ReminderStatus,
    Reservation,
    ReservationItem,
    ReservationStatus,
    StockPosition,
    add_months,
    add_reservation_line,
    default_snooze_due,
    initial_reminder_due,
    is_reservation_resolved,
    next_reminder_status,
    remove_reservation_line,
    summarize_reservation,
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


def test_full_cancellation_marks_line_cancelled() -> None:
    item = ReservationItem(product_id="product-1", quantity=2)

    cancelled = item.cancel(quantity=2)

    assert cancelled.status is ReservationStatus.CANCELLED
    assert cancelled.open_quantity == 0


def test_cancellation_cannot_exceed_open_quantity() -> None:
    item = ReservationItem(product_id="product-1", quantity=2, delivered_quantity=1)

    with pytest.raises(ValueError, match="açık miktarı aşamaz"):
        item.cancel(quantity=2)


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


def test_status_steps_can_be_skipped_forward() -> None:
    item = ReservationItem(product_id="product-1", quantity=1)

    depot_ready = transition_item(item, ReservationStatus.DEPOT_READY)

    assert depot_ready.status is ReservationStatus.DEPOT_READY


def test_status_can_step_back_before_delivery() -> None:
    item = ReservationItem(
        product_id="product-1",
        quantity=1,
        status=ReservationStatus.SERVICE_ASSIGNED,
    )

    back = transition_item(item, ReservationStatus.DEPOT_READY)

    assert back.status is ReservationStatus.DEPOT_READY
    assert back.open_quantity == 1


@pytest.mark.parametrize(
    "target", [ReservationStatus.DELIVERED, ReservationStatus.CANCELLED]
)
def test_terminal_statuses_are_not_produced_by_transition(
    target: ReservationStatus,
) -> None:
    item = ReservationItem(product_id="product-1", quantity=1)

    with pytest.raises(ValueError, match="teslim veya iptal"):
        transition_item(item, target)


def test_terminal_line_rejects_status_changes() -> None:
    item = ReservationItem(
        product_id="product-1",
        quantity=1,
        status=ReservationStatus.DELIVERED,
    )

    with pytest.raises(ValueError, match="Tamamlanmış"):
        transition_item(item, ReservationStatus.DEPOT_READY)


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


def test_direct_delivery_from_reserved_is_allowed() -> None:
    item = ReservationItem(product_id="product-1", quantity=1)

    delivered = item.deliver(quantity=1, physical_stock=5, idempotency_key="delivery-1")

    assert delivered.item.status is ReservationStatus.DELIVERED
    assert delivered.physical_stock == 4


def test_partial_delivery_keeps_line_active() -> None:
    item = ReservationItem(product_id="product-1", quantity=2)

    delivered = item.deliver(quantity=1, physical_stock=5, idempotency_key="delivery-1")

    assert delivered.item.status is ReservationStatus.RESERVED
    assert delivered.item.delivered_quantity == 1
    assert delivered.item.open_quantity == 1


def test_low_stock_delivery_requires_reason_and_records_warning() -> None:
    item = ReservationItem(
        product_id="product-1",
        quantity=2,
        status=ReservationStatus.SERVICE_ASSIGNED,
    )

    with pytest.raises(ValueError, match="gerekçe"):
        item.deliver(quantity=2, physical_stock=1, idempotency_key="delivery-1")

    delivered = item.deliver(
        quantity=2,
        physical_stock=1,
        idempotency_key="delivery-1",
        low_stock_reason="Customer delivery approved",
    )

    assert delivered.warning == "Fiziksel stok yetersiz."
    assert delivered.reason == "Customer delivery approved"
    assert delivered.physical_stock == -1


def test_reservation_item_rejects_invalid_quantity_invariant() -> None:
    with pytest.raises(ValueError, match="Teslim ve iptal"):
        ReservationItem(
            product_id="product-1",
            quantity=1,
            delivered_quantity=1,
            cancelled_quantity=1,
        )


def test_quantity_cannot_drop_below_closed_quantity() -> None:
    item = ReservationItem(
        product_id="product-1",
        quantity=4,
        delivered_quantity=2,
        cancelled_quantity=1,
    )

    assert item.change_quantity(3).quantity == 3
    with pytest.raises(ValueError, match="altına inemez"):
        item.change_quantity(2)
    with pytest.raises(ValueError, match="sıfırdan büyük"):
        item.change_quantity(0)


def test_line_with_closed_quantity_cannot_be_removed() -> None:
    items = (ReservationItem(product_id="a", quantity=2, delivered_quantity=1),)

    with pytest.raises(ValueError, match="kaldırılamaz"):
        remove_reservation_line(items, "a")


def test_open_line_can_be_removed_and_duplicate_product_rejected() -> None:
    item = ReservationItem(product_id="a", quantity=2)

    assert remove_reservation_line((item,), "a") == ()
    with pytest.raises(ValueError, match="zaten mevcut"):
        add_reservation_line((item,), ReservationItem(product_id="a", quantity=1))


def test_month_arithmetic_clamps_to_month_end() -> None:
    assert add_months(datetime(2026, 1, 31, tzinfo=UTC), 1) == datetime(
        2026, 2, 28, tzinfo=UTC
    )
    assert add_months(datetime(2024, 1, 31, tzinfo=UTC), 1) == datetime(
        2024, 2, 29, tzinfo=UTC
    )


def test_default_due_dates_are_thirteen_months_and_one_month() -> None:
    reservation_date = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)

    assert initial_reminder_due(reservation_date) == datetime(
        2027, 12, 10, 9, 0, tzinfo=UTC
    )
    assert default_snooze_due(reservation_date) == datetime(
        2026, 12, 10, 9, 0, tzinfo=UTC
    )


def test_reminder_status_resolves_when_all_lines_are_closed() -> None:
    items = (
        ReservationItem(product_id="a", quantity=1, delivered_quantity=1),
        ReservationItem(product_id="b", quantity=2, cancelled_quantity=2),
    )

    assert is_reservation_resolved(items)
    assert next_reminder_status(ReminderStatus.PENDING, items) is (
        ReminderStatus.RESOLVED
    )


def test_reminder_reopens_when_a_line_is_added_again() -> None:
    items = (ReservationItem(product_id="a", quantity=1),)

    assert next_reminder_status(ReminderStatus.RESOLVED, items) is (
        ReminderStatus.PENDING
    )


def test_summary_labels_cover_reserved_partial_and_terminal_states() -> None:
    reserved = summarize_reservation((ReservationItem(product_id="a", quantity=2),))
    partial = summarize_reservation(
        (
            ReservationItem(
                product_id="a",
                quantity=2,
                delivered_quantity=1,
                status=ReservationStatus.DELIVERY_REQUESTED,
            ),
        )
    )
    delivered = summarize_reservation(
        (ReservationItem(product_id="a", quantity=2, delivered_quantity=2),)
    )
    cancelled = summarize_reservation(
        (ReservationItem(product_id="a", quantity=2, cancelled_quantity=2),)
    )

    assert (reserved.label, reserved.open_quantity) == ("Rezerve", 2)
    assert partial.label == "Kısmi süreçte"
    assert partial.delivered_quantity == 1
    assert delivered.label == "Teslim edildi"
    assert delivered.is_open is False
    assert cancelled.label == "İptal"
