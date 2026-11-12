from __future__ import annotations

import io
import uuid

from openpyxl import Workbook, load_workbook

from bayios.adapters.db.models.commissions import Bank
from bayios.application.commissions.io import (
    export_commission_limits_xlsx,
    export_commission_rates_xlsx,
)
from bayios.application.imports.commissions import (
    commit_commission_limits,
    commit_commission_rates,
    preview_commission_limits,
    preview_commission_rates,
)
from tests.fakes import FakeUnitOfWork


def _workbook(headers: list[str], rows: list[list[object]], title: str) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _uow_with_bank() -> FakeUnitOfWork:
    uow = FakeUnitOfWork()
    uow.commissions.add_bank(Bank(id=uuid.uuid4(), name="Yapı Kredi"))
    return uow


def test_commission_exports_are_separate_files() -> None:
    uow = _uow_with_bank()
    rates = export_commission_rates_xlsx(uow)
    limits = export_commission_limits_xlsx(uow)
    rates_wb = load_workbook(io.BytesIO(rates))
    limits_wb = load_workbook(io.BytesIO(limits))
    assert rates_wb.sheetnames == ["Komisyon Oranları", "Kullanım"]
    assert limits_wb.sheetnames == ["Taksit Limitleri", "Kullanım"]
    assert rates_wb.active["A1"].value == "Dönem"
    assert limits_wb.active["F1"].value == "Max Taksit"


def test_commission_rate_import_creates_draft_period_and_rate() -> None:
    uow = _uow_with_bank()
    data = _workbook(
        ["Dönem", "Kanal", "Banka", "Ürün Grubu", "Ödero Bandı", "Taksit", "Oran %"],
        [["2026-11", "POS", "Yapı Kredi", "Klima", "", 3, 2.5]],
        "Komisyon Oranları",
    )
    preview = preview_commission_rates(uow, data)
    assert not preview.rows[0].errors
    result = commit_commission_rates(
        uow,
        file_name="oranlar.xlsx",
        file_type="xlsx",
        source=data,
        decisions={},
        commit_token="rates-1",
    )
    assert result.created_count == 1
    assert len(uow.commissions.periods) == 1
    period = next(iter(uow.commissions.periods.values()))
    assert period.period_key == "2026-11"
    assert period.status == "draft"
    assert len(uow.commissions.rates) == 1


def test_commission_limit_import_upserts_limit() -> None:
    uow = _uow_with_bank()
    data = _workbook(
        ["Dönem", "Kanal", "Banka", "Ürün Grubu", "Kart Tipi", "Max Taksit"],
        [["2026-11", "POS", "Yapı Kredi", "Klima", "Bireysel", 6]],
        "Taksit Limitleri",
    )
    preview = preview_commission_limits(uow, data)
    assert not preview.rows[0].errors
    result = commit_commission_limits(
        uow,
        file_name="limitler.xlsx",
        file_type="xlsx",
        source=data,
        decisions={},
        commit_token="limits-1",
    )
    assert result.created_count == 1
    assert len(uow.commissions.limits) == 1


class _StrictUow(FakeUnitOfWork):
    def __init__(self) -> None:
        super().__init__()
        self._active = False

    def __enter__(self):
        if self._active:
            raise RuntimeError("UnitOfWork is already active")
        self._active = True
        return super().__enter__()

    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self._active = False


def test_commission_commit_with_existing_rates_does_not_nest_uow() -> None:
    uow = _StrictUow()
    uow.commissions.add_bank(Bank(id=uuid.uuid4(), name="Yapı Kredi"))
    data = _workbook(
        ["Dönem", "Kanal", "Banka", "Ürün Grubu", "Ödero Bandı", "Taksit", "Oran %"],
        [["2026-11", "POS", "Yapı Kredi", "Klima", "", 10, 10]],
        "Komisyon Oranları",
    )
    commit_commission_rates(
        uow,
        file_name="oranlar.xlsx",
        file_type="xlsx",
        source=data,
        decisions={},
        commit_token="first",
    )

    preview = preview_commission_rates(uow, data)
    assert preview.rows[0].decision == "skip"
    result = commit_commission_rates(
        uow,
        file_name="oranlar.xlsx",
        file_type="xlsx",
        source=data,
        decisions={},
        commit_token="second",
    )
    assert result.skipped_count == 1


def test_commission_preview_marks_new_rate_in_existing_period_as_create() -> None:
    uow = _uow_with_bank()
    first = _workbook(
        ["Dönem", "Kanal", "Banka", "Ürün Grubu", "Ödero Bandı", "Taksit", "Oran %"],
        [["2026-11", "POS", "Yapı Kredi", "Klima", "", 10, 10]],
        "Komisyon Oranları",
    )
    commit_commission_rates(
        uow,
        file_name="first.xlsx",
        file_type="xlsx",
        source=first,
        decisions={},
        commit_token="first",
    )
    second = _workbook(
        ["Dönem", "Kanal", "Banka", "Ürün Grubu", "Ödero Bandı", "Taksit", "Oran %"],
        [
            ["2026-11", "POS", "Yapı Kredi", "Klima", "", 10, 10],
            ["2026-11", "POS", "Yapı Kredi", "Klima", "", 5, 8],
        ],
        "Komisyon Oranları",
    )
    preview = preview_commission_rates(uow, second)
    assert [row.decision for row in preview.rows] == ["skip", "create"]
