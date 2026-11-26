from __future__ import annotations

import json
import uuid
from decimal import Decimal

from bayios.adapters.db.models.commissions import Bank
from bayios.adapters.db.models.products import Product
from bayios.application.campaigns.json_io import export_campaign_detail_json
from bayios.application.imports.campaigns_json import (
    commit_campaign_json,
    preview_campaign_json,
)
from tests.fakes import FakeUnitOfWork


def _fixture() -> tuple[FakeUnitOfWork, Product, Product]:
    uow = FakeUnitOfWork()
    fridge = Product(
        id=uuid.uuid4(),
        external_id="9000",
        name="70 cm Buzdolabı",
        name_normalized="70 cm buzdolabı",
        regular_price=Decimal(50000),
        physical_stock=1,
    )
    freezer = Product(
        id=uuid.uuid4(),
        external_id="9001",
        name="Buzluk",
        name_normalized="buzluk",
        regular_price=Decimal(5000),
        physical_stock=1,
    )
    uow.products.add(fridge)
    uow.products.add(freezer)
    return uow, fridge, freezer


def _payload(
    *,
    campaign_id: str = "json-kampanya",
    conditions: list[str] | None = None,
    unknown_product: bool = False,
) -> bytes:
    products = [
        {
            "name": "70 cm Buzdolabı",
            "product_id": "9000",
            "relationship": "Şart ürünü",
            "required_quantity": 1,
        },
        {
            "name": "Buzluk",
            "product_id": "9001",
            "relationship": "Hediye ürünü",
            "required_quantity": None,
        },
    ]
    if unknown_product:
        products.append(
            {
                "name": "Katalogda Olmayan Ürün",
                "product_id": "9999999999",
                "relationship": "İlgili ürün",
                "required_quantity": None,
            }
        )
    return json.dumps(
        {
            "schema_version": "1.0",
            "scraped_at": "2026-11-22T14:26:27Z",
            "campaigns": [
                {
                    "id": campaign_id,
                    "name": "JSON Kampanya",
                    "category": "beyaz-esya-kampanyalari",
                    "url": "https://example.test/kampanya",
                    "date_text": "1 Kasım - 30 Kasım 2026",
                    "start_date": "2026-11-01",
                    "end_date": "2026-11-30",
                    "conditions": conditions or ["Koşul 1", "Koşul 2"],
                    "product_count": len(products),
                    "products": products,
                    "scraped_at": "2026-11-22T14:26:27Z",
                }
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")


def test_campaign_json_imports_structured_campaign_fields() -> None:
    uow, _fridge, freezer = _fixture()
    bank = Bank(
        id=uuid.uuid4(),
        name="Akbank",
        name_normalized="akbank",
        is_active=True,
    )
    uow.commissions.add_bank(bank)
    payload = _payload()
    data = json.loads(payload)
    campaign = data["campaigns"][0]
    campaign.update(
        {
            "campaign_type": "bundle",
            "discount_type": "fixed_amount",
            "discount_value": 17850,
            "min_basket_total": 125000,
            "combines_with_others": False,
            "gift_description": "Çay Makinesi",
            "gift_optional": False,
            "payment_conditions": [
                {
                    "channel": "pos",
                    "bank_names": ["Akbank"],
                    "card_type": "consumer",
                    "card_network": "World",
                    "installment_count": 8,
                }
            ],
        }
    )
    campaign["products"][1]["gift_price"] = 800
    source = json.dumps(data, ensure_ascii=False).encode("utf-8")

    preview = preview_campaign_json(uow, source)
    assert not preview.rows[0].errors

    commit_campaign_json(
        uow,
        file_name="kampanyalar.json",
        file_type="json",
        source=source,
        decisions={},
    )
    campaign_row = next(iter(uow.campaigns.campaigns.values()))
    version = uow.campaigns.get_current_version(campaign_row.id)
    assert version is not None
    assert version.campaign_type == "bundle"
    assert version.discount_type == "fixed_amount"
    assert version.discount_value == Decimal(17850)
    assert version.min_basket_total == Decimal(125000)
    assert version.combines_with_others is False
    assert version.gift_description == "Çay Makinesi"
    assert version.payment_conditions == [
        {
            "channel": "pos",
            "bank_ids": [str(bank.id)],
            "card_type": "consumer",
            "card_network": "World",
            "installment_count": 8,
        }
    ]
    links = uow.campaigns.get_version_products(version.id)
    gift_link = next(link for link in links if link.product_id == freezer.id)
    assert gift_link.gift_price == Decimal(800)


def test_campaign_json_preview_and_commit_saves_conditions() -> None:
    uow, fridge, freezer = _fixture()
    source = _payload()

    preview = preview_campaign_json(uow, source)

    assert len(preview.rows) == 1
    assert preview.rows[0].decision == "create"
    assert not preview.rows[0].errors
    assert preview.rows[0].values["products"] == "2 / 2"
    assert preview.rows[0].values["conditions"] == 2

    result = commit_campaign_json(
        uow,
        file_name="kampanyalar.json",
        file_type="json",
        source=source,
        decisions={},
    )

    assert result.created_count == 1
    campaign = next(iter(uow.campaigns.campaigns.values()))
    version = uow.campaigns.get_current_version(campaign.id)
    assert version is not None
    assert campaign.external_id == "json-kampanya"
    assert campaign.source_url == "https://example.test/kampanya"
    assert version.source_category == "beyaz-esya-kampanyalari"
    assert version.conditions == ["Koşul 1", "Koşul 2"]
    assert version.source_product_count == 2
    assert version.scraped_at is not None
    links = uow.campaigns.get_version_products(version.id)
    assert {link.product_id for link in links} == {fridge.id, freezer.id}


def test_campaign_json_reimport_is_idempotent_and_condition_change_creates_version() -> None:
    uow, _fridge, _freezer = _fixture()
    source = _payload()
    commit_campaign_json(
        uow,
        file_name="kampanyalar.json",
        file_type="json",
        source=source,
        decisions={},
    )
    campaign = next(iter(uow.campaigns.campaigns.values()))
    first_version = uow.campaigns.get_current_version(campaign.id)

    result = commit_campaign_json(
        uow,
        file_name="kampanyalar.json",
        file_type="json",
        source=source,
        decisions={},
    )

    assert result.updated_count == 0
    assert result.skipped_count == 1
    assert uow.campaigns.get_current_version(campaign.id) is first_version

    changed = _payload(conditions=["Yeni koşul"])
    result = commit_campaign_json(
        uow,
        file_name="kampanyalar-2.json",
        file_type="json",
        source=changed,
        decisions={},
    )

    assert result.updated_count == 1
    new_version = uow.campaigns.get_current_version(campaign.id)
    assert new_version is not None
    assert new_version.version_no == 2
    assert new_version.conditions == ["Yeni koşul"]


def test_campaign_json_missing_products_are_warned_and_skipped() -> None:
    uow, _fridge, _freezer = _fixture()
    source = _payload(unknown_product=True)

    preview = preview_campaign_json(uow, source)

    assert not preview.rows[0].errors
    assert any(
        "otomatik oluşturulacak" in warning
        for warning in preview.rows[0].warnings
    )
    assert preview.rows[0].values["products"] == "2 / 3"

    result = commit_campaign_json(
        uow,
        file_name="kampanyalar.json",
        file_type="json",
        source=source,
        decisions={},
    )

    assert result.created_count == 1
    campaign = next(iter(uow.campaigns.campaigns.values()))
    version = uow.campaigns.get_current_version(campaign.id)
    assert version is not None
    assert version.source_product_count == 3
    assert len(uow.campaigns.get_version_products(version.id)) == 3
    created = uow.products.get_by_external_id("9999999999")
    assert created is not None
    assert created.name == "Katalogda Olmayan Ürün"
    assert created.regular_price is None


def test_campaign_json_export_round_trips_conditions_and_product_ids() -> None:
    uow, _fridge, _freezer = _fixture()
    source = _payload()
    commit_campaign_json(
        uow,
        file_name="kampanyalar.json",
        file_type="json",
        source=source,
        decisions={},
    )
    campaign = next(iter(uow.campaigns.campaigns.values()))

    exported = json.loads(export_campaign_detail_json(uow, campaign.id))
    item = exported["campaigns"][0]

    assert exported["schema_version"] == "1.0"
    assert item["id"] == "json-kampanya"
    assert item["conditions"] == ["Koşul 1", "Koşul 2"]
    assert item["category"] == "beyaz-esya-kampanyalari"
    assert item["url"] == "https://example.test/kampanya"
    assert {product["product_id"] for product in item["products"]} == {
        "9000",
        "9001",
    }
    assert item["date_text"] == "1 Kasım - 30 Kasım 2026"


def test_campaign_json_duplicate_external_id_is_skipped() -> None:
    uow, _fridge, _freezer = _fixture()
    payload = json.loads(_payload())
    payload["campaigns"].append(payload["campaigns"][0])
    source = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    preview = preview_campaign_json(uow, source)

    assert len(preview.rows) == 2
    assert preview.rows[0].decision == "create"
    assert preview.rows[1].errors
    result = commit_campaign_json(
        uow,
        file_name="kampanyalar.json",
        file_type="json",
        source=source,
        decisions={},
    )
    assert result.created_count == 1
    assert result.error_count == 1


def test_campaign_json_creates_same_missing_product_once_across_campaigns() -> None:
    uow = FakeUnitOfWork()
    product = {
        "name": "6433 OK",
        "product_id": "6433",
        "relationship": "İlgili ürün",
        "required_quantity": None,
    }
    payload = {
        "schema_version": "1.0",
        "scraped_at": "2026-11-22T14:26:27Z",
        "campaigns": [
            {
                "id": "campaign-a",
                "name": "Kampanya A",
                "start_date": "2026-11-01",
                "end_date": "2026-11-30",
                "products": [product],
            },
            {
                "id": "campaign-b",
                "name": "Kampanya B",
                "start_date": "2026-11-01",
                "end_date": "2026-11-30",
                "products": [product],
            },
        ],
    }
    source = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    result = commit_campaign_json(
        uow,
        file_name="kampanyalar.json",
        file_type="json",
        source=source,
        decisions={},
    )

    assert result.created_count == 2
    created = uow.products.get_all()
    assert len(created) == 1
    assert created[0].external_id == "6433"
    assert created[0].name == "6433 OK"
