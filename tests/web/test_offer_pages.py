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
