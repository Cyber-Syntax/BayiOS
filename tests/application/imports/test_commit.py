from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from decimal import Decimal

from bayios.application.imports import commit_product_import
from bayios.domain.products import ActorContext
from tests.fakes import FakeUnitOfWork


def test_commit_creates_new_products_and_history_and_movements() -> None:
    uow = FakeUnitOfWork()
    csv_bytes = b"product_name,regular_price,website_discounted_price,quantity\n07325 A,38099,34099,5\n"
    actor = ActorContext(device_name="Terminal 1", worker_name="Ahmet")

    result = commit_product_import(
        uow=uow,
        file_name="test.csv",
        file_type="csv",
        source=csv_bytes,
        actor=actor,
    )

    assert result.created_count == 1
    assert result.updated_count == 0
    assert result.error_count == 0
    assert uow.committed

    product = uow.products.get_by_normalized_name("07325 a")
    assert product is not None
    assert product.name == "07325 A"
    assert product.regular_price == Decimal(38099)
    assert product.website_discounted_price == Decimal(34099)
    assert product.physical_stock == 5

    # Check price history
    histories = uow.products.get_price_history(product.id)
    assert len(histories) == 2
    assert {h.field_name for h in histories} == {"regular_price", "website_discounted_price"}

    # Check stock movements
    movements = uow.products.get_stock_movements(product.id)
    assert len(movements) == 1
    assert movements[0].movement_type == "csv_update"
    assert movements[0].quantity_delta == 5
    assert movements[0].quantity_before == 0
    assert movements[0].quantity_after == 5


def test_commit_assigns_and_auto_creates_category() -> None:
    uow = FakeUnitOfWork()
    csv_bytes = (
        b"product_name,category,regular_price,quantity\n"
        b"07325 A,Buzdolabi,38099,5\n"
        b"09470 HP,,52899,0\n"
    )

    result = commit_product_import(
        uow=uow,
        file_name="test.csv",
        file_type="csv",
        source=csv_bytes,
        actor=ActorContext(worker_name="Ahmet"),
    )

    assert result.created_count == 2

    p1 = uow.products.get_by_normalized_name("07325 a")
    assert p1 is not None
    assert p1.category_id is not None
    category = uow.products.get_category(p1.category_id)
    assert category is not None
    assert category.name == "Buzdolabi"

    p2 = uow.products.get_by_normalized_name("09470 hp")
    assert p2 is not None
    assert p2.category_id is None


def test_commit_updates_existing_product_price_and_stock() -> None:
    uow = FakeUnitOfWork()
    csv1 = b"product_name,regular_price,website_discounted_price,quantity\n07325 A,38099,34099,5\n"
    commit_product_import(uow=uow, file_name="test1.csv", file_type="csv", source=csv1)

    product = uow.products.get_by_normalized_name("07325 a")
    assert product is not None
    initial_hist_count = len(uow.products.get_price_history(product.id))

    # Second import: price increases to 40000, stock becomes 8
    csv2 = b"product_name,regular_price,website_discounted_price,quantity\n07325 A,40000,34099,8\n"
    result2 = commit_product_import(
        uow=uow,
        file_name="test2.csv",
        file_type="csv",
        source=csv2,
    )

    assert result2.updated_count == 1
    assert product.regular_price == Decimal(40000)
    assert product.physical_stock == 8

    # Price history grew by 1 (only regular_price changed, website_discounted_price did not)
    histories = uow.products.get_price_history(product.id)
    assert len(histories) == initial_hist_count + 1
    latest_hist = histories[-1]
    assert latest_hist.field_name == "regular_price"
    assert latest_hist.old_value == Decimal(38099)
    assert latest_hist.new_value == Decimal(40000)

    # Stock movements grew by 1 with delta +3
    movements = uow.products.get_stock_movements(product.id)
    assert len(movements) == 2
    assert movements[-1].quantity_delta == 3
    assert movements[-1].quantity_before == 5
    assert movements[-1].quantity_after == 8


def test_commit_blank_quantity_leaves_stock_unchanged() -> None:
    uow = FakeUnitOfWork()
    csv1 = b"product_name,regular_price,website_discounted_price,quantity\n07325 A,38099,,10\n"
    commit_product_import(uow=uow, file_name="test1.csv", file_type="csv", source=csv1)

    product = uow.products.get_by_normalized_name("07325 a")
    assert product is not None
    assert product.physical_stock == 10

    # Second import with blank quantity
    csv2 = b"product_name,regular_price,website_discounted_price,quantity\n07325 A,39000,,\n"
    commit_product_import(uow=uow, file_name="test2.csv", file_type="csv", source=csv2)

    # Physical stock should STILL be 10!
    assert product.physical_stock == 10
    # No new stock movement created
    assert len(uow.products.get_stock_movements(product.id)) == 1


def test_commit_zero_quantity_resets_stock_to_zero() -> None:
    uow = FakeUnitOfWork()
    csv1 = b"product_name,regular_price,website_discounted_price,quantity\n07325 A,38099,,10\n"
    commit_product_import(uow=uow, file_name="test1.csv", file_type="csv", source=csv1)

    product = uow.products.get_by_normalized_name("07325 a")
    assert product is not None

    csv2 = b"product_name,regular_price,website_discounted_price,quantity\n07325 A,38099,,0\n"
    commit_product_import(uow=uow, file_name="test2.csv", file_type="csv", source=csv2)

    assert product.physical_stock == 0
    movements = uow.products.get_stock_movements(product.id)
    assert len(movements) == 2
    assert movements[-1].quantity_delta == -10
    assert movements[-1].quantity_after == 0


def test_commit_respects_skip_and_clear_discount_decisions() -> None:
    uow = FakeUnitOfWork()
    csv1 = b"product_name,regular_price,website_discounted_price,quantity\n07325 A,38099,34099,5\n09325 A,42000,38000,3\n"
    commit_product_import(uow=uow, file_name="test1.csv", file_type="csv", source=csv1)

    p1 = uow.products.get_by_normalized_name("07325 a")
    p2 = uow.products.get_by_normalized_name("09325 a")
    assert p1 is not None and p2 is not None

    csv2 = b"product_name,regular_price,website_discounted_price,quantity\n07325 A,50000,34099,10\n09325 A,42000,38000,3\n"
    # Row 2 (07325 A) decision overridden to clear_discount
    # Row 3 (09325 A) decision overridden to skip
    commit_product_import(
        uow=uow,
        file_name="test2.csv",
        file_type="csv",
        source=csv2,
        decisions={2: "clear_discount", 3: "skip"},
    )

    # 07325 A had its discounted price cleared
    assert p1.website_discounted_price is None

    # 09325 A was skipped completely
    assert p2.regular_price == Decimal(42000)


def test_commit_real_arcelik_csv_snippet() -> None:
    uow = FakeUnitOfWork()
    csv_bytes = (
        b"product_name,regular_price,website_discounted_price,quantity\n"
        b"0.58m  with Anderson cable,475 TL,\n"
        b"07325 A,38.099 TL,34.099 TL\n"
        b"09325 A,42.199 TL,38.199 TL\n"
    )

    result = commit_product_import(
        uow=uow,
        file_name="arcelik-06-09-2026.csv",
        file_type="csv",
        source=csv_bytes,
    )

    assert result.created_count == 3
    assert result.error_count == 0

    p_cable = uow.products.get_by_normalized_name("0.58m with anderson cable")
    assert p_cable is not None
    assert p_cable.regular_price == Decimal(475)
    assert p_cable.website_discounted_price is None
    assert p_cable.physical_stock == 0

    p_07325 = uow.products.get_by_normalized_name("07325 a")
    assert p_07325 is not None
    assert p_07325.regular_price == Decimal(38099)
    assert p_07325.website_discounted_price == Decimal(34099)


def test_commit_unarchives_products_present_in_catalog_file() -> None:
    from bayios.application.products import archive_products

    uow = FakeUnitOfWork()
    csv_bytes = b"product_name,regular_price,quantity\n07325 A,38099,5\n"
    commit_product_import(uow=uow, file_name="test.csv", file_type="csv", source=csv_bytes)
    product = uow.products.get_by_normalized_name("07325 a")
    assert product is not None

    archive_products(uow, [product.id], archive=True)
    assert product.is_archived is True

    # A catalog file that still contains the product means it is active again.
    commit_product_import(
        uow=uow,
        file_name="test2.csv",
        file_type="csv",
        source=b"product_name,regular_price,quantity\n07325 A,38099,5\n",
        commit_token="second-import",
    )

    assert product.is_archived is False


def test_commit_duplicate_checksum_is_idempotent() -> None:
    uow = FakeUnitOfWork()
    csv_bytes = b"product_name,regular_price,website_discounted_price,quantity\n07325 A,38099,34099,5\n"

    r1 = commit_product_import(uow=uow, file_name="test.csv", file_type="csv", source=csv_bytes)
    assert r1.created_count == 1

    r2 = commit_product_import(uow=uow, file_name="test.csv", file_type="csv", source=csv_bytes)
    assert r2.created_count == 1
    assert r2.batch_id == r1.batch_id
    assert len(uow.products.get_all()) == 1


def test_commit_parses_turkish_cost_and_dealer_floor_prices() -> None:
    uow = FakeUnitOfWork()
    csv_bytes = (
        "Ürün Adı,Kategori,Perakende Fiyat,Oliz İndirimli Fiyat,Fiziksel Stok,Alış Fiyatı,Kredi Kartı Taban Fiyatı,Nakit Taban Fiyatı,Aktif Kampanya\n"
        "OCD T 601-1 EG,,38099,34099,5,25000,37000,36000,Kasım İndirimi\n"
    ).encode()

    result = commit_product_import(
        uow=uow,
        file_name="urunler.csv",
        file_type="csv",
        source=csv_bytes,
    )

    assert result.created_count == 1
    product = uow.products.get_by_normalized_name("ocd t 601-1 eg")
    assert product is not None
    assert product.cost_price == Decimal(25000)
    pricing = uow.dealer_pricing.get(product.id)
    assert pricing is not None
    assert pricing.cash_floor_price == Decimal(36000)
    assert pricing.card_floor_price == Decimal(37000)
    assert {row.field_name for row in uow.products.get_price_history(product.id)} == {
        "regular_price",
        "website_discounted_price",
        "cost_price",
    }


def test_commit_clears_cost_and_floor_prices_with_dash() -> None:
    uow = FakeUnitOfWork()
    commit_product_import(
        uow=uow,
        file_name="ilk.csv",
        file_type="csv",
        source=(
            "Ürün Adı,Perakende Fiyat,Alış Fiyatı,Kredi Kartı Taban Fiyatı,Nakit Taban Fiyatı\n"
            "OCD T 601-1 EG,38099,25000,37000,36000\n"
        ).encode(),
    )
    product = uow.products.get_by_normalized_name("ocd t 601-1 eg")
    assert product is not None

    commit_product_import(
        uow=uow,
        file_name="ikinci.csv",
        file_type="csv",
        source=(
            "Ürün Adı,Alış Fiyatı,Kredi Kartı Taban Fiyatı,Nakit Taban Fiyatı\n"
            "OCD T 601-1 EG,-,-,-\n"
        ).encode(),
    )

    assert product.cost_price is None
    pricing = uow.dealer_pricing.get(product.id)
    assert pricing is not None
    assert pricing.cash_floor_price is None
    assert pricing.card_floor_price is None


def test_commit_blank_oliz_clears_existing_discount_on_update() -> None:
    uow = FakeUnitOfWork()
    first = b"product_name,regular_price,website_discounted_price\n07325 A,38099,34099\n"
    commit_product_import(uow=uow, file_name="first.csv", file_type="csv", source=first)
    product = uow.products.get_by_normalized_name("07325 a")
    assert product is not None
    assert product.website_discounted_price == Decimal(34099)
    history_count = len(uow.products.get_price_history(product.id))

    second = b"product_name,regular_price,website_discounted_price\n07325 A,38099,\n"
    result = commit_product_import(
        uow=uow, file_name="second.csv", file_type="csv", source=second
    )

    assert result.updated_count == 1
    assert product.website_discounted_price is None
    histories = uow.products.get_price_history(product.id)
    assert len(histories) == history_count + 1
    assert histories[-1].field_name == "website_discounted_price"
    assert histories[-1].old_value == Decimal(34099)
    assert histories[-1].new_value is None


def test_commit_zero_oliz_clears_existing_discount_on_update() -> None:
    uow = FakeUnitOfWork()
    first = b"product_name,regular_price,website_discounted_price\n07325 A,38099,34099\n"
    commit_product_import(uow=uow, file_name="first.csv", file_type="csv", source=first)
    product = uow.products.get_by_normalized_name("07325 a")
    assert product is not None

    second = b"product_name,regular_price,website_discounted_price\n07325 A,38099,0\n"
    commit_product_import(
        uow=uow, file_name="second.csv", file_type="csv", source=second
    )

    assert product.website_discounted_price is None


def test_commit_absent_oliz_column_preserves_existing_discount() -> None:
    uow = FakeUnitOfWork()
    first = b"product_name,regular_price,website_discounted_price\n07325 A,38099,34099\n"
    commit_product_import(uow=uow, file_name="first.csv", file_type="csv", source=first)
    product = uow.products.get_by_normalized_name("07325 a")
    assert product is not None
    assert product.website_discounted_price == Decimal(34099)

    second = b"product_name,regular_price\n07325 A,39000\n"
    commit_product_import(
        uow=uow, file_name="second.csv", file_type="csv", source=second
    )

    assert product.regular_price == Decimal(39000)
    assert product.website_discounted_price == Decimal(34099)


def _csv_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return stream.getvalue().encode("utf-8")


def _catalog_bytes(products: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {
            "schema_version": "1.0",
            "scraped_at": "2026-11-22T11:53:05Z",
            "products": products,
        },
        ensure_ascii=False,
    ).encode("utf-8")


def test_commit_updates_external_id_and_keeps_old_id_alias() -> None:
    uow = FakeUnitOfWork()
    first = _csv_bytes(
        ["Ürün ID", "Ürün Adı", "Perakende Fiyat"],
        [["8000", "Ürün A", "10000"]],
    )
    commit_product_import(uow=uow, file_name="first.csv", file_type="csv", source=first)
    product = uow.products.get_by_normalized_name("ürün a")
    assert product is not None
    assert product.external_id == "8000"

    second = _csv_bytes(
        ["Ürün ID", "Ürün Adı", "Perakende Fiyat"],
        [["9000", "Ürün A", "12000"]],
    )
    result = commit_product_import(
        uow=uow, file_name="second.csv", file_type="csv", source=second
    )

    assert result.updated_count == 1
    assert product.external_id == "9000"
    assert product.regular_price == Decimal(12000)
    assert uow.products.get_by_external_id("9000") is product
    assert uow.products.get_by_external_id_including_history("8000") is product
    same_name = [
        item
        for item in uow.products.get_all()
        if item.name_normalized == "ürün a"
    ]
    assert len(same_name) == 1


def test_commit_catalog_json_saves_details_meta_and_kind() -> None:
    uow = FakeUnitOfWork()
    source = _catalog_bytes(
        [
            {
                "id": "457100070000",
                "product_name": "10122 SuperWash",
                "category": "Çamaşır Makinesi",
                "price": 42999.0,
                "discounted_price": None,
                "currency": "TRY",
                "source_url": "https://example.test/10122",
                "features": [
                    {"title": "SuperWash", "text": "Aciklama", "note": "Not"}
                ],
                "specifications": [
                    {"group": "Genel", "name": "Kapasite", "value": "10 kg"}
                ],
                "kind": "explicit",
                "scraped_at": "2026-11-22T11:53:05Z",
            }
        ]
    )

    result = commit_product_import(
        uow=uow, file_name="catalog.json", file_type="json", source=source
    )

    assert result.created_count == 1
    product = uow.products.get_by_external_id("457100070000")
    assert product is not None
    assert product.name == "10122 SuperWash"
    assert product.kind == "explicit"
    assert product.source_url == "https://example.test/10122"
    assert product.scraped_at is not None
    assert product.details == {
        "features": [{"title": "SuperWash", "text": "Aciklama", "note": "Not"}],
        "specifications": [
            {"group": "Genel", "name": "Kapasite", "value": "10 kg"}
        ],
    }


def test_commit_warranty_catalog_row_without_id_creates_product() -> None:
    uow = FakeUnitOfWork()
    source = _catalog_bytes(
        [
            {
                "id": "",
                "product_name": "2 Yıl Garanti",
                "category": "Ek Garanti",
                "price": 3099.0,
                "discounted_price": None,
                "currency": "TRY",
                "source_url": "https://example.test/garanti",
                "features": [],
                "specifications": [],
                "kind": "warranty",
                "scraped_at": "2026-11-22T11:53:05Z",
            }
        ]
    )

    result = commit_product_import(
        uow=uow, file_name="catalog.json", file_type="json", source=source
    )

    assert result.created_count == 1
    product = uow.products.get_by_normalized_name("2 yıl garanti")
    assert product is not None
    assert product.external_id is None
    assert product.kind == "warranty"


def test_commit_json_details_blank_preserves_and_empty_lists_clear() -> None:
    uow = FakeUnitOfWork()
    headers = [
        "Ürün Adı",
        "Perakende Fiyat",
        "Ürün Özellikleri (JSON)",
    ]
    details = {
        "features": [{"title": "T", "text": "X", "note": ""}],
        "specifications": [{"group": "G", "name": "N", "value": "V"}],
    }
    first = _csv_bytes(
        headers, [["Ürün Detay", "10000", json.dumps(details)]]
    )
    commit_product_import(uow=uow, file_name="first.csv", file_type="csv", source=first)
    product = uow.products.get_by_normalized_name("ürün detay")
    assert product is not None
    assert product.details == details

    second = _csv_bytes(headers, [["Ürün Detay", "11000", ""]])
    commit_product_import(
        uow=uow, file_name="second.csv", file_type="csv", source=second
    )
    assert product.details == details

    third = _csv_bytes(
        headers,
        [["Ürün Detay", "11000", '{"features":[],"specifications":[]}']],
    )
    commit_product_import(
        uow=uow, file_name="third.csv", file_type="csv", source=third
    )
    assert product.details == {"features": [], "specifications": []}


def test_commit_broken_json_details_updates_fields_but_preserves_details() -> None:
    uow = FakeUnitOfWork()
    headers = ["Ürün Adı", "Perakende Fiyat", "Ürün Özellikleri (JSON)"]
    first = _csv_bytes(
        headers,
        [
            [
                "Ürün Detay",
                "10000",
                '{"features":[{"title":"T","text":"X","note":""}],"specifications":[]}',
            ]
        ],
    )
    commit_product_import(uow=uow, file_name="first.csv", file_type="csv", source=first)
    product = uow.products.get_by_normalized_name("ürün detay")
    assert product is not None
    original_details = product.details

    second = _csv_bytes(headers, [["Ürün Detay", "12000", "{bozuk json"]])
    result = commit_product_import(
        uow=uow, file_name="second.csv", file_type="csv", source=second
    )

    assert product.regular_price == Decimal(12000)
    assert product.details == original_details
    assert result.error_count == 1


def test_commit_duplicate_external_id_first_row_wins() -> None:
    uow = FakeUnitOfWork()
    source = _csv_bytes(
        ["Ürün ID", "Ürün Adı", "Perakende Fiyat"],
        [
            ["8000", "Ürün A", "10000"],
            ["8000", "Ürün B", "20000"],
        ],
    )
    result = commit_product_import(
        uow=uow, file_name="duplicate.csv", file_type="csv", source=source
    )

    assert result.created_count == 1
    assert result.skipped_count == 1
    assert uow.products.get_by_external_id("8000") is not None
    assert uow.products.get_by_normalized_name("ürün b") is None


def test_commit_skips_unchanged_catalog_row_and_reports_zero_updated() -> None:
    uow = FakeUnitOfWork()
    source = _catalog_bytes(
        [
            {
                "id": "100",
                "product_name": "07325 A",
                "category": "",
                "price": 38099.0,
                "discounted_price": None,
                "currency": "TRY",
                "source_url": "https://example.test/100",
                "features": [],
                "specifications": [],
                "kind": "product",
                "scraped_at": "2026-11-24T20:47:23Z",
            }
        ]
    )

    first = commit_product_import(
        uow=uow,
        file_name="catalog.json",
        file_type="json",
        source=source,
        decisions={},
    )
    assert first.created_count == 1
    product = uow.products.get_by_external_id("100")
    assert product is not None
    old_seen = datetime(2020, 1, 1, tzinfo=UTC)
    old_scraped = datetime(2020, 1, 2, tzinfo=UTC)
    product.last_seen_at = old_seen
    product.scraped_at = old_scraped

    second = commit_product_import(
        uow=uow,
        file_name="catalog.json",
        file_type="json",
        source=source,
        decisions={},
    )

    assert second.created_count == 0
    assert second.updated_count == 0
    assert second.skipped_count == 1
    # FR-PROD-16: unchanged rows still refresh the seen timestamp.
    assert product.last_seen_at is not None
    assert product.last_seen_at > old_seen
    assert product.scraped_at is not None
    assert product.scraped_at > old_scraped
