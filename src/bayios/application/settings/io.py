from __future__ import annotations

import uuid

from bayios.adapters.db.models.commissions import Bank
from bayios.adapters.db.models.products import ProductCategory
from bayios.application.errors import ValidationError
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.settings import MasterImportResult
from bayios.application.tabular import (
    ColumnSpec,
    SheetSpec,
    first_sheet,
    locate_header,
    normalize_header,
    read_raw_sheets,
    row_value,
    write_xlsx,
)
from bayios.domain.commissions import commission_group_for_category_name
from bayios.domain.naming import canonical_display_name, normalize_name

BANK_HEADERS = {
    "name": ("Banka", "Bank", "name"),
    "active": ("Aktif", "Durum", "active"),
}
CATEGORY_HEADERS = {
    "name": ("Kategori", "Category", "name"),
    "group": ("Komisyon Grubu", "Grup", "commission_group"),
}
_TRUE_VALUES = {"evet", "e", "1", "true", "aktif", "active"}
_FALSE_VALUES = {"hayir", "h", "0", "false", "pasif", "inactive"}


def export_banks_xlsx(uow: UnitOfWork) -> bytes:
    with uow:
        banks = uow.commissions.get_banks(active_only=False)
        rows = [
            {
                "name": bank.name,
                "active": "Evet" if bank.is_active else "Hayır",
            }
            for bank in banks
        ]
    sheet = SheetSpec(
        title="Bankalar",
        columns=(
            ColumnSpec("Banka", "name", "text", 28),
            ColumnSpec("Aktif", "active", "text", 10),
        ),
        rows=rows,
        instructions=(
            ("Banka", "Zorunlu", "Banka adı; normalize edilerek eşleştirilir."),
            ("Aktif", "Opsiyonel", "Evet/Hayır; boşsa mevcut değer korunur."),
        ),
    )
    return write_xlsx((sheet,))


def export_categories_xlsx(uow: UnitOfWork) -> bytes:
    with uow:
        categories = uow.products.get_categories()
        rows = [
            {
                "name": category.name,
                "group": "Klima"
                if category.commission_group == "klima"
                else "Diğer",
            }
            for category in categories
        ]
    sheet = SheetSpec(
        title="Kategoriler",
        columns=(
            ColumnSpec("Kategori", "name", "text", 28),
            ColumnSpec("Komisyon Grubu", "group", "text", 16),
        ),
        rows=rows,
        instructions=(
            ("Kategori", "Zorunlu", "Kategori adı; normalize edilerek eşleştirilir."),
            ("Komisyon Grubu", "Opsiyonel", "Klima veya Diğer; boşsa korunur."),
        ),
    )
    return write_xlsx((sheet,))


def _parse_active(value: object) -> bool | None:
    text = normalize_header(value)
    if not text:
        return None
    if text in {normalize_header(item) for item in _TRUE_VALUES}:
        return True
    if text in {normalize_header(item) for item in _FALSE_VALUES}:
        return False
    raise ValueError("Aktif değeri Evet/Hayır olmalıdır.")


def _parse_group(value: object) -> str | None:
    text = normalize_header(value)
    if not text:
        return None
    if text in {"klima", "k"}:
        return "klima"
    if text in {"diger", "other", "d"}:
        return "other"
    raise ValueError("Komisyon grubu Klima veya Diğer olmalıdır.")


def import_banks_xlsx(uow: UnitOfWork, source: bytes) -> MasterImportResult:
    sheet = first_sheet(read_raw_sheets(source))
    layout = locate_header(
        sheet.rows, BANK_HEADERS, required=("name",), sheet_label=sheet.name
    )
    parsed: list[tuple[int, str, str, bool | None]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for offset, raw in enumerate(sheet.rows[layout.row_index + 1 :], start=1):
        row_number = layout.row_index + 2 + offset
        name = str(row_value(raw, layout, "name") or "").strip()
        if not name:
            continue
        canonical = canonical_display_name(name, always_title=True)
        normalized = normalize_name(canonical)
        if normalized in seen:
            errors.append(f"Satır {row_number}: aynı banka birden fazla kez var.")
            continue
        seen.add(normalized)
        try:
            active = _parse_active(row_value(raw, layout, "active"))
        except ValueError as exc:
            errors.append(f"Satır {row_number}: {exc}")
            continue
        parsed.append((row_number, canonical, normalized, active))
    if errors:
        raise ValidationError(" ".join(errors[:5]))
    created = updated = skipped = 0
    with uow:
        for _row, canonical, normalized, active in parsed:
            existing = uow.commissions.get_bank_by_normalized(normalized)
            if existing is None:
                uow.commissions.add_bank(
                    Bank(
                        id=uuid.uuid4(),
                        name=canonical,
                        name_normalized=normalized,
                        is_active=True if active is None else active,
                    )
                )
                created += 1
                continue
            if existing.name != canonical:
                existing.name = canonical
            if active is not None and existing.is_active != active:
                existing.is_active = active
            updated += 1
        uow.commit()
    return MasterImportResult(
        created=created, updated=updated, skipped=skipped
    )


def import_categories_xlsx(
    uow: UnitOfWork, source: bytes
) -> MasterImportResult:
    sheet = first_sheet(read_raw_sheets(source))
    layout = locate_header(
        sheet.rows,
        CATEGORY_HEADERS,
        required=("name",),
        sheet_label=sheet.name,
    )
    parsed: list[tuple[int, str, str, str | None]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for offset, raw in enumerate(sheet.rows[layout.row_index + 1 :], start=1):
        row_number = layout.row_index + 2 + offset
        name = str(row_value(raw, layout, "name") or "").strip()
        if not name:
            continue
        canonical = canonical_display_name(name)
        normalized = normalize_name(canonical)
        if normalized in seen:
            errors.append(f"Satır {row_number}: aynı kategori birden fazla kez var.")
            continue
        seen.add(normalized)
        try:
            group = _parse_group(row_value(raw, layout, "group"))
        except ValueError as exc:
            errors.append(f"Satır {row_number}: {exc}")
            continue
        parsed.append((row_number, canonical, normalized, group))
    if errors:
        raise ValidationError(" ".join(errors[:5]))
    created = updated = skipped = 0
    with uow:
        for _row, canonical, normalized, group in parsed:
            existing = uow.products.get_category_by_normalized(normalized)
            if existing is None:
                uow.products.add_category(
                    ProductCategory(
                        id=uuid.uuid4(),
                        name=canonical,
                        name_normalized=normalized,
                        commission_group=(
                            group
                            or commission_group_for_category_name(
                                canonical
                            ).value
                        ),
                    )
                )
                created += 1
                continue
            if existing.name != canonical:
                existing.name = canonical
            if group is not None and existing.commission_group != group:
                existing.commission_group = group
            updated += 1
        uow.commit()
    return MasterImportResult(
        created=created, updated=updated, skipped=skipped
    )
