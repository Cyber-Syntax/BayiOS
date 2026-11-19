from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from bayios.adapters.db.models.products import Product
from bayios.bootstrap import ApplicationSettings
from bayios.main import create_app
from bayios.web.deps import get_unit_of_work
from tests.fakes import FakeUnitOfWork


def _seed_pos_commission(fake_uow: FakeUnitOfWork) -> None:
    from datetime import UTC, datetime

    from bayios.adapters.db.models.commissions import (
        Bank,
        CommissionPeriod,
        CommissionRate,
    )

    period = CommissionPeriod(
        id=uuid.uuid4(),
        period_key="2026-11",
        valid_from=datetime(2026, 11, 1, tzinfo=UTC),
        valid_until=datetime(2026, 11, 30, 23, 59, tzinfo=UTC),
        status="active",
    )
    fake_uow.commissions.add_period(period)
    fake_uow.commissions.add_bank(
        Bank(
            id=uuid.uuid4(),
            name="Akbank",
            name_normalized="akbank",
            is_active=True,
        )
    )
    for installment in range(1, 7):
        fake_uow.commissions.add_rate(
            CommissionRate(
                id=uuid.uuid4(),
                period_id=period.id,
                channel="pos",
                bank_id=None,
                product_group="other",
                amount_tier=None,
                installment_count=installment,
                commission_percent=Decimal("2.00"),
                scope_key=f"pos||other|-|{installment}",
            )
        )


def test_offer_comparison_includes_cash_and_banks(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    _seed_pos_commission(fake_uow)
    product = next(iter(fake_uow.products.get_all()))

    response = client.post(
        "/offers/compare",
        data={
            "payment_type": "card",
            "dealer_discount_percent": "10",
            "dealer_discount_cash_percent": "20",
            "channel": "pos",
            "installment_count": "1",
            "card_type": "consumer",
            "product_id": str(product.id),
            "quantity": "1",
            "campaign_id": "",
            "gift_present": "",
            "unit_price_cash": "",
            "unit_price_card": "",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Taksit Seçenekleri" in response.text
    assert "Nakit" in response.text
    assert "Genel (tüm bankalar)" in response.text
    assert "Akbank" in response.text
    assert "36.800,00 TL" in response.text


def test_cash_and_card_discounts_are_independent(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))
    response = client.post(
        "/offers",
        data={
            "customer_name": "Nakit Müşteri",
            "payment_type": "cash",
            "dealer_discount_percent": "10",
            "dealer_discount_cash_percent": "20",
            "product_id": str(product.id),
            "quantity": "1",
            "campaign_id": "",
            "gift_present": "",
            "unit_price_cash": "",
            "unit_price_card": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = client.get(response.headers["location"])
    assert "36.800,00 TL" in detail.text
    assert "Nakit İndirimi" in detail.text


def test_delete_offer_from_detail(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))
    created = client.post(
        "/offers",
        data={
            "customer_name": "Silinecek",
            "payment_type": "cash",
            "dealer_discount_percent": "10",
            "dealer_discount_cash_percent": "10",
            "product_id": str(product.id),
            "quantity": "1",
            "campaign_id": "",
            "gift_present": "",
            "unit_price_cash": "",
            "unit_price_card": "",
        },
        follow_redirects=False,
    )
    offer_id = created.headers["location"].split("?")[0].rsplit("/", 1)[-1]
    deleted = client.post(
        f"/offers/{offer_id}/delete",
        data={"confirm": "1"},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert deleted.headers["location"].startswith("/offers")
    assert client.get(f"/offers/{offer_id}").status_code == 404



@pytest.fixture
def fake_uow() -> FakeUnitOfWork:
    uow = FakeUnitOfWork()
    product = Product(
        id=uuid.uuid4(),
        name="Buzdolabı",
        name_normalized="buzdolabı",
        regular_price=Decimal("50000.00"),
        website_discounted_price=Decimal("46000.00"),
        cost_price=Decimal("36000.00"),
        physical_stock=1,
    )
    uow.products.add(product)
    return uow


@pytest.fixture
def client(fake_uow: FakeUnitOfWork) -> TestClient:
    settings = ApplicationSettings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/bayios"
    )
    app = create_app(settings)
    app.dependency_overrides[get_unit_of_work] = lambda: fake_uow
    return TestClient(app)


def test_offers_list_and_form_render(client: TestClient) -> None:
    listing = client.get("/offers")
    form = client.get("/offers/new")

    assert listing.status_code == 200
    assert "Teklifler" in listing.text
    assert "Teklifler (yakında)" not in listing.text
    assert form.status_code == 200
    assert "Yeni Teklif" in form.text
    assert "Bayi İndirimi" in form.text
    assert "Otomatik (ürünün aktif kampanyası)" in form.text


def test_offers_htmx_search_returns_partial(client: TestClient) -> None:
    response = client.get(
        "/offers?q=Ayşe", headers={"HX-Request": "true"}
    )

    assert response.status_code == 200
    assert "<!doctype html>" not in response.text
    assert "Teklif bulunmuyor." in response.text


def test_create_cash_offer_from_ui(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))

    response = client.post(
        "/offers",
        data={
            "customer_name": "Ayşe Yılmaz",
            "customer_phone": "555",
            "payment_type": "cash",
            "dealer_discount_percent": "10",
            "product_id": str(product.id),
            "quantity": "1",
            "campaign_id": "",
            "gift_present": "",
            "unit_price_cash": "",
            "unit_price_card": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    location = response.headers["location"]
    detail = client.get(location)
    assert detail.status_code == 200
    assert "Ayşe Yılmaz" in detail.text
    assert "41.400,00 TL" in detail.text
    assert "Taslak" in detail.text

    printed = client.get(f"{location.split('?')[0]}/print")
    assert printed.status_code == 200
    assert "Müşteri Teklifi" in printed.text


def test_offer_detail_quick_reserve_and_sell_buttons(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))
    created = client.post(
        "/offers",
        data={
            "customer_name": "Ayşe Yılmaz",
            "customer_phone": "555",
            "payment_type": "cash",
            "dealer_discount_percent": "10",
            "product_id": str(product.id),
            "quantity": "1",
            "campaign_id": "",
            "gift_present": "",
            "unit_price_cash": "",
            "unit_price_card": "",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    offer_id = created.headers["location"].split("?")[0].rsplit("/", 1)[-1]

    detail = client.get(f"/offers/{offer_id}")
    assert "Rezervasyon Aç" in detail.text
    assert "Teslim Et (Hızlı Sat)" in detail.text

    reserved = client.post(
        f"/offers/{offer_id}/reserve", follow_redirects=False
    )
    assert reserved.status_code == 303
    assert "msg=reserved" in reserved.headers["location"]
    assert product.physical_stock == 1

    sold = client.post(
        f"/offers/{offer_id}/sell",
        data={"low_stock_reason": ""},
        follow_redirects=False,
    )
    assert sold.status_code == 303
    assert "msg=sold" in sold.headers["location"]
    assert product.physical_stock == 0

    detail = client.get(f"/offers/{offer_id}")
    assert "Rezervasyonu Gör" in detail.text
