from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from openpyxl import Workbook, load_workbook

from bayios.adapters.db.models.products import Product
from bayios.application.imports.reservations import (
    commit_reservation_import,
    preview_reservation_import,
)
from bayios.application.reservations import NewReservationItem, create_reservation
from bayios.application.reservations.io import export_reservations_xlsx
from tests.fakes import FakeUnitOfWork


def _fixture() -> tuple[FakeUnitOfWork, Product]:
    uow = FakeUnitOfWork()
    product = Product(
        id=uuid.uuid4(),
        name="Buzdolabı",
        name_normalized="buzdolabı",
        regular_price=Decimal(50000),
        physical_stock=1,
    )
    uow.products.add(product)
    create_reservation(
        uow,
        "Ayşe",
        (NewReservationItem(product.id, 2),),
        reservation_date=datetime(2026, 11, 10, tzinfo=UTC),
        note="Kapıda teslim",
    )
    return uow, product


def _flat_workbook(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Rezervasyonlar"
    sheet.append(
        [
            "Rezervasyon Anahtarı",
            "Müşteri Adı",
            "Rezervasyon Tarihi",
            "Hatırlatma Tarihi",
            "Ürün Adı",
            "Miktar",
        ]
    )
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def test_reservation_export_has_header_and_lines() -> None:
    uow, _product = _fixture()
    data = export_reservations_xlsx(uow)
    workbook = load_workbook(io.BytesIO(data))
    assert workbook.sheetnames == ["Rezervasyonlar", "Rezervasyon Satırları", "Kullanım"]
    assert workbook["Rezervasyonlar"]["C1"].value == "Müşteri Adı"
    assert workbook["Rezervasyon Satırları"]["C1"].value == "Ürün ID"
    assert workbook["Rezervasyon Satırları"]["D1"].value == "Ürün Adı"
    assert workbook["Rezervasyon Satırları"].max_row == 2


def test_reservation_export_round_trip_skips_existing_number() -> None:
    uow, _product = _fixture()
    data = export_reservations_xlsx(uow)
    preview = preview_reservation_import(uow, data)
    assert len(preview.rows) == 1
    assert preview.rows[0].decision == "skip"
    result = commit_reservation_import(
        uow,
        file_name="rezervasyon.xlsx",
        file_type="xlsx",
        source=data,
        decisions={},
        commit_token="res-roundtrip",
    )
    assert result.skipped_count == 1
    assert len(uow.reservations.reservations) == 1


def test_reservation_flat_import_creates_open_reservation() -> None:
    uow = FakeUnitOfWork()
    product = Product(
        id=uuid.uuid4(),
        name="Buzdolabı",
        name_normalized="buzdolabı",
        regular_price=Decimal(50000),
        physical_stock=1,
    )
    uow.products.add(product)
    data = _flat_workbook(
        [
            [
                "MUS-1",
                "Mehmet",
                "10.11.2026",
                "10.12.2027",
                "Buzdolabı",
                1,
            ]
        ]
    )
    preview = preview_reservation_import(uow, data)
    assert not preview.rows[0].errors, preview.rows[0].errors
    result = commit_reservation_import(
        uow,
        file_name="rezervasyon.xlsx",
        file_type="xlsx",
        source=data,
        decisions={},
        commit_token="res-flat",
    )
    assert result.created_count == 1
    assert len(uow.reservations.reservations) == 1
    reservation = next(iter(uow.reservations.reservations.values()))
    assert reservation.customer_name == "Mehmet"
    assert reservation.reservation_date.date().isoformat() == "2026-11-10"
    assert reservation.reminder_due_at.date().isoformat() == "2027-12-10"


def test_reservation_import_resolves_product_by_external_id_before_name() -> None:
    uow, product = _fixture()
    product.external_id = "9000"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Rezervasyonlar"
    sheet.append(
        [
            "Rezervasyon Anahtarı",
            "Müşteri Adı",
            "Rezervasyon Tarihi",
            "Ürün ID",
            "Ürün Adı",
            "Miktar",
        ]
    )
    sheet.append(
        [
            "res-id",
            "Ayşe",
            "10.11.2026",
            "9000",
            "Tamamen Farkli Ad",
            1,
        ]
    )
    stream = io.BytesIO()
    workbook.save(stream)
    data = stream.getvalue()

    preview = preview_reservation_import(uow, data)
    assert not preview.rows[0].errors, preview.rows[0].errors

    sheet.cell(row=2, column=4, value="9999")
    stream = io.BytesIO()
    workbook.save(stream)
    missing = preview_reservation_import(uow, stream.getvalue())
    assert any("Ürün ID bulunamadı" in error for error in missing.rows[0].errors)


def test_reservation_import_resolves_old_product_id_alias() -> None:
    from bayios.adapters.db.models.products import ProductExternalIdHistory

    uow, product = _fixture()
    product.external_id = "9000"
    uow.products.add_external_id_history(
        ProductExternalIdHistory(
            id=uuid.uuid4(),
            product_id=product.id,
            external_id="8000",
        )
    )
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Rezervasyonlar"
    sheet.append(
        [
            "Rezervasyon Anahtarı",
            "Müşteri Adı",
            "Rezervasyon Tarihi",
            "Ürün ID",
            "Ürün Adı",
            "Miktar",
        ]
    )
    sheet.append(["alias-res", "Ayşe", "10.11.2026", "8000", "Eski Ad", 1])
    stream = io.BytesIO()
    workbook.save(stream)

    preview = preview_reservation_import(uow, stream.getvalue())

    assert not preview.rows[0].errors, preview.rows[0].errors
