from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from bayios.adapters.db.models.products import Product
from bayios.application.errors import NotFoundError, ValidationError
from bayios.application.reservations import (
    NewReservationItem,
    add_reservation_item,
    cancel_item,
    change_item_status,
    create_reservation,
    deliver_item,
    get_open_reservation_totals,
    get_products_with_open_reservations,
    get_reservation_detail,
    list_reservations,
    remove_reservation_item,
    snooze_reminder,
    update_reservation,
    update_reservation_item_quantity,
)
from bayios.domain.reservations import ReservationStatus
from tests.fakes import FakeUnitOfWork

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


def _product(name: str, stock: int = 5) -> Product:
    return Product(
        id=uuid.uuid4(),
        name=name,
        name_normalized=name.lower(),
        regular_price=Decimal("100.00"),
        physical_stock=stock,
    )


@pytest.fixture
def products() -> tuple[FakeUnitOfWork, Product, Product]:
    uow = FakeUnitOfWork()
    first = _product("07325 A", stock=5)
    second = _product("09325 A", stock=4)
    uow.products.add(first)
    uow.products.add(second)
    return uow, first, second


def _create(uow: FakeUnitOfWork, *items: NewReservationItem) -> uuid.UUID:
    view = create_reservation(
        uow,
        "Ayşe Yılmaz",
        items,
        reservation_date=NOW,
        note="Kapıda teslim",
    )
    return view.id


def _first_item_id(uow: FakeUnitOfWork, reservation_id: uuid.UUID) -> uuid.UUID:
    view = get_reservation_detail(uow, reservation_id, now=NOW)
    assert view is not None
    return view.items[0].id


def test_create_reservation_keeps_physical_stock_and_sets_open_quantity(
    products: tuple[FakeUnitOfWork, Product, Product],
) -> None:
    uow, first, _ = products

    reservation_id = _create(uow, NewReservationItem(first.id, 2))
    view = get_reservation_detail(uow, reservation_id, now=NOW)

    assert view is not None
    assert first.physical_stock == 5
    assert view.summary.open_quantity == 2
    assert view.summary.total_quantity == 2
    assert view.summary.label == "Rezerve"
    assert view.reminder_status == "pending"
    assert view.reminder_due_at == datetime(2027, 12, 10, 9, 0, tzinfo=UTC)
    assert view.items[0].status is ReservationStatus.RESERVED.value
    assert view.items[0].status_label == "Rezerveli"
    assert view.items[0].events[0].note == "Rezervasyon oluşturuldu"


def test_create_requires_customer_name_and_lines(
    products: tuple[FakeUnitOfWork, Product, Product],
) -> None:
    uow, first, _ = products

    with pytest.raises(ValidationError, match="Müşteri adı"):
        create_reservation(uow, "  ", [NewReservationItem(first.id, 1)])
    with pytest.raises(ValidationError, match="En az bir ürün"):
        create_reservation(uow, "Ayşe", [])
    with pytest.raises(ValidationError, match="bulunamadı"):
        create_reservation(uow, "Ayşe", [NewReservationItem(uuid.uuid4(), 1)])


def test_status_steps_are_optional_reversible_and_stock_neutral(
    products: tuple[FakeUnitOfWork, Product, Product],
) -> None:
    uow, first, _ = products
    reservation_id = _create(uow, NewReservationItem(first.id, 2))
    item_id = _first_item_id(uow, reservation_id)

    change_item_status(
        uow, item_id, ReservationStatus.SERVICE_ASSIGNED, note="Servis atandı"
    )
    change_item_status(uow, item_id, ReservationStatus.DEPOT_READY, note="Geri alındı")
    view = get_reservation_detail(uow, reservation_id, now=NOW)

    assert view is not None
    assert first.physical_stock == 5
    assert view.items[0].status is ReservationStatus.DEPOT_READY.value
    assert view.summary.label == "Kısmi süreçte"
    assert [event.new_status for event in view.items[0].events] == [
        "reserved",
        "service_assigned",
        "depot_ready",
    ]

    with pytest.raises(ValidationError, match="kendi akışlarından"):
        change_item_status(uow, item_id, ReservationStatus.DELIVERED)


def test_partial_and_remaining_delivery_update_physical_and_open_stock(
    products: tuple[FakeUnitOfWork, Product, Product],
) -> None:
    uow, first, _ = products
    reservation_id = _create(uow, NewReservationItem(first.id, 2))
    item_id = _first_item_id(uow, reservation_id)

    deliver_item(uow, item_id, 1, idempotency_key="delivery-1", actor=None)
    after_first = get_reservation_detail(uow, reservation_id, now=NOW)
    assert after_first is not None
    assert first.physical_stock == 4
    assert after_first.summary.open_quantity == 1
    assert after_first.items[0].status is ReservationStatus.RESERVED.value

    deliver_item(uow, item_id, 1, idempotency_key="delivery-2")
    after_second = get_reservation_detail(uow, reservation_id, now=NOW)

    assert after_second is not None
    assert first.physical_stock == 3
    assert after_second.summary.open_quantity == 0
    assert after_second.summary.label == "Teslim edildi"
    assert after_second.items[0].status is ReservationStatus.DELIVERED.value
    assert after_second.reminder_status == "resolved"
    movement_types = [m.movement_type for m in uow.products.stock_movements]
    assert movement_types == ["delivery_out", "delivery_out"]
    assert [m.quantity_after for m in uow.products.stock_movements] == [4, 3]


def test_delivery_retry_with_same_idempotency_key_writes_nothing(
    products: tuple[FakeUnitOfWork, Product, Product],
) -> None:
    uow, first, _ = products
    reservation_id = _create(uow, NewReservationItem(first.id, 2))
    item_id = _first_item_id(uow, reservation_id)

    deliver_item(uow, item_id, 1, idempotency_key="same-key")
    deliver_item(uow, item_id, 1, idempotency_key="same-key")

    view = get_reservation_detail(uow, reservation_id, now=NOW)
    assert view is not None
    assert len(uow.products.stock_movements) == 1
    assert first.physical_stock == 4
    assert view.items[0].delivered_quantity == 1


def test_low_stock_delivery_requires_reason_and_allows_negative_stock(
    products: tuple[FakeUnitOfWork, Product, Product],
) -> None:
    uow, first, _ = products
    reservation_id = _create(uow, NewReservationItem(first.id, 3))
    item_id = _first_item_id(uow, reservation_id)
    first.physical_stock = 2

    with pytest.raises(ValidationError, match="gerekçe"):
        deliver_item(uow, item_id, 3, idempotency_key="low-1")

    deliver_item(
        uow,
        item_id,
        3,
        idempotency_key="low-2",
        low_stock_reason="Müşteri teslimi onaylandı",
    )

    view = get_reservation_detail(uow, reservation_id, now=NOW)
    assert view is not None
    assert first.physical_stock == -1
    assert view.items[0].delivered_quantity == 3
    assert "Gerekçe" in (view.items[0].events[-1].note or "")
    assert uow.products.stock_movements[0].quantity_after == -1


def test_cancel_reduces_open_quantity_without_stock_movement(
    products: tuple[FakeUnitOfWork, Product, Product],
) -> None:
    uow, first, _ = products
    reservation_id = _create(uow, NewReservationItem(first.id, 3))
    item_id = _first_item_id(uow, reservation_id)

    cancel_item(uow, item_id, 1, note="Müşteri vazgeçti")
    partial = get_reservation_detail(uow, reservation_id, now=NOW)
    assert partial is not None
    assert partial.summary.open_quantity == 2
    assert partial.summary.cancelled_quantity == 1
    assert partial.items[0].status is ReservationStatus.RESERVED.value
    assert first.physical_stock == 5
    assert uow.products.stock_movements == []

    cancel_item(uow, item_id, 2)
    done = get_reservation_detail(uow, reservation_id, now=NOW)
    assert done is not None
    assert done.summary.open_quantity == 0
    assert done.summary.label == "İptal"
    assert done.items[0].status is ReservationStatus.CANCELLED.value
    assert done.reminder_status == "resolved"
    assert uow.products.stock_movements == []


def test_multi_item_reservation_delivery_is_isolated(
    products: tuple[FakeUnitOfWork, Product, Product],
) -> None:
    uow, first, second = products
    reservation_id = _create(
        uow, NewReservationItem(first.id, 1), NewReservationItem(second.id, 2)
    )
    view = get_reservation_detail(uow, reservation_id, now=NOW)
    assert view is not None
    first_line = next(item for item in view.items if item.product_id == first.id)

    deliver_item(uow, first_line.id, 1, idempotency_key="multi-1")

    after = get_reservation_detail(uow, reservation_id, now=NOW)
    assert after is not None
    assert first.physical_stock == 4
    assert second.physical_stock == 4
    assert after.summary.open_quantity == 2
    assert after.summary.label == "Kısmi süreçte"


def test_item_edit_and_removal_rules(
    products: tuple[FakeUnitOfWork, Product, Product],
) -> None:
    uow, first, second = products
    reservation_id = _create(uow, NewReservationItem(first.id, 3))
    item_id = _first_item_id(uow, reservation_id)

    update_reservation_item_quantity(uow, item_id, 5, note="Müşteri 2 adet ekledi")
    view = get_reservation_detail(uow, reservation_id, now=NOW)
    assert view is not None
    assert view.items[0].quantity == 5
    assert view.items[0].events[-1].quantity_delta == 2

    deliver_item(uow, item_id, 2, idempotency_key="edit-1")
    with pytest.raises(ValidationError, match="below delivered"):
        update_reservation_item_quantity(uow, item_id, 1)
    with pytest.raises(ValidationError, match="cannot be removed"):
        remove_reservation_item(uow, item_id)

    added_id = add_reservation_item(uow, reservation_id, second.id, 2)
    updated = get_reservation_detail(uow, reservation_id, now=NOW)
    assert updated is not None
    assert len(updated.items) == 2
    assert updated.summary.total_quantity == 7

    with pytest.raises(ValidationError, match="zaten var"):
        add_reservation_item(uow, reservation_id, second.id, 1)

    second_line = next(item for item in updated.items if item.id == added_id)
    assert second_line.open_quantity == 2
    remove_reservation_item(uow, added_id)
    final = get_reservation_detail(uow, reservation_id, now=NOW)
    assert final is not None
    assert len(final.items) == 1


def test_update_reservation_header(
    products: tuple[FakeUnitOfWork, Product, Product],
) -> None:
    uow, first, _ = products
    reservation_id = _create(uow, NewReservationItem(first.id, 1))

    update_reservation(uow, reservation_id, "Mehmet Kaya", note="Yeni not")
    view = get_reservation_detail(uow, reservation_id, now=NOW)

    assert view is not None
    assert view.customer_name == "Mehmet Kaya"
    assert view.note == "Yeni not"

    with pytest.raises(ValidationError, match="Müşteri adı"):
        update_reservation(uow, reservation_id, " ")
    with pytest.raises(NotFoundError):
        update_reservation(uow, uuid.uuid4(), "Yok")


def test_snooze_records_history_and_blocks_resolved_reservations(
    products: tuple[FakeUnitOfWork, Product, Product],
) -> None:
    uow, first, _ = products
    reservation_id = _create(uow, NewReservationItem(first.id, 1))

    snooze_reminder(uow, reservation_id, note="Müşteri arandı", now=NOW)
    view = get_reservation_detail(uow, reservation_id, now=NOW)

    assert view is not None
    assert view.reminder_status == "snoozed"
    assert view.reminder_due_at == datetime(2026, 12, 10, 9, 0, tzinfo=UTC)
    assert len(view.reminders) == 1
    assert view.reminders[0].note == "Müşteri arandı"

    snooze_reminder(
        uow,
        reservation_id,
        new_due_at=NOW + timedelta(days=60),
        now=NOW,
    )
    with pytest.raises(ValidationError, match="ileri"):
        snooze_reminder(uow, reservation_id, new_due_at=NOW - timedelta(days=1), now=NOW)

    item_id = _first_item_id(uow, reservation_id)
    deliver_item(uow, item_id, 1, idempotency_key="resolve-1")
    with pytest.raises(ValidationError, match="ertelenemez"):
        snooze_reminder(uow, reservation_id, now=NOW)


def test_listing_and_open_totals(
    products: tuple[FakeUnitOfWork, Product, Product],
) -> None:
    uow, first, second = products
    open_id = _create(uow, NewReservationItem(first.id, 2))
    closed_id = _create(uow, NewReservationItem(second.id, 1))
    closed_line = _first_item_id(uow, closed_id)
    deliver_item(uow, closed_line, 1, idempotency_key="list-1")

    open_rows, open_total = list_reservations(uow, status="open", now=NOW)
    delivered_rows, delivered_total = list_reservations(
        uow, status="delivered", now=NOW
    )
    found, total = list_reservations(uow, query="ayşe", now=NOW)

    assert open_total == 1 and open_rows[0].id == open_id
    assert delivered_total == 1 and delivered_rows[0].id == closed_id
    assert delivered_rows[0].summary.label == "Teslim edildi"
    assert total == 2 and found[0].summary.open_quantity in (0, 2)

    totals = get_open_reservation_totals(uow, [first.id, second.id])
    assert totals == {first.id: 2}
    assert get_products_with_open_reservations(uow, [first.id, second.id]) == {
        first.id
    }


def test_product_screens_report_real_open_reservation_quantity(
    products: tuple[FakeUnitOfWork, Product, Product],
) -> None:
    from bayios.application.inventory import get_stock_overview
    from bayios.application.products import get_product_detail

    uow, first, _ = products
    _create(uow, NewReservationItem(first.id, 2))

    detail = get_product_detail(uow, first.id)
    rows, _ = get_stock_overview(uow)
    row = next(row for row in rows if row.product.id == first.id)

    assert detail is not None
    assert detail.open_reservation == 2
    assert row.summary.physical == 5
    assert row.summary.open_reservation == 2


def test_product_delete_is_blocked_while_a_reservation_line_is_open(
    products: tuple[FakeUnitOfWork, Product, Product],
) -> None:
    from bayios.application.errors import ProductHasOpenReservationsError
    from bayios.application.products import delete_products

    uow, first, _ = products
    reservation_id = _create(uow, NewReservationItem(first.id, 1))

    with pytest.raises(ProductHasOpenReservationsError, match="açık rezervasyonda"):
        delete_products(uow, [first.id])
    assert first.id in uow.products.products

    item_id = _first_item_id(uow, reservation_id)
    deliver_item(uow, item_id, 1, idempotency_key="delete-guard-1")

    assert delete_products(uow, [first.id]) == 1
    assert first.id not in uow.products.products
