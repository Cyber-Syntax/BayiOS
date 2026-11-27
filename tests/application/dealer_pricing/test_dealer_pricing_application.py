from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from bayios.adapters.db.models.products import Product
from bayios.application.dealer_pricing import (
    get_dealer_pricing,
    get_default_dealer_discount,
    update_dealer_pricing,
    update_default_dealer_discount,
)
from bayios.application.errors import NotFoundError, ValidationError
from tests.fakes import FakeUnitOfWork


def _product() -> Product:
    return Product(
        id=uuid.uuid4(),
        name="Buzdolabı",
        name_normalized="buzdolabı",
        regular_price=Decimal(25999),
        website_discounted_price=Decimal(23999),
        physical_stock=1,
    )


@pytest.fixture
def setup() -> tuple[FakeUnitOfWork, Product]:
    uow = FakeUnitOfWork()
    product = _product()
    uow.products.add(product)
    return uow, product


def test_missing_pricing_returns_empty_view(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup

    view = get_dealer_pricing(uow, product.id)

    assert view is not None
    assert view.cash_floor_price is None
    assert view.card_floor_price is None
    assert view.history == ()


def test_update_creates_current_pricing_and_first_history(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup

    view = update_dealer_pricing(
        uow,
        product.id,
        Decimal(22000),
        Decimal(22500),
        note="Kasım fiyatı",
    )

    assert view.cash_floor_price == Decimal(22000)
    assert view.card_floor_price == Decimal(22500)
    assert view.note == "Kasım fiyatı"
    assert len(view.history) == 1
    assert view.history[0].old_cash_floor is None
    assert view.history[0].new_cash_floor == Decimal(22000)
    assert view.history[0].old_card_floor is None
    assert view.history[0].new_card_floor == Decimal(22500)


def test_same_values_do_not_add_history(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup
    update_dealer_pricing(uow, product.id, Decimal(22000), Decimal(22500))

    view = update_dealer_pricing(
        uow,
        product.id,
        Decimal(22000),
        Decimal(22500),
        note="Sadece not değişti",
    )

    assert view.note == "Sadece not değişti"
    assert len(view.history) == 1


def test_changed_values_add_history_with_old_and_new(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup
    update_dealer_pricing(uow, product.id, Decimal(22000), Decimal(22500))

    view = update_dealer_pricing(
        uow, product.id, Decimal(21000), Decimal(21500)
    )

    assert len(view.history) == 2
    changes = {
        (
            row.old_cash_floor,
            row.new_cash_floor,
            row.old_card_floor,
            row.new_card_floor,
        )
        for row in view.history
    }
    assert (
        Decimal(22000),
        Decimal(21000),
        Decimal(22500),
        Decimal(21500),
    ) in changes


def test_negative_floor_and_missing_product_are_rejected(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup

    with pytest.raises(ValidationError, match="negatif"):
        update_dealer_pricing(uow, product.id, Decimal(-1), None)
    with pytest.raises(NotFoundError, match="Ürün bulunamadı"):
        update_dealer_pricing(uow, uuid.uuid4(), Decimal(1), None)


def test_default_discount_history_only_on_change(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, _ = setup

    initial = get_default_dealer_discount(uow)
    assert initial.default_percent == Decimal("10.00")
    assert initial.history == ()

    first = update_default_dealer_discount(uow, Decimal(15))
    assert first.default_percent == Decimal(15)
    assert len(first.history) == 1
    assert first.history[0].old_percent == Decimal("10.00")
    assert first.history[0].new_percent == Decimal(15)

    same = update_default_dealer_discount(uow, Decimal(15))
    assert len(same.history) == 1

    changed = update_default_dealer_discount(uow, Decimal(12))
    assert len(changed.history) == 2
    assert {
        (row.old_percent, row.new_percent) for row in changed.history
    } == {
        (Decimal("10.00"), Decimal(15)),
        (Decimal(15), Decimal(12)),
    }


def test_default_discount_rejects_out_of_range(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, _ = setup

    with pytest.raises(ValidationError, match="%0"):
        update_default_dealer_discount(uow, Decimal(101))


def test_floor_prices_and_default_discount_are_separate(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup

    update_dealer_pricing(uow, product.id, Decimal(22000), Decimal(22500))
    update_default_dealer_discount(uow, Decimal(15))

    pricing = get_dealer_pricing(uow, product.id)
    setting = get_default_dealer_discount(uow)

    assert pricing is not None
    assert pricing.cash_floor_price == Decimal(22000)
    assert setting.default_percent == Decimal(15)
