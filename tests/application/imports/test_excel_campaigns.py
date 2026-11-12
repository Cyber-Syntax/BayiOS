from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from openpyxl import Workbook, load_workbook

from bayios.adapters.db.models.products import Product
from bayios.application.campaigns import (
    CampaignInput,
    CampaignProductInput,
    create_campaign,
)
from bayios.application.campaigns.io import (
    export_campaign_products_xlsx,
    export_campaigns_xlsx,
)
from bayios.application.imports.campaigns import (
    commit_campaign_import,
    preview_campaign_import,
)
from bayios.domain.campaigns import (
    CampaignType,
    DiscountType,
    ProductRelationType,
)
from tests.fakes import FakeUnitOfWork


def _fixture() -> tuple[FakeUnitOfWork, Product, Product]:
    uow = FakeUnitOfWork()
    fridge = Product(
        id=uuid.uuid4(),
        name="70 cm Buzdolabı",
        name_normalized="70 cm buzdolabı",
        regular_price=Decimal(50000),
        physical_stock=1,
    )
    freezer = Product(
        id=uuid.uuid4(),
        name="Buzluk",
        name_normalized="buzluk",
        regular_price=Decimal(5000),
        physical_stock=1,
    )
    uow.products.add(fridge)
    uow.products.add(freezer)
    create_campaign(
        uow,
        CampaignInput(
            name="Düğün",
            campaign_type=CampaignType.GIFT,
            starts_at=datetime(2026, 11, 1, tzinfo=UTC),
            ends_at=datetime(2026, 11, 30, tzinfo=UTC),
            discount_type=DiscountType.GIFT,
            gift_description="Buzluk hediye",
            products=(
                CampaignProductInput(fridge.id, ProductRelationType.QUALIFYING),
                CampaignProductInput(freezer.id, ProductRelationType.GIFT),
            ),
        ),
    )
    return uow, fridge, freezer


def _flat_workbook(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Kampanyalar"
    sheet.append(
        [
            "Kampanya Adı",
            "Başlangıç Tarihi",
            "Bitiş Tarihi",
            "Kampanya Tipi",
            "İndirim Türü",
            "İndirim Değeri",
            "Hediye Açıklaması",
            "Ürün Adı",
            "İlişki Türü",
            "Gerekli Adet",
        ]
    )
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def test_campaign_export_has_two_sheets_and_relations() -> None:
    uow, _fridge, _freezer = _fixture()
    data = export_campaigns_xlsx(uow)
    workbook = load_workbook(io.BytesIO(data))
    assert workbook.sheetnames == ["Kampanyalar", "Kampanya Ürünleri", "Kullanım"]
    campaign_headers = [cell.value for cell in workbook["Kampanyalar"][1]]
    product_headers = [cell.value for cell in workbook["Kampanya Ürünleri"][1]]
    assert "Kampanya Adı" in campaign_headers
    assert "Başlangıç Tarihi" in campaign_headers
    assert "Ürün Adı" in product_headers
    assert "İlişki Türü" in product_headers
    assert workbook["Kampanya Ürünleri"].max_row == 3


def test_campaign_round_trip_is_skipped_unchanged() -> None:
    uow, _fridge, _freezer = _fixture()
    data = export_campaigns_xlsx(uow)
    preview = preview_campaign_import(uow, data)
    assert len(preview.rows) == 1
    assert preview.rows[0].decision == "update"
    result = commit_campaign_import(
        uow,
        file_name="kampanya.xlsx",
        file_type="xlsx",
        source=data,
        decisions={},
        commit_token="campaign-roundtrip",
    )
    assert result.updated_count == 0
    assert result.skipped_count == 1
    assert len(uow.campaigns.versions) == 1


def test_flat_campaign_import_creates_campaign_with_relations() -> None:
    uow = FakeUnitOfWork()
    fridge = Product(
        id=uuid.uuid4(),
        name="70 cm Buzdolabı",
        name_normalized="70 cm buzdolabı",
        regular_price=Decimal(50000),
        physical_stock=1,
    )
    freezer = Product(
        id=uuid.uuid4(),
        name="Buzluk",
        name_normalized="buzluk",
        regular_price=Decimal(5000),
        physical_stock=1,
    )
    uow.products.add(fridge)
    uow.products.add(freezer)
    data = _flat_workbook(
        [
            [
                "Kasım Hediyesi",
                "01.11.2026",
                "30.11.2026",
                "Hediye",
                "Hediye",
                "",
                "Buzluk",
                "70 cm Buzdolabı",
                "Şart ürünü",
                1,
            ],
            [
                "Kasım Hediyesi",
                "01.11.2026",
                "30.11.2026",
                "Hediye",
                "Hediye",
                "",
                "Buzluk",
                "Buzluk",
                "Hediye ürünü",
                1,
            ],
        ]
    )
    preview = preview_campaign_import(uow, data)
    assert len(preview.rows) == 1
    assert not preview.rows[0].errors, preview.rows[0].errors
    result = commit_campaign_import(
        uow,
        file_name="kampanya.xlsx",
        file_type="xlsx",
        source=data,
        decisions={},
        commit_token="campaign-flat",
    )
    assert result.created_count == 1
    assert len(uow.campaigns.campaigns) == 1
    assert sum(
        len(bucket) for bucket in uow.campaigns.version_products.values()
    ) == 2


def test_campaign_import_requires_end_date() -> None:
    uow, _fridge, _freezer = _fixture()
    data = _flat_workbook(
        [
            [
                "Eksik Tarih",
                "01.11.2026",
                "",
                "Genel",
                "Sadece bilgi",
                "",
                "",
                "",
                "",
                "",
            ],
        ]
    )
    preview = preview_campaign_import(uow, data)
    assert preview.rows[0].errors
    assert any("Bitiş tarihi" in error for error in preview.rows[0].errors)


def test_campaign_detail_export_contains_only_target_campaign() -> None:
    uow, _fridge, _freezer = _fixture()
    create_campaign(
        uow,
        CampaignInput(
            name="Başka Kampanya",
            campaign_type=CampaignType.GENERAL,
            starts_at=datetime(2026, 11, 1, tzinfo=UTC),
            ends_at=datetime(2026, 11, 30, tzinfo=UTC),
            discount_type=DiscountType.INFO_ONLY,
        ),
    )
    campaign = next(iter(uow.campaigns.campaigns.values()))
    data = export_campaign_products_xlsx(uow, campaign.id)
    workbook = load_workbook(io.BytesIO(data))
    assert workbook["Kampanya Ürünleri"].max_row == 3
    assert workbook["Kampanya Ürünleri"]["A1"].value == "Ürün Adı"


def test_campaign_detail_import_can_replace_products_from_product_only_sheet() -> None:
    uow, fridge, freezer = _fixture()
    campaign = next(iter(uow.campaigns.campaigns.values()))
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Kampanya Ürünleri"
    sheet.append(["Ürün Adı", "İlişki Türü", "Gerekli Adet"])
    sheet.append(["70 cm Buzdolabı", "Şart ürünü", 1])
    sheet.append(["Buzluk", "Hediye ürünü", 1])
    stream = io.BytesIO()
    workbook.save(stream)
    data = stream.getvalue()

    preview = preview_campaign_import(
        uow, data, target_campaign_id=campaign.id
    )
    assert len(preview.rows) == 1
    assert not preview.rows[0].errors
    result = commit_campaign_import(
        uow,
        file_name="kampanya.xlsx",
        file_type="xlsx",
        source=data,
        decisions={},
        commit_token="campaign-detail-products",
        target_campaign_id=campaign.id,
    )
    assert result.updated_count == 1
    current = uow.campaigns.get_current_version(campaign.id)
    assert current is not None
    links = uow.campaigns.get_version_products(current.id)
    assert {link.product_id for link in links} == {fridge.id, freezer.id}
