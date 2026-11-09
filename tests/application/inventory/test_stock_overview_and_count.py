from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from bayios.adapters.db.models.inventory import StockMovement
from bayios.adapters.db.models.products import Product, ProductCategory
from bayios.application.errors import ConflictError, ValidationError
from bayios.application.inventory import (
    complete_stock_count_session,
    create_product_category,
    get_stock_count_session,
    get_stock_overview,
    open_stock_count_session,
    refresh_stock_count_session,
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

    rows = get_stock_overview(uow, open_reservations={product.id: 5})

    assert len(rows) == 1
    assert rows[0].summary.physical == 2
    assert rows[0].summary.open_reservation == 5
    assert rows[0].summary.sellable == 0
    assert rows[0].summary.supply_need == 3


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
    assert view.category_name == "Beyaz Eşya"
    assert view.stock_version == 1
    assert {item.product_name for item in view.items} == {"Buzdolabı", "Fırın"}
    snapshot = {item.product_name: item.system_quantity for item in view.items}
    assert snapshot == {"Buzdolabı": 4, "Fırın": 3}
    assert uow.committed


def test_save_counted_quantities_enters_review_with_differences() -> None:
    uow = FakeUnitOfWork()
    product = _add_product(uow, "Buzdolabı", physical_stock=5)
    session = open_stock_count_session(uow, category_id=None)

    view = save_counted_quantities(uow, session.id, {product.id: 3})

    assert view.status == "review"
    assert view.items[0].counted_quantity == 3
    assert view.items[0].difference == -2
    assert view.difference_lines == 1
    assert view.total_difference == -2


def test_completion_requires_difference_acknowledgement() -> None:
    uow = FakeUnitOfWork()
    product = _add_product(uow, "Buzdolabı", physical_stock=5)
    session = open_stock_count_session(uow, category_id=None)
    save_counted_quantities(uow, session.id, {product.id: 3})

    with pytest.raises(ValidationError, match="difference"):
        complete_stock_count_session(uow, session.id)

    assert product.physical_stock == 5
    assert uow.products.get_stock_movements(product.id) == []


def test_complete_applies_adjustment_once_and_is_idempotent() -> None:
    uow = FakeUnitOfWork()
    product = _add_product(uow, "Buzdolabı", physical_stock=5)
    session = open_stock_count_session(
        uow, category_id=None, actor=ActorContext(worker_name="Ayşe")
    )
    save_counted_quantities(uow, session.id, {product.id: 3})

    result = complete_stock_count_session(
        uow, session.id, actor=ActorContext(worker_name="Ayşe"), acknowledge_differences=True
    )

    assert result.adjusted_count == 1
    assert result.unchanged_count == 0
    assert result.total_difference == -2
    assert product.physical_stock == 3
    movements = uow.products.get_stock_movements(product.id)
    assert len(movements) == 1
    assert movements[0].movement_type == "stock_count_adjustment"
    assert movements[0].quantity_before == 5
    assert movements[0].quantity_after == 3

    retry = complete_stock_count_session(
        uow, session.id, actor=ActorContext(worker_name="Ayşe"), acknowledge_differences=True
    )

    assert retry == result
    assert len(uow.products.get_stock_movements(product.id)) == 1
    completed = get_stock_count_session(uow, session.id)
    assert completed is not None
    assert completed.status == "completed"
    assert completed.completed_by_name == "Ayşe"


def test_stale_stock_version_is_rejected_and_can_be_refreshed() -> None:
    uow = FakeUnitOfWork()
    product = _add_product(uow, "Buzdolabı", physical_stock=5)
    session = open_stock_count_session(uow, category_id=None)
    save_counted_quantities(uow, session.id, {product.id: 3})
    _add_movement(uow, product, -1)

    with pytest.raises(ConflictError, match="stok değişti"):
        complete_stock_count_session(uow, session.id, acknowledge_differences=True)

    refreshed = refresh_stock_count_session(uow, session.id)
    assert refreshed.stock_version == 1
    assert refreshed.items[0].system_quantity == 4
    assert refreshed.items[0].difference == -1

    result = complete_stock_count_session(
        uow, session.id, acknowledge_differences=True
    )
    assert result.total_difference == -1
    assert product.physical_stock == 3


def test_completed_session_cannot_be_refreshed() -> None:
    uow = FakeUnitOfWork()
    product = _add_product(uow, "Buzdolabı", physical_stock=5)
    session = open_stock_count_session(uow, category_id=None)
    save_counted_quantities(uow, session.id, {product.id: 5})
    complete_stock_count_session(uow, session.id)

    with pytest.raises(ValidationError, match="Tamamlanmış"):
        refresh_stock_count_session(uow, session.id)


def test_create_product_category_rejects_duplicate_names() -> None:
    uow = FakeUnitOfWork()

    category = create_product_category(uow, "Beyaz Eşya")
    assert category.name == "Beyaz Eşya"

    with pytest.raises(ValidationError, match="zaten mevcut"):
        create_product_category(uow, "Beyaz Eşya")
