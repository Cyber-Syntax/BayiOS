from __future__ import annotations

import base64
import io
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from bayios.adapters.db.models.products import Product
from bayios.application.campaigns import (
    CampaignInput,
    CampaignProductInput,
    create_campaign,
)
from bayios.application.commissions import create_commission_period
from bayios.application.offers import OfferInput, OfferItemInput, create_offer
from bayios.application.reservations import NewReservationItem, create_reservation
from bayios.bootstrap import ApplicationSettings
from bayios.domain.campaigns import (
    CampaignType,
    DiscountType,
    ProductRelationType,
)
from bayios.domain.offers import PaymentType
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
        regular_price=Decimal(50000),
        website_discounted_price=Decimal(46000),
        cost_price=Decimal(36000),
        physical_stock=1,
    )
    uow.products.add(product)
    create_campaign(
        uow,
        CampaignInput(
            name="Düğün",
            campaign_type=CampaignType.GIFT,
            starts_at=datetime(2026, 11, 1, tzinfo=UTC),
            ends_at=datetime(2026, 11, 30, tzinfo=UTC),
            discount_type=DiscountType.GIFT,
            gift_description="Buzluk",
            products=(
                CampaignProductInput(product.id, ProductRelationType.QUALIFYING),
            ),
        ),
    )
    create_offer(
        uow,
        OfferInput(
            customer_name="Ayşe",
            customer_phone="",
            payment_type=PaymentType.CASH,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product.id, 1),),
        ),
    )
    create_reservation(
        uow,
        "Mehmet",
        (NewReservationItem(product.id, 1),),
        reservation_date=datetime(2026, 11, 10, tzinfo=UTC),
    )
    create_commission_period(uow, 2026, 11)
    return uow


@pytest.fixture
def client(fake_uow: FakeUnitOfWork) -> TestClient:
    app = create_app(
        ApplicationSettings(
            database_url="postgresql+psycopg://user:pass@localhost:5432/bayios"
        )
    )
    app.dependency_overrides[get_unit_of_work] = lambda: fake_uow
    return TestClient(app)


def test_import_pages_and_export_endpoints(client: TestClient) -> None:
    for path in (
        "/imports/campaigns",
        "/imports/offers",
        "/imports/commissions/rates",
        "/imports/commissions/limits",
        "/imports/reservations",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert "Şablon İndir" in response.text

    for path in (
        "/campaigns/export/xlsx",
        "/offers/export/xlsx",
        "/commissions/export/rates.xlsx",
        "/commissions/export/limits.xlsx",
        "/reservations/export/xlsx",
        "/stock/export/xlsx",
        "/imports/products/template",
        "/imports/campaigns/template",
        "/imports/offers/template",
        "/imports/commissions/rates/template",
        "/imports/commissions/limits/template",
        "/imports/reservations/template",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.content.startswith(b"PK")


def test_product_export_contains_new_columns(client: TestClient) -> None:
    response = client.get("/products/export/xlsx")
    workbook = load_workbook(io.BytesIO(response.content))
    headers = [cell.value for cell in workbook.active[1]]
    assert "Alış Fiyatı" in headers
    assert "Kredi Kartı Taban Fiyatı" in headers
    assert "Nakit Taban Fiyatı" in headers
    assert "Aktif Kampanya" in headers


def test_campaign_preview_and_commit_routes(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    exported = client.get("/campaigns/export/xlsx").content
    preview = client.post(
        "/imports/campaigns/preview",
        files={
            "file": (
                "kampanyalar.xlsx",
                exported,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert preview.status_code == 200
    assert "Kampanya Excel İçe Aktarma Önizlemesi" in preview.text

    commit = client.post(
        "/imports/campaigns/commit",
        data={
            "file_name": "kampanyalar.xlsx",
            "file_type": "xlsx",
            "source_b64": base64.b64encode(exported).decode("ascii"),
            "import_token": "campaign-web-1",
            "decisions_json": "{}",
        },
        follow_redirects=False,
    )
    assert commit.status_code == 303
    assert "msg=import_success" in commit.headers["location"]


def test_offer_detail_shows_inline_profit_summary(client: TestClient) -> None:
    response = client.get("/offers")
    assert response.status_code == 200
    match = re.search(r"/offers/([0-9a-f-]{36})", response.text)
    assert match is not None
    detail = client.get(f"/offers/{match.group(1)}")
    assert detail.status_code == 200
    assert "Kâr / Komisyon Özeti" in detail.text
    assert "Kâr / Zarar" in detail.text
    assert "Komisyon Sonrası" in detail.text


def test_commission_rate_preview_route(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Komisyon Oranları"
    sheet.append(
        ["Dönem", "Kanal", "Banka", "Ürün Grubu", "Ödero Bandı", "Taksit", "Oran %"]
    )
    sheet.append(["2026-11", "POS", "", "Klima", "", 3, 2.5])
    stream = io.BytesIO()
    workbook.save(stream)
    response = client.post(
        "/imports/commissions/rates/preview",
        files={"file": ("oranlar.xlsx", stream.getvalue())},
    )
    assert response.status_code == 200
    assert "Komisyon Oranları Excel İçe Aktarma Önizlemesi" in response.text


def test_campaign_detail_excel_routes(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    campaign = next(iter(fake_uow.campaigns.campaigns.values()))
    export = client.get(f"/campaigns/{campaign.id}/export/xlsx")
    assert export.status_code == 200
    assert export.content.startswith(b"PK")
    workbook = load_workbook(io.BytesIO(export.content))
    assert workbook["Kampanya Ürünleri"]["A1"].value == "Ürün Adı"
    assert workbook["Kampanya Ürünleri"]["B1"].value == "İlişki Türü"

    page = client.get(f"/imports/campaigns?campaign_id={campaign.id}")
    assert page.status_code == 200
    assert f'name="campaign_id" value="{campaign.id}"' in page.text
