from __future__ import annotations

import io
import uuid
from decimal import Decimal

from openpyxl import load_workbook

from bayios.adapters.db.models.products import Product, ProductCategory
from bayios.application.products import (
    export_products_csv,
    export_products_xlsx,
    get_product_detail,
    search_products,
)
from tests.fakes import FakeUnitOfWork


def test_search_preserves_leading_zeros() -> None:
    uow = FakeUnitOfWork()
    p1 = Product(
        id=uuid.uuid4(),
        name="07325 A",
        name_normalized="07325 a",
        regular_price=Decimal(38099),
        physical_stock=5,
    )
    p2 = Product(
        id=uuid.uuid4(),
        name="7325 B",
        name_normalized="7325 b",
        regular_price=Decimal(20000),
        physical_stock=2,
    )
    uow.products.add(p1)
    uow.products.add(p2)

    # Search with leading zero
    results, count = search_products(uow, query="07325")
    assert count == 1
    assert results[0].name == "07325 A"

    # Search without leading zero
    results, count = search_products(uow, query="7325 B")
    assert count == 1
    assert results[0].name == "7325 B"


def test_search_finds_by_turkish_normalized_name() -> None:
    uow = FakeUnitOfWork()
    p = Product(
        id=uuid.uuid4(),
        name="Çamaşır Makinesi",
        name_normalized="çamaşır makinesi",
        regular_price=Decimal(15000),
        physical_stock=3,
    )
    uow.products.add(p)

    results, count = search_products(uow, query="çamaşır")
    assert count == 1
    assert results[0].name == "Çamaşır Makinesi"

    results, count = search_products(uow, query="CAMASIR")
    # In Turkish normalization, CAMASIR or ÇAMAŞIR matches
    results, count = search_products(uow, query="ÇAMAŞIR")
    assert count == 1


def test_search_filters_by_category() -> None:
    uow = FakeUnitOfWork()
    category = ProductCategory(id=uuid.uuid4(), name="Bulaşık Makinesi")
    uow.products.add_category(category)
    p1 = Product(
        id=uuid.uuid4(),
        name="09470 HP",
        name_normalized="09470 hp",
        regular_price=Decimal(52899),
        physical_stock=5,
        category_id=category.id,
    )
    p2 = Product(
        id=uuid.uuid4(),
        name="07325 A",
        name_normalized="07325 a",
        regular_price=Decimal(38099),
        physical_stock=3,
    )
    uow.products.add(p1)
    uow.products.add(p2)

    results, count = search_products(uow, category_id=category.id)
    assert count == 1
    assert results[0].name == "09470 HP"


def test_get_product_detail_calculates_stock_correctly() -> None:
    uow = FakeUnitOfWork()
    prod_id = uuid.uuid4()
    p = Product(
        id=prod_id,
        name="Buzdolabı",
        name_normalized="buzdolabı",
        regular_price=Decimal(25000),
        website_discounted_price=Decimal(23000),
        physical_stock=7,
    )
    uow.products.add(p)

    detail = get_product_detail(uow, prod_id)
    assert detail is not None
    assert detail.product.name == "Buzdolabı"
    assert detail.open_reservation == 0


def test_export_products_csv_and_xlsx() -> None:
    uow = FakeUnitOfWork()
    category = ProductCategory(id=uuid.uuid4(), name="Buzdolabı")
    uow.products.add_category(category)
    p1 = Product(
        id=uuid.uuid4(),
        name="07325 A",
        name_normalized="07325 a",
        regular_price=Decimal("38099.00"),
        website_discounted_price=Decimal("34099.00"),
        physical_stock=5,
        category_id=category.id,
    )
    p2 = Product(
        id=uuid.uuid4(),
        name="09325 A",
        name_normalized="09325 a",
        regular_price=Decimal("42199.00"),
        website_discounted_price=None,
        physical_stock=0,
    )
    uow.products.add(p1)
    uow.products.add(p2)

    # 1. Test CSV export
    csv_bytes = export_products_csv(uow)
    assert csv_bytes.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
    csv_text = csv_bytes.decode("utf-8-sig")
    assert "07325 A,Buzdolabı,38099.00,34099.00,5," in csv_text
    assert "09325 A,,42199.00,,0," in csv_text

    # 2. Test XLSX export
    xlsx_bytes = export_products_xlsx(uow)
    assert xlsx_bytes.startswith(b"PK")  # ZIP signature of xlsx
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0] == (
        "product_name",
        "category",
        "regular_price",
        "website_discounted_price",
        "quantity",
        "cost_price",
    )
    assert rows[1][0] == "07325 A"
    assert rows[1][1] == "Buzdolabı"
    assert rows[1][2] == 38099.00
    assert rows[1][3] == 34099.00
    assert rows[1][4] == 5
    wb.close()


def test_create_manual_product_creates_history_and_movements() -> None:
    from bayios.application.products import create_manual_product
    from bayios.domain.products import ActorContext

    uow = FakeUnitOfWork()
    actor = ActorContext(worker_name="Ahmet", device_name="Kasa-1")
    product = create_manual_product(
        uow=uow,
        name="07325 A",
        regular_price=Decimal(38099),
        website_discounted_price=Decimal(34099),
        cost_price=Decimal(25000),
        physical_stock=5,
        actor=actor,
    )

    assert uow.committed
    assert product.name == "07325 A"
    assert product.physical_stock == 5
    assert len(uow.products.price_history) == 3
    assert len(uow.products.stock_movements) == 1
    assert uow.products.stock_movements[0].quantity_delta == 5
    assert uow.products.stock_movements[0].movement_type == "manual_adjustment"


def test_archive_and_unarchive_products() -> None:
    from bayios.application.products import archive_products, create_manual_product

    uow = FakeUnitOfWork()
    p1 = create_manual_product(uow, name="Ürün 1")
    p2 = create_manual_product(uow, name="Ürün 2")

    # Bulk archive
    archived_count = archive_products(uow, [p1.id, p2.id], archive=True)
    assert archived_count == 2
    assert uow.committed
    active_results, count = search_products(uow, include_archived=False)
    assert count == 0

    _archived_results, count = search_products(uow, only_archived=True)
    assert count == 2

    # Unarchive
    archive_products(uow, [p1.id], archive=False)
    active_results, count = search_products(uow, include_archived=False)
    assert count == 1
    assert active_results[0].id == p1.id


def test_delete_products_removes_from_database() -> None:
    from bayios.application.products import create_manual_product, delete_products

    uow = FakeUnitOfWork()
    p1 = create_manual_product(uow, name="Silinecek Ürün", regular_price=Decimal(100), physical_stock=2)
    assert len(uow.products.products) == 1
    assert len(uow.products.price_history) == 1
    assert len(uow.products.stock_movements) == 1

    deleted_count = delete_products(uow, [p1.id])
    assert deleted_count == 1
    assert uow.committed
    assert len(uow.products.products) == 0
    assert len(uow.products.price_history) == 0
    assert len(uow.products.stock_movements) == 0


def test_adjust_product_stock_creates_movement() -> None:
    from bayios.application.products import adjust_product_stock, create_manual_product

    uow = FakeUnitOfWork()
    p = create_manual_product(uow, name="Stok Test Ürün", physical_stock=3)
    assert p.physical_stock == 3

    adjust_product_stock(uow, p.id, new_physical_stock=8, note="Raf sayımı düzeltildi")
    assert uow.committed
    assert p.physical_stock == 8
    movements = uow.products.get_stock_movements(p.id)
    # 1 initial + 1 adjustment
    assert len(movements) == 2
    latest = movements[-1]
    assert latest.quantity_delta == 5
    assert latest.quantity_before == 3
    assert latest.quantity_after == 8
    assert latest.note == "Raf sayımı düzeltildi"


def test_update_product_records_price_history_and_normalized_name() -> None:
    from bayios.application.products import create_manual_product, update_product

    uow = FakeUnitOfWork()
    p = create_manual_product(
        uow,
        name="07325 A",
        regular_price=Decimal(38099),
        website_discounted_price=Decimal(34099),
        cost_price=Decimal(25000),
    )
    initial_history = len(uow.products.get_price_history(p.id))

    updated = update_product(
        uow,
        p.id,
        name="07325 A V2",
        regular_price=Decimal(40000),
        website_discounted_price=None,
        cost_price=Decimal(25000),
    )

    assert uow.committed
    assert updated.name == "07325 A V2"
    assert updated.name_normalized == "07325 a v2"
    assert updated.regular_price == Decimal(40000)
    assert updated.website_discounted_price is None
    histories = uow.products.get_price_history(p.id)
    assert len(histories) == initial_history + 2
    assert {h.field_name for h in histories[-2:]} == {
        "regular_price",
        "website_discounted_price",
    }
