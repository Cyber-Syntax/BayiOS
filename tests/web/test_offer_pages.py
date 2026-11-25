from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from bayios.adapters.db.models.products import Product
from bayios.application.offers import (
    OfferInput,
    OfferItemInput,
    create_offer,
)
from bayios.application.offers.json_io import export_offers_json
from bayios.bootstrap import ApplicationSettings
from bayios.domain.offers import PaymentType
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
    assert "Otomatik (en yüksek indirim)" in form.text


def test_new_offer_prefills_product_from_deep_link(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))

    response = client.get(f"/offers/new?product_id={product.id}")

    assert response.status_code == 200
    assert product.name in response.text
    assert str(product.id) in response.text


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


def test_offer_form_has_live_comparison_and_basket_totals(
    client: TestClient,
) -> None:
    form = client.get("/offers/new")

    assert form.status_code == 200
    assert 'id="offer-comparison"' in form.text
    assert "hx-trigger=\"load delay:800ms, change from:#offer-form" in form.text
    assert 'id="basket-totals"' in form.text
    assert "Normal Toplam" in form.text
    assert "Kart Bayi İndirimi" in form.text


def test_offer_comparison_hides_oliz_when_product_has_none(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    from datetime import UTC, datetime, timedelta

    from bayios.application.campaigns import (
        CampaignInput,
        CampaignProductInput,
        create_campaign,
    )
    from bayios.domain.campaigns import (
        BasePriceType,
        CampaignType,
        DiscountType,
        ProductRelationType,
    )

    _seed_pos_commission(fake_uow)
    product = next(iter(fake_uow.products.get_all()))
    product.website_discounted_price = None
    now = datetime.now(UTC)
    create_campaign(
        fake_uow,
        CampaignInput(
            name="Düğün",
            campaign_type=CampaignType.PRODUCT_DISCOUNT,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=30),
            base_price_type=BasePriceType.REGULAR,
            discount_type=DiscountType.PERCENT,
            discount_value=Decimal(10),
            products=(
                CampaignProductInput(product.id, ProductRelationType.BENEFIT),
            ),
        ),
    )

    response = client.post(
        "/offers/compare",
        data={
            "payment_type": "card",
            "dealer_discount_percent": "10",
            "dealer_discount_cash_percent": "10",
            "channel": "pos",
            "installment_count": "1",
            "card_type": "consumer",
            "product_id": str(product.id),
            "quantity": "1",
            "campaign_id": "auto",
            "gift_present": "",
            "unit_price_cash": "",
            "unit_price_card": "",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Senaryo Özeti" in response.text
    assert "Kampanya + bayi" in response.text
    assert "Oliz" not in response.text


def test_offer_detail_hides_oliz_when_product_has_none(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))
    product.website_discounted_price = None
    created = client.post(
        "/offers",
        data={
            "customer_name": "İndirimsiz",
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
    detail = client.get(created.headers["location"])

    assert detail.status_code == 200
    assert "Oliz" not in detail.text
    assert "Normal Toplam" in detail.text


def test_offer_list_products_column_and_json_export(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))
    create_offer(
        fake_uow,
        OfferInput(
            customer_name="Liste Müşterisi",
            customer_phone=None,
            payment_type=PaymentType.CASH,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product.id, 2),),
            cash_total_override=Decimal("15000.00"),
        ),
    )

    listing = client.get("/offers")
    assert listing.status_code == 200
    assert "Ürünler" in listing.text
    assert "Buzdolabı ×2" in listing.text
    assert "JSON Dışa Aktar" in listing.text

    exported = client.get("/offers/export/json")
    assert exported.status_code == 200
    payload = json.loads(exported.content)
    assert payload["offers"][0]["items"][0]["product_name"] == "Buzdolabı"
    assert payload["offers"][0]["items"][0]["quantity"] == 2
    assert payload["offers"][0]["cash_total_override"] == "15000.00"


def test_offer_line_long_campaign_name_uses_wrapping_text_not_badge(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    from datetime import UTC, datetime, timedelta

    from bayios.application.campaigns import (
        CampaignInput,
        CampaignProductInput,
        create_campaign,
    )
    from bayios.domain.campaigns import (
        BasePriceType,
        CampaignType,
        DiscountType,
        ProductRelationType,
    )

    product = next(iter(fake_uow.products.get_all()))
    long_name = (
        "Seçili Beyaz Eşya, Ankastre Set alımına Kurutma Makineleri "
        "veya Klimalarda %50'ye Varan İndirim Fırsatı!"
    )
    now = datetime.now(UTC)
    create_campaign(
        fake_uow,
        CampaignInput(
            name=long_name,
            campaign_type=CampaignType.PRODUCT_DISCOUNT,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=30),
            base_price_type=BasePriceType.REGULAR,
            discount_type=DiscountType.PERCENT,
            discount_value=Decimal(50),
            products=(CampaignProductInput(product.id, ProductRelationType.BENEFIT),),
        ),
    )

    form = client.get(f"/offers/new?product_id={product.id}")

    assert form.status_code == 200
    assert "Kurutma Makineleri" in form.text
    assert "offer-line-campaign-name" in form.text
    assert (
        '<span class="badge badge-info" x-text="item.campaign_name"></span>'
        not in form.text
    )


def test_offer_form_has_manual_totals_sticky_bar_and_collapsible_options(
    client: TestClient,
) -> None:
    form = client.get("/offers/new")

    assert form.status_code == 200
    assert "Nakit Toplam (manuel)" in form.text
    assert "Kart Toplam (manuel)" in form.text
    assert "sticky-action-bar" in form.text
    assert "offer-scenario-summary" in form.text
    assert "Senaryo Özeti" in form.text
    assert "<details" in form.text
    assert "Taksit Seçenekleri" in form.text
    assert "applyManualTotals" in form.text


def test_offer_json_import_preview_accepts_exported_payload(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))
    create_offer(
        fake_uow,
        OfferInput(
            customer_name="JSON Müşterisi",
            customer_phone=None,
            payment_type=PaymentType.CASH,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product.id, 1),),
        ),
    )
    source = export_offers_json(fake_uow)

    preview = client.post(
        "/imports/offers/preview",
        files={"file": ("teklifler.json", source, "application/json")},
    )
    assert preview.status_code == 200
    assert "Teklif JSON İçe Aktarma Önizlemesi" in preview.text
    assert "JSON Müşterisi" in preview.text
