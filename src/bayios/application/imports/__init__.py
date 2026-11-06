from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable


@dataclass(frozen=True)
class ProductImportRow:
    row_number: int
    decision: str
    product_name: str | None = None
    regular_price: str | None = None
    website_discounted_price: str | None = None
    quantity: str | None = None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProductImportPreview:
    rows: tuple[ProductImportRow, ...]


def preview_product_import(source: bytes) -> ProductImportPreview:
    rows: list[ProductImportRow] = []

    for row_number, raw_row in enumerate(_source_rows(source), start=2):
        product_name = _value(raw_row, "product_name", "name")
        regular_price = _value(raw_row, "regular_price", "regular price")
        discounted_price = _value(
            raw_row,
            "website_discounted_price",
            "website discounted price",
        )
        quantity = _value(raw_row, "quantity")
        errors: list[str] = []
        warnings: list[str] = []

        if not product_name:
            errors.append("Name is required")
        elif not re.fullmatch(r"[0-9A-Z]+(?: [0-9A-Z]+)*", product_name.upper()):
            warnings.append("Name format may need review")
        normalized_price = _normalize_decimal(regular_price)
        if regular_price and normalized_price is None:
            errors.append("Regular Price must be a number")
        normalized_discounted_price = _normalize_decimal(discounted_price)
        if discounted_price and normalized_discounted_price is None:
            errors.append("Website Discounted Price must be a number")
        normalized_quantity = _normalize_quantity(quantity)
        if quantity and normalized_quantity is None:
            errors.append("Quantity must be a non-negative integer")

        rows.append(
            ProductImportRow(
                row_number=row_number,
                decision="error" if errors else "create",
                product_name=product_name or None,
                regular_price=normalized_price,
                website_discounted_price=normalized_discounted_price,
                quantity=normalized_quantity,
                errors=tuple(errors),
                warnings=tuple(warnings),
            )
        )

    return ProductImportPreview(rows=tuple(rows))


def _source_rows(source: bytes) -> Iterable[dict[str, str | None]]:
    if source.startswith(b"PK"):
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(source), read_only=True, data_only=True)
        try:
            rows = workbook.active.iter_rows(values_only=True)
            headers = [str(value or "").strip() for value in next(rows)]
            for values in rows:
                yield dict(zip(headers, (None if value is None else str(value) for value in values)))
        finally:
            workbook.close()
        return

    text = _decode_source(source)
    reader = csv.DictReader(io.StringIO(text), delimiter=_detect_delimiter(text))
    yield from reader


def _decode_source(source: bytes) -> str:
    try:
        return source.decode("utf-8-sig")
    except UnicodeDecodeError:
        return source.decode("cp1254").lstrip("\ufeffï»¿")


def _detect_delimiter(text: str) -> str:
    sample = text.splitlines()[0] if text.splitlines() else ""
    return ";" if sample.count(";") > sample.count(",") else ","


def _value(row: dict[str, str | None], *headers: str) -> str:
    for key, value in row.items():
        normalized_key = key.strip().casefold().replace(" ", "_") if key else ""
        if normalized_key in headers:
            return (value or "").strip()
    return ""


def _normalize_decimal(value: str) -> str | None:
    if not value:
        return None
    candidate = value.replace(" ", "").replace(",", ".")
    try:
        number = Decimal(candidate)
    except InvalidOperation:
        return None
    return format(number, "f")


def _normalize_quantity(value: str) -> str | None:
    if not value:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if number < 0 or number != number.to_integral_value():
        return None
    return format(number, "f").split(".")[0]
