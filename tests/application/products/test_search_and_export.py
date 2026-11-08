from __future__ import annotations

import io
import uuid
from decimal import Decimal

from openpyxl import load_workbook

from bayios.adapters.db.models.products import Product
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
        regular_price=Decimal("38099"),
        physical_stock=5,
    )
    p2 = Product(
        id=uuid.uuid4(),
        name="7325 B",
        name_normalized="7325 b",
        regular_price=Decimal("20000"),
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
        regular_price=Decimal("15000"),
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


def test_get_product_detail_calculates_stock_correctly() -> None:
    uow = FakeUnitOfWork()
    prod_id = uuid.uuid4()
    p = Product(
        id=prod_id,
        name="Buzdolabı",
        name_normalized="buzdolabı",
        regular_price=Decimal("25000"),
        website_discounted_price=Decimal("23000"),
        physical_stock=7,
    )
    uow.products.add(p)

    detail = get_product_detail(uow, prod_id)
    assert detail is not None
    assert detail.product.name == "Buzdolabı"
    assert detail.sellable_stock == 7
    assert detail.open_reservation == 0
    assert detail.supply_need == 0


def test_export_products_csv_and_xlsx() -> None:
    uow = FakeUnitOfWork()
    p1 = Product(
        id=uuid.uuid4(),
        name="07325 A",
        name_normalized="07325 a",
        regular_price=Decimal("38099.00"),
        website_discounted_price=Decimal("34099.00"),
        physical_stock=5,
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
    assert "07325 A,38099.00,34099.00,5," in csv_text
    assert "09325 A,42199.00,,0," in csv_text

    # 2. Test XLSX export
    xlsx_bytes = export_products_xlsx(uow)
    assert xlsx_bytes.startswith(b"PK")  # ZIP signature of xlsx
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0] == (
        "product_name",
        "regular_price",
        "website_discounted_price",
        "quantity",
        "cost_price",
    )
    assert rows[1][0] == "07325 A"
    assert rows[1][1] == 38099.00
    assert rows[1][2] == 34099.00
    assert rows[1][3] == 5
    wb.close()
