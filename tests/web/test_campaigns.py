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
        regular_price=Decimal("25999.00"),
        website_discounted_price=Decimal("23999.00"),
        physical_stock=5,
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


def _product(fake_uow: FakeUnitOfWork) -> Product:
    return next(iter(fake_uow.products.get_all()))


def _campaign_data(
    product_id: uuid.UUID, **overrides: str
) -> dict[str, str]:
    data = {
        "name": "Hediye Kampanyası",
        "campaign_type": "gift",
        "starts_at": "2026-01-01",
        "ends_at": "2027-12-31",
        "base_price_type": "regular",
        "discount_type": "gift",
        "gift_description": "Buzdolabı hediye",
        "gift_optional": "1",
        "gift_yes_base_price_type": "regular",
        "gift_no_base_price_type": "website_discounted",
        "product_id": str(product_id),
        "relation_type": "benefit",
        "quantity_required": "",
    }
    data.update(overrides)
    return data


def _create_campaign(
    client: TestClient, fake_uow: FakeUnitOfWork, **overrides: str
) -> str:
    product = _product(fake_uow)
    response = client.post(
        "/campaigns",
        data=_campaign_data(product.id, **overrides),
        follow_redirects=False,
    )
    assert response.status_code == 303
    return response.headers["location"].split("?")[0]


def test_new_and_edit_forms_and_picker_render(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    new_form = client.get("/campaigns/new")
    picker = client.get("/campaigns/picker?q=Buz")
    location = _create_campaign(client, fake_uow)
    edit_form = client.get(f"{location}/edit")

    assert new_form.status_code == 200
    assert "Yeni Kampanya" in new_form.text
    assert "Kampanya Adı" in new_form.text
    assert "Buzdolabı" in new_form.text
    assert picker.status_code == 200
    assert "Buzdolabı" in picker.text
    assert "addProduct" in picker.text
    assert edit_form.status_code == 200
    assert "Kampanya Düzenle" in edit_form.text
    assert "Hediye Kampanyası" in edit_form.text
    assert "Buzdolabı" in edit_form.text


def test_campaign_list_renders_with_enabled_nav(client: TestClient) -> None:
    response = client.get("/campaigns")

    assert response.status_code == 200
    assert "Kampanyalar" in response.text
    assert 'href="/campaigns/new"' in response.text
    assert "Bayi İndirimi Varsayılanı" in response.text
    assert "Kampanyalar (yakında)" not in response.text
    assert "Bu filtreye uyan kampanya bulunmuyor." in response.text


def test_create_campaign_from_ui_shows_gift_scenarios(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    location = _create_campaign(client, fake_uow)

    page = client.get(location)

    assert page.status_code == 200
    assert "Hediye Kampanyası" in page.text
    assert "23.399,10 TL" in page.text
    assert "21.599,10 TL" in page.text
    assert "v1" in page.text


def test_edit_without_change_keeps_one_version_and_change_creates_v2(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    location = _create_campaign(client, fake_uow)
    product = _product(fake_uow)

    unchanged = client.post(
        f"{location}/edit",
        data=_campaign_data(product.id),
        follow_redirects=False,
    )
    assert unchanged.status_code == 303
    detail = client.get(location)
    assert "Sürüm v1" in detail.text
    assert "Sürüm v2" not in detail.text

    changed = client.post(
        f"{location}/edit",
        data=_campaign_data(product.id, name="Yeni Ad"),
        follow_redirects=False,
    )
    assert changed.status_code == 303
    detail = client.get(location)
    assert "Yeni Ad" in detail.text
    assert "Sürüm v2" in detail.text


def test_archive_hides_campaign_from_active_list(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    location = _create_campaign(client, fake_uow)

    response = client.post(f"{location}/archive", follow_redirects=False)
    assert response.status_code == 303

    detail = client.get(location)
    assert "Arşivde" in detail.text
    listing = client.get("/campaigns")
    assert "Bu filtreye uyan kampanya bulunmuyor." in listing.text


def test_campaign_filters_by_type(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    _create_campaign(client, fake_uow)
    _create_campaign(
        client,
        fake_uow,
        name="Kış İndirimi",
        campaign_type="product_discount",
        discount_type="percent",
        discount_value="10",
        gift_description="",
        gift_optional="",
        gift_yes_base_price_type="",
        gift_no_base_price_type="",
    )

    response = client.get("/campaigns?campaign_type=product_discount")

    assert response.status_code == 200
    assert "Kış İndirimi" in response.text
    assert "Hediye Kampanyası" not in response.text


def test_scenario_panel_accepts_dealer_percent_override(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    location = _create_campaign(client, fake_uow)

    response = client.get(f"{location}/scenario?dealer_percent=15")

    assert response.status_code == 200
    assert "22.099,15 TL" in response.text
    assert "20.399,15 TL" in response.text


def test_htmx_campaign_search_returns_partial(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    _create_campaign(client, fake_uow)

    response = client.get("/campaigns?q=Hediye", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "Hediye Kampanyası" in response.text
    assert "<!doctype html>" not in response.text


def test_invalid_campaign_shows_form_error(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = _product(fake_uow)

    response = client.post(
        "/campaigns",
        data=_campaign_data(product.id, name=""),
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Kaydedilemedi" in response.text


def test_product_detail_shows_active_campaigns_and_dealer_pricing(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    _create_campaign(client, fake_uow)
    product = _product(fake_uow)

    response = client.get(f"/products/{product.id}")

    assert response.status_code == 200
    assert "Aktif Kampanyalar" in response.text
    assert "Hediye Kampanyası" in response.text
    assert "Bayi Fiyatı" in response.text
    assert "Fiyatları Güncelle" in response.text


def test_dealer_pricing_update_saves_values_and_history(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = _product(fake_uow)

    response = client.post(
        f"/products/{product.id}/dealer-pricing",
        data={
            "cash_floor_price": "22000",
            "card_floor_price": "22500",
            "note": "Kasım fiyatı",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    page = client.get(f"/products/{product.id}")
    assert "22.000,00 TL" in page.text
    assert "22.500,00 TL" in page.text
    assert "Kasım fiyatı" in page.text
    assert "Fiyat Geçmişi" in page.text


def test_dealer_discount_update_and_history(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    response = client.post(
        "/campaigns/dealer-discount",
        data={"default_percent": "15", "note": "Patron yönlendirmesi"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    page = client.get("/campaigns")
    assert "15,00 %" in page.text
    assert "Değişiklik Geçmişi" in page.text
    assert "Patron yönlendirmesi" in page.text


def test_campaign_print_pages_render(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    location = _create_campaign(client, fake_uow)

    listing = client.get("/campaigns/print")
    detail = client.get(f"{location}/print")

    assert listing.status_code == 200
    assert "BayiOS Kampanya Rehberi" in listing.text
    assert detail.status_code == 200
    assert "A4 Kampanya Rehberi" in detail.text
    assert "23.399,10 TL" in detail.text
