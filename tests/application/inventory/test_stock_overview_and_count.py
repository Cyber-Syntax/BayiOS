from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from bayios.adapters.db.models.inventory import StockMovement
from bayios.adapters.db.models.products import Product, ProductCategory
from bayios.application.errors import ConflictError, ValidationError
from bayios.application.inventory import (
    add_stock_count_line,
    cancel_stock_count_session,
    complete_stock_count_session,
    create_product_category,
    get_stock_count_session,
    get_stock_overview,
    open_stock_count_session,
    refresh_stock_count_session,
    save_and_complete_stock_count,
    save_counted_quantities,
)
from bayios.domain.products import ActorContext
from tests.fakes import FakeUnitOfWork


def _add_product(
    uow: FakeUnitOfWork,
    name: str,
    *,
    physical_stock: int,
    category_id: uuid.UUID | None = None,
) -> Product:
    product = Product(
        id=uuid.uuid4(),
        name=name,
        name_normalized=name.lower(),
        physical_stock=physical_stock,
        category_id=category_id,
        is_archived=False,
    )
    uow.products.add(product)
    return product


def _add_movement(uow: FakeUnitOfWork, product: Product, delta: int) -> None:
    before = product.physical_stock
    product.physical_stock = before + delta
    uow.products.add_stock_movement(
        StockMovement(
            id=uuid.uuid4(),
            product_id=product.id,
            movement_type="delivery_out",
            quantity_delta=delta,
            quantity_before=before,
            quantity_after=product.physical_stock,
            created_at=datetime.now(UTC),
            created_by_name=None,
        )
    )


def test_stock_overview_uses_shared_summary_policy() -> None:
    uow = FakeUnitOfWork()
    product = _add_product(uow, "Buzdolabı", physical_stock=2)

    rows, total = get_stock_overview(uow, open_reservations={product.id: 5})

    assert total == 1
    assert len(rows) == 1
    assert rows[0].summary.physical == 2
    assert rows[0].summary.open_reservation == 5


def test_stock_overview_can_filter_in_stock_only() -> None:
    uow = FakeUnitOfWork()
    _add_product(uow, "Buzdolabı", physical_stock=2)
    _add_product(uow, "Fırın", physical_stock=0)
    _add_product(uow, "Çamaşır", physical_stock=-1)

    rows, total = get_stock_overview(uow, only_in_stock=True)

    assert total == 1
    assert [row.product.name for row in rows] == ["Buzdolabı"]


def test_open_session_snapshots_category_products_and_version() -> None:
    uow = FakeUnitOfWork()
    category = ProductCategory(id=uuid.uuid4(), name="Beyaz Eşya")
    uow.products.add_category(category)
    product = _add_product(
        uow, "Buzdolabı", physical_stock=5, category_id=category.id
    )
    _add_product(uow, "Fırın", physical_stock=3, category_id=category.id)
    _add_product(uow, "Diğer", physical_stock=9)
    _add_movement(uow, product, -1)

    view = open_stock_count_session(
        uow,
        category_id=category.id,
        actor=ActorContext(worker_name="Ayşe"),
    )

    assert view.status == "open"
    assert view.mode == "category"
    assert view.category_name == "Beyaz Eşya"
    assert view.stock_version == 1
    assert {item.product_name for item in view.items} == {"Buzdolabı", "Fırın"}
    snapshot = {item.product_name: item.system_quantity for item in view.items}
    assert snapshot == {"Buzdolabı": 4, "Fırın": 3}
    assert uow.committed


def test_quick_session_starts_empty_and_adds_only_requested_products() -> None:
    uow = FakeUnitOfWork()
    product = _add_product(uow, "Buzdolabı", physical_stock=5)

    session = open_stock_count_session(uow, category_id=None, mode="quick")
    assert session.mode == "quick"
    assert session.items == ()

    view = add_stock_count_line(uow, session.id, product.id)

    assert len(view.items) == 1
    assert view.items[0].product_name == "Buzdolabı"
    assert view.items[0].system_quantity == 5
    assert view.items[0].counted_quantity is None

    duplicate = add_stock_count_line(uow, session.id, product.id)
    assert len(duplicate.items) == 1


def test_quick_session_rejects_archived_and_wrong_category_products() -> None:
    uow = FakeUnitOfWork()
    category = ProductCategory(id=uuid.uuid4(), name="Beyaz Eşya")
    other = ProductCategory(id=uuid.uuid4(), name="Küçük Ev Aletleri")
    uow.products.add_category(category)
    uow.products.add_category(other)
    archived = _add_product(
        uow, "Arşiv", physical_stock=1, category_id=category.id
    )
    archived.is_archived = True
    wrong = _add_product(uow, "Yanlış", physical_stock=1, category_id=other.id)
    session = open_stock_count_session(uow, category_id=category.id, mode="quick")

    with pytest.raises(ValidationError, match="Arşiv"):
        add_stock_count_line(uow, session.id, archived.id)
    with pytest.raises(ValidationError, match="kategorisinde"):
        add_stock_count_line(uow, session.id, wrong.id)


def test_draft_save_does_not_change_stock() -> None:
    uow = FakeUnitOfWork()
    product = _add_product(uow, "Buzdolabı", physical_stock=5)
    session = open_stock_count_session(uow, category_id=None)

    view = save_counted_quantities(uow, session.id, {product.id: 3})

    assert view.status == "open"
    assert view.items[0].counted_quantity == 3
    assert view.items[0].difference == -2
    assert view.difference_lines == 1
    assert view.total_difference == -2
    assert product.physical_stock == 5
    assert uow.products.get_stock_movements(product.id) == []


def test_save_and_complete_applies_positive_counts_and_skips_uncounted() -> None:
    uow = FakeUnitOfWork()
    counted_product = _add_product(uow, "Buzdolabı", physical_stock=5)
    skipped_product = _add_product(uow, "Fırın", physical_stock=8)
    session = open_stock_count_session(
        uow, category_id=None, actor=ActorContext(worker_name="Ayşe")
    )

    result = save_and_complete_stock_count(
        uow,
        session.id,
        {counted_product.id: 3},
        actor=ActorContext(worker_name="Ayşe"),
    )

    assert result.counted_count == 1
    assert result.skipped_count == 1
    assert result.adjusted_count == 1
    assert result.total_difference == -2
    assert counted_product.physical_stock == 3
    assert skipped_product.physical_stock == 8
    movements = uow.products.get_stock_movements(counted_product.id)
    assert len(movements) == 1
    assert movements[0].movement_type == "stock_count_adjustment"
    assert movements[0].quantity_before == 5
    assert movements[0].quantity_after == 3

    view = get_stock_count_session(uow, session.id)
    assert view is not None
    assert view.status == "completed"
    assert view.counted_lines == 1
    assert view.skipped_lines == 1
    assert view.summary["adjusted_count"] == 1


def test_save_preserves_counts_saved_on_other_pages() -> None:
    uow = FakeUnitOfWork()
    first = _add_product(uow, "Buzdolabı", physical_stock=5)
    second = _add_product(uow, "Fırın", physical_stock=8)
    session = open_stock_count_session(uow, category_id=None)
    save_counted_quantities(uow, session.id, {second.id: 6})

    result = save_and_complete_stock_count(
        uow, session.id, {first.id: 3}
    )

    assert result.counted_count == 2
    assert first.physical_stock == 3
    assert second.physical_stock == 6
    movements = uow.products.get_stock_movements(second.id)
    assert len(movements) == 1
    assert movements[0].quantity_after == 6


def test_zero_and_blank_counts_leave_stock_unchanged() -> None:
    uow = FakeUnitOfWork()
    product = _add_product(uow, "Buzdolabı", physical_stock=5)
    session = open_stock_count_session(uow, category_id=None)

    result = save_and_complete_stock_count(
        uow, session.id, {product.id: 0}
    )

    assert result.counted_count == 0
    assert result.skipped_count == 1
    assert result.adjusted_count == 0
    assert product.physical_stock == 5
    assert uow.products.get_stock_movements(product.id) == []


def test_stale_stock_is_rejected_and_can_be_refreshed() -> None:
    uow = FakeUnitOfWork()
    product = _add_product(uow, "Buzdolabı", physical_stock=5)
    session = open_stock_count_session(uow, category_id=None)
    save_counted_quantities(uow, session.id, {product.id: 3})
    _add_movement(uow, product, -1)

    with pytest.raises(ConflictError, match="stok değişti"):
        complete_stock_count_session(uow, session.id)

    refreshed = refresh_stock_count_session(uow, session.id)
    assert refreshed.stock_version == 1
    assert refreshed.items[0].system_quantity == 4
    assert refreshed.items[0].difference == -1

    result = complete_stock_count_session(uow, session.id)
    assert result.total_difference == -1
    assert product.physical_stock == 3


def test_complete_is_idempotent() -> None:
    uow = FakeUnitOfWork()
    product = _add_product(uow, "Buzdolabı", physical_stock=5)
    session = open_stock_count_session(uow, category_id=None)
    first = save_and_complete_stock_count(uow, session.id, {product.id: 3})

    second = save_and_complete_stock_count(uow, session.id, {product.id: 1})

    assert second == first
    assert product.physical_stock == 3
    assert len(uow.products.get_stock_movements(product.id)) == 1


def test_cancelling_open_session_does_not_touch_stock() -> None:
    uow = FakeUnitOfWork()
    product = _add_product(uow, "Buzdolabı", physical_stock=5)
    session = open_stock_count_session(uow, category_id=None)
    save_counted_quantities(uow, session.id, {product.id: 3})

    view = cancel_stock_count_session(
        uow, session.id, actor=ActorContext(worker_name="Ayşe"), reason="Yanlış sayım"
    )

    assert view.status == "cancelled"
    assert view.cancel_reason == "Yanlış sayım"
    assert product.physical_stock == 5
    assert uow.products.get_stock_movements(product.id) == []


def test_cancelling_completed_session_reverses_stock() -> None:
    uow = FakeUnitOfWork()
    product = _add_product(uow, "Buzdolabı", physical_stock=5)
    session = open_stock_count_session(uow, category_id=None)
    save_and_complete_stock_count(uow, session.id, {product.id: 3})
    assert product.physical_stock == 3

    view = cancel_stock_count_session(
        uow, session.id, actor=ActorContext(worker_name="Mehmet"), reason="Yanlış"
    )

    assert view.status == "cancelled"
    assert view.reversed_at is not None
    assert product.physical_stock == 5
    movements = uow.products.get_stock_movements(product.id)
    assert [movement.movement_type for movement in movements] == [
        "stock_count_adjustment",
        "reversal",
    ]
    assert movements[1].quantity_delta == 2
    assert movements[1].quantity_after == 5


def test_cancelling_completed_session_refuses_if_stock_changed_after_count() -> None:
    uow = FakeUnitOfWork()
    product = _add_product(uow, "Buzdolabı", physical_stock=5)
    session = open_stock_count_session(uow, category_id=None)
    save_and_complete_stock_count(uow, session.id, {product.id: 3})
    _add_movement(uow, product, 1)

    with pytest.raises(ConflictError, match="stok değişti"):
        cancel_stock_count_session(uow, session.id)

    assert product.physical_stock == 4
    assert get_stock_count_session(uow, session.id).status == "completed"


def test_quick_refresh_only_keeps_added_products() -> None:
    uow = FakeUnitOfWork()
    category = ProductCategory(id=uuid.uuid4(), name="Beyaz Eşya")
    uow.products.add_category(category)
    product = _add_product(
        uow, "Buzdolabı", physical_stock=5, category_id=category.id
    )
    _add_product(uow, "Fırın", physical_stock=3, category_id=category.id)
    session = open_stock_count_session(uow, category_id=category.id, mode="quick")
    add_stock_count_line(uow, session.id, product.id)
    product.physical_stock = 7

    view = refresh_stock_count_session(uow, session.id)

    assert [item.product_name for item in view.items] == ["Buzdolabı"]
    assert view.items[0].system_quantity == 7


def test_completed_session_cannot_be_refreshed() -> None:
    uow = FakeUnitOfWork()
    product = _add_product(uow, "Buzdolabı", physical_stock=5)
    session = open_stock_count_session(uow, category_id=None)
    save_and_complete_stock_count(uow, session.id, {product.id: 5})

    with pytest.raises(ValidationError, match="Tamamlanmış"):
        refresh_stock_count_session(uow, session.id)


def test_create_product_category_rejects_duplicate_names() -> None:
    uow = FakeUnitOfWork()

    category = create_product_category(uow, "Beyaz Eşya")
    assert category.name == "Beyaz Eşya"

    with pytest.raises(ValidationError, match="zaten mevcut"):
        create_product_category(uow, "Beyaz Eşya")
