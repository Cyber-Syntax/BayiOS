from __future__ import annotations

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
