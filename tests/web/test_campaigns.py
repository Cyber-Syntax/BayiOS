from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from bayios.adapters.db.models.products import Product, ProductCategory
from bayios.application.campaigns import (
    CampaignInput,
    CampaignProductInput,
    create_campaign,
)
from bayios.bootstrap import ApplicationSettings
from bayios.domain.campaigns import CampaignType, DiscountType, ProductRelationType
from bayios.main import create_app
from bayios.web.deps import get_unit_of_work
from tests.fakes import FakeUnitOfWork


def test_campaign_accepts_more_than_one_thousand_form_fields(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    products: list[Product] = []
    for index in range(340):
        product = Product(
            id=uuid.uuid4(),
            name=f"Ürün {index:03d}",
            name_normalized=f"urun {index:03d}",
            regular_price=Decimal("1000.00"),
            physical_stock=1,
        )
        fake_uow.products.add(product)
        products.append(product)

    data: list[tuple[str, str]] = [
        ("name", "Büyük Yüzde Kampanyası"),
        ("campaign_type", "product_discount"),
        ("starts_at", "2026-01-01"),
        ("ends_at", "2027-12-31"),
        ("base_price_type", "regular"),
        ("discount_type", "percent"),
        ("discount_value", "10"),
    ]
    for product in products:
        data.extend(
            [
                ("product_id", str(product.id)),
                ("relation_type", "benefit"),
                ("quantity_required", ""),
            ]
        )

    from urllib.parse import urlencode

    response = client.post(
        "/campaigns",
        content=urlencode(data),
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/campaigns/")



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


def test_campaign_form_accepts_category_benefit_rule(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    category = ProductCategory(
        id=uuid.uuid4(),
        name="Kurutma Makinesi",
        name_normalized="kurutma makinesi",
        commission_group="other",
    )
    fake_uow.products.add_category(category)
    product = _product(fake_uow)

    response = client.post(
        "/campaigns",
        data={
            "name": "Kategori Hedefli",
            "campaign_type": "bundle",
            "starts_at": "2026-01-01",
            "ends_at": "2027-12-31",
            "base_price_type": "regular",
            "discount_type": "fixed_amount",
            "discount_value": "17850",
            "combines_with_others": "0",
            "min_basket_total": "100000",
            "product_id": str(product.id),
            "relation_type": "qualifying",
            "quantity_required": "",
            "product_discount_type": "",
            "product_discount_value": "",
            "product_base_price_type": "",
            "product_applies_per_unit": "1",
            "category_id": str(category.id),
            "category_relation_type": "benefit",
            "category_discount_type": "fixed_amount",
            "category_discount_value": "17850",
            "category_base_price_type": "regular",
            "category_applies_per_unit": "0",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    campaign_id = uuid.UUID(
        response.headers["location"].rsplit("/", 1)[-1].split("?", 1)[0]
    )
    campaign = fake_uow.campaigns.get(campaign_id)
    version = fake_uow.campaigns.get_current_version(campaign_id)
    assert campaign is not None
    assert version is not None
    assert version.combines_with_others is False
    assert version.min_basket_total == Decimal("100000.00")
    links = fake_uow.campaigns.get_version_products(version.id)
    category_links = [link for link in links if link.category_id == category.id]
    assert len(category_links) == 1
    assert category_links[0].discount_type == "fixed_amount"
    assert category_links[0].discount_value == Decimal("17850.00")
    assert category_links[0].applies_per_unit is False


def test_campaign_form_accepts_payment_condition(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = _product(fake_uow)
    bank_id = uuid.uuid4()
    response = client.post(
        "/campaigns",
        data={
            "name": "Banka Koşullu",
            "campaign_type": "product_discount",
            "starts_at": "2026-01-01",
            "ends_at": "2027-12-31",
            "discount_type": "percent",
            "discount_value": "10",
            "payment_channel": "pos",
            "payment_bank_id": str(bank_id),
            "payment_card_type": "consumer",
            "payment_card_network": "World",
            "payment_installment_count": "8",
            "product_id": str(product.id),
            "relation_type": "benefit",
            "quantity_required": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    campaign_id = uuid.UUID(
        response.headers["location"].rsplit("/", 1)[-1].split("?", 1)[0]
    )
    version = fake_uow.campaigns.get_current_version(campaign_id)
    assert version is not None
    assert version.payment_conditions == [
        {
            "channel": "pos",
            "bank_ids": [str(bank_id)],
            "card_type": "consumer",
            "card_network": "World",
            "installment_count": 8,
        }
    ]
    detail = client.get(f"/campaigns/{campaign_id}")
    assert detail.status_code == 200
    assert "8 taksit" in detail.text
    assert "Bireysel" in detail.text
    assert "World" in detail.text


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


def test_invalid_gift_campaign_shows_turkish_errors(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = _product(fake_uow)

    value_response = client.post(
        "/campaigns",
        data=_campaign_data(product.id, discount_value="5"),
        follow_redirects=False,
    )
    assert value_response.status_code == 400
    assert "Hediye indirimi değer almaz." in value_response.text
    assert "does not take a value" not in value_response.text

    description_response = client.post(
        "/campaigns",
        data=_campaign_data(
            product.id, gift_description="", gift_optional=""
        ),
        follow_redirects=False,
    )
    assert description_response.status_code == 400
    assert (
        "Hediye kampanyalarında hediye açıklaması zorunludur."
        in description_response.text
    )


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


def test_campaign_json_preview_commit_and_conditions_panel(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = _product(fake_uow)
    payload = {
        "schema_version": "1.0",
        "scraped_at": "2026-11-22T14:26:27Z",
        "campaigns": [
            {
                "id": "json-web-kampanya",
                "name": "JSON Web Kampanyası",
                "category": "beyaz-esya-kampanyalari",
                "url": "https://example.test/json-web",
                "date_text": "1 Kasım - 30 Kasım 2026",
                "start_date": "2026-11-01",
                "end_date": "2026-11-30",
                "conditions": ["Koşul 1", "Koşul 2"],
                "product_count": 1,
                "products": [
                    {
                        "name": product.name,
                        "product_id": "9000",
                        "relationship": "İlgili ürün",
                        "required_quantity": None,
                    }
                ],
                "scraped_at": "2026-11-22T14:26:27Z",
            }
        ],
    }
    source = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    preview = client.post(
        "/imports/campaigns/preview",
        files={"file": ("kampanyalar.json", source, "application/json")},
    )

    assert preview.status_code == 200
    assert "Kampanya JSON İçe Aktarma Önizlemesi" in preview.text
    assert "JSON Web Kampanyası" in preview.text
    assert "Koşul" in preview.text

    commit = client.post(
        "/imports/campaigns/commit",
        data={
            "file_name": "kampanyalar.json",
            "file_type": "json",
            "source_b64": base64.b64encode(source).decode("ascii"),
            "decisions_json": "{}",
        },
        follow_redirects=False,
    )
    assert commit.status_code == 303

    campaign = next(iter(fake_uow.campaigns.campaigns.values()))
    page = client.get(f"/campaigns/{campaign.id}")
    assert page.status_code == 200
    assert "Koşullar" in page.text
    assert "Koşul 1" in page.text
    assert "<details" in page.text

    exported = client.get(f"/campaigns/{campaign.id}/export/json")
    assert exported.status_code == 200
    body = json.loads(exported.content)
    assert body["campaigns"][0]["id"] == "json-web-kampanya"
    assert body["campaigns"][0]["conditions"] == ["Koşul 1", "Koşul 2"]

    all_exported = client.get("/campaigns/export/json")
    assert all_exported.status_code == 200
    assert len(json.loads(all_exported.content)["campaigns"]) == 1

    upload = client.get("/imports/campaigns")
    assert upload.status_code == 200
    assert "Kampanya İçe Aktar (Excel/JSON)" in upload.text
    assert ".json" in upload.text


def test_campaign_list_paginates_without_missing_request_context(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = _product(fake_uow)
    now = datetime.now(UTC)
    for index in range(6):
        create_campaign(
            fake_uow,
            CampaignInput(
                name=f"Sayfalama Kampanyası {index}",
                campaign_type=CampaignType.GENERAL,
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=1),
                discount_type=DiscountType.INFO_ONLY,
                products=(
                    CampaignProductInput(
                        product_id=product.id,
                        relation_type=ProductRelationType.RELATED,
                    ),
                ),
            ),
        )

    response = client.get("/campaigns?limit=5&state=active")

    assert response.status_code == 200
    assert "Sayfalama Kampanyası" in response.text
    assert "Sonraki" in response.text
    assert "Sayfa" in response.text


def test_home_active_campaigns_kpi_shows_count(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    _create_campaign(client, fake_uow)

    response = client.get("/")

    assert response.status_code == 200
    assert "CampaignListItem" not in response.text
    assert '<div class="kpi-value">1</div>' in response.text

