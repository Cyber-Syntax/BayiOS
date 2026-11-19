from __future__ import annotations

import uuid
from datetime import UTC, datetime

from bayios.adapters.db.models.commissions import (
    Bank,
    CommissionLimit,
    CommissionPeriod,
    CommissionRate,
)
from bayios.adapters.db.models.offers import Offer
from bayios.adapters.db.models.products import Product, ProductCategory
from bayios.application.settings import merge_banks, merge_categories
from tests.fakes import FakeUnitOfWork


def test_merge_banks_repoints_rates_limits_and_offers() -> None:
    uow = FakeUnitOfWork()
    source = Bank(id=uuid.uuid4(), name="Akbannk", name_normalized="akbannk")
    target = Bank(id=uuid.uuid4(), name="Akbank", name_normalized="akbank")
    uow.commissions.add_bank(source)
    uow.commissions.add_bank(target)
    period = CommissionPeriod(
        id=uuid.uuid4(),
        period_key="2026-11",
        valid_from=datetime(2026, 11, 1, tzinfo=UTC),
        valid_until=datetime(2026, 11, 30, tzinfo=UTC),
        status="active",
    )
    uow.commissions.add_period(period)
    uow.commissions.add_rate(
        CommissionRate(
            id=uuid.uuid4(),
            period_id=period.id,
            channel="pos",
            bank_id=source.id,
            product_group="other",
            installment_count=2,
            commission_percent=4,
            scope_key=f"pos|{source.id}|other|-|2",
        )
    )
    uow.commissions.add_limit(
        CommissionLimit(
            id=uuid.uuid4(),
            period_id=period.id,
            channel="pos",
            bank_id=source.id,
            product_group=None,
            category_id=None,
            card_type=None,
            max_installments=5,
            scope_key=f"pos|{source.id}|-|-|-",
        )
    )
    offer = Offer(id=uuid.uuid4(), bank_id=source.id, payment_type="cash")
    uow.offers.add(offer)

    merge_banks(uow, source.id, target.id)

    assert source.id not in uow.commissions.banks
    rate = uow.commissions.rates[period.id][0]
    assert rate.bank_id == target.id
    assert str(target.id) in rate.scope_key
    limit = uow.commissions.limits[period.id][0]
    assert limit.bank_id == target.id
    assert str(target.id) in limit.scope_key
    assert offer.bank_id == target.id


def test_merge_categories_repoints_products_and_limits() -> None:
    uow = FakeUnitOfWork()
    source = ProductCategory(
        id=uuid.uuid4(),
        name="Televizyon",
        name_normalized="televizyon",
        commission_group="other",
    )
    target = ProductCategory(
        id=uuid.uuid4(),
        name="TV",
        name_normalized="tv",
        commission_group="other",
    )
    uow.products.add_category(source)
    uow.products.add_category(target)
    product = Product(
        id=uuid.uuid4(),
        name="TV 55",
        name_normalized="tv 55",
        category_id=source.id,
        physical_stock=1,
    )
    uow.products.add(product)
    period = CommissionPeriod(
        id=uuid.uuid4(),
        period_key="2026-11",
        valid_from=datetime(2026, 11, 1, tzinfo=UTC),
        valid_until=datetime(2026, 11, 30, tzinfo=UTC),
        status="active",
    )
    uow.commissions.add_period(period)
    uow.commissions.add_limit(
        CommissionLimit(
            id=uuid.uuid4(),
            period_id=period.id,
            channel=None,
            bank_id=None,
            product_group=None,
            category_id=source.id,
            card_type=None,
            max_installments=4,
            scope_key=f"-|-|-|{source.id}|-",
        )
    )

    merge_categories(uow, source.id, target.id)

    assert source.id not in uow.products.categories
    assert product.category_id == target.id
    limit = uow.commissions.limits[period.id][0]
    assert limit.category_id == target.id
    assert str(target.id) in limit.scope_key
