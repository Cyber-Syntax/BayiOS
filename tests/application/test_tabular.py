from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal

from openpyxl import load_workbook

from bayios.application.tabular import (
    CLEAR,
    ColumnSpec,
    SheetSpec,
    normalize_header,
    parse_bool,
    parse_date,
    parse_decimal,
    parse_optional_decimal,
    read_raw_sheets,
    write_xlsx,
)


def test_normalize_header_handles_turkish_and_ascii_variants() -> None:
    assert normalize_header("Ürün Adı") == "urun adi"
    assert normalize_header("Urun Adi") == "urun adi"
    assert normalize_header("Kredi Kartı Taban Fiyatı") == (
        "kredi karti taban fiyati"
    )


def test_parse_turkish_money_dates_and_booleans() -> None:
    assert parse_decimal("38.099,50 TL", "Fiyat") == Decimal("38099.50")
    assert parse_decimal("12,50", "Fiyat") == Decimal("12.50")
    assert parse_date("10.11.2026", "Tarih") == date(2026, 11, 10)
    assert parse_date(datetime(2026, 11, 10, 9, 30), "Tarih") == date(
        2026, 11, 10
    )
    assert parse_bool("Evet", "Durum") is True
    assert parse_bool("hayır", "Durum") is False


def test_clear_sentinel_is_distinct_from_blank() -> None:
    assert parse_optional_decimal("", "Fiyat") is None
    assert parse_optional_decimal("-", "Fiyat") is CLEAR
    assert parse_optional_decimal("temizle", "Fiyat") is CLEAR


def test_write_and_read_xlsx_preserves_text_and_values() -> None:
    sheet = SheetSpec(
        title="Test",
        columns=(
            ColumnSpec("Ürün Adı", "name", "text"),
            ColumnSpec("Fiyat", "price", "money"),
            ColumnSpec("Tarih", "date", "date"),
        ),
        rows=(
            {
                "name": "07325 A",
                "price": Decimal("123.45"),
                "date": date(2026, 11, 10),
            },
        ),
        instructions=(("Ürün Adı", "Zorunlu", "Metin"),),
    )
    data = write_xlsx((sheet,))
    sheets = read_raw_sheets(data)
    assert sheets[0].name == "Test"
    assert sheets[0].rows[0] == ("Ürün Adı", "Fiyat", "Tarih")
    assert sheets[0].rows[1][0] == "07325 A"
    assert sheets[0].rows[1][1] == 123.45
    assert sheets[0].rows[1][2].date() == date(2026, 11, 10)


def test_write_xlsx_writes_formula_like_text_as_string() -> None:
    sheet = SheetSpec(
        title="Test",
        columns=(ColumnSpec("Ad", "name", "text"),),
        rows=({"name": "=SUM(A1)"},),
    )
    data = write_xlsx((sheet,))
    workbook = load_workbook(io.BytesIO(data))
    cell = workbook.active["A2"]
    assert cell.value == "=SUM(A1)"
    assert cell.data_type == "s"
