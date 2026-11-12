from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from bayios.application.imports.common import (
    ImportPreview,
    ImportResult,
    PreviewRow,
    record_batch,
    replay_result,
)
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.reservations import NewReservationItem, create_reservation
from bayios.application.tabular import (
    first_sheet,
    locate_header,
    parse_date,
    parse_decimal,
    parse_int,
    read_raw_sheets,
    row_value,
    sheet_named,
)
from bayios.domain.products import ActorContext, normalize_product_name

RESERVATION_HEADERS = {
    "reservation_number": ("Rezervasyon No", "Rezervasyon Numarası", "reservation_number"),
    "reservation_key": ("Rezervasyon Anahtarı", "Rezervasyon Anahtari", "reservation_key"),
    "customer_name": ("Müşteri Adı", "Musteri Adi", "customer_name"),
    "reservation_date": ("Rezervasyon Tarihi", "reservation_date"),
    "reminder_due_at": ("Hatırlatma Tarihi", "reminder_due_at"),
    "note": ("Not", "note"),
    "product_name": ("Ürün Adı", "Urun Adi", "product_name"),
    "quantity": ("Miktar", "Adet", "quantity"),
}
ITEM_HEADERS = {
    "reservation_number": ("Rezervasyon No", "Rezervasyon Numarası", "reservation_number"),
    "reservation_key": ("Rezervasyon Anahtarı", "Rezervasyon Anahtari", "reservation_key"),
    "product_name": ("Ürün Adı", "Urun Adi", "product_name"),
    "quantity": ("Miktar", "Adet", "quantity"),
    "note": ("Satır Notu", "note"),
}
DECISION_OPTIONS = (("skip", "Atla"),)


@dataclass(frozen=True)
class _ReservationEntity:
    key: str
    row_number: int
    reservation_number: int | None
    existing: bool
    customer_name: str
    reservation_date: datetime | None
    item_count: int
    items: tuple[NewReservationItem, ...]
    note: str | None
    reminder_due_at: datetime | None
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    decision: str


def preview_reservation_import(uow: UnitOfWork, source: bytes) -> ImportPreview:
    entities, unknown = _parse_reservations(uow, source)
    return ImportPreview(
        module="reservations",
        title="Rezervasyon Excel İçe Aktarma Önizlemesi",
        entity_label="rezervasyon",
        columns=(
            ("reservation_no", "Rezervasyon No"),
            ("customer", "Müşteri"),
            ("date", "Rezervasyon Tarihi"),
            ("items", "Ürün"),
            ("status", "Durum"),
        ),
        rows=tuple(
            PreviewRow(
                key=entity.key,
                row_number=entity.row_number,
                decision=entity.decision,
                summary=entity.customer_name,
                values={
                    "reservation_no": entity.reservation_number or "",
                    "customer": entity.customer_name,
                    "date": (
                        entity.reservation_date.strftime("%d.%m.%Y")
                        if entity.reservation_date
                        else ""
                    ),
                    "items": entity.item_count,
                    "status": "Mevcut (atlanacak)" if entity.existing else "Yeni",
                },
                errors=entity.errors,
                warnings=entity.warnings,
            )
            for entity in entities
        ),
        decision_options=DECISION_OPTIONS,
        unknown_headers=unknown,
    )


def commit_reservation_import(
    uow: UnitOfWork,
    *,
    file_name: str,
    file_type: str,
    source: bytes,
    decisions: dict[str, str],
    actor: ActorContext | None = None,
    commit_token: str | None = None,
) -> ImportResult:
    actor = actor or ActorContext()
    entities = _parse_reservations(uow, source)[0]
    with uow:
        replay = replay_result(uow, "reservations", commit_token)
        if replay is not None:
            return replay
    created = skipped = errors = 0
    for entity in entities:
        if entity.existing:
            skipped += 1
            continue
        if entity.errors or entity.reservation_date is None or not entity.items:
            errors += 1
            continue
        if (decisions.get(entity.key) or entity.decision) == "skip":
            skipped += 1
            continue
        view = create_reservation(
            uow,
            customer_name=entity.customer_name,
            items=entity.items,
            reservation_date=entity.reservation_date,
            note=entity.note,
            actor=actor,
        )
        if entity.reminder_due_at is not None:
            with uow:
                row = uow.reservations.get(view.id)
                if row is not None:
                    row.reminder_due_at = entity.reminder_due_at
                    uow.commit()
        created += 1
    now = datetime.now(UTC)
    with uow:
        result = record_batch(
            uow,
            module="reservations",
            file_name=file_name,
            file_type=file_type,
            source=source,
            commit_token=commit_token,
            created_count=created,
            updated_count=0,
            skipped_count=skipped,
            error_count=errors,
            total_count=len(entities),
            actor=actor,
            now=now,
        )
        uow.commit()
    return result


def _parse_reservations(
    uow: UnitOfWork, source: bytes
) -> tuple[list[_ReservationEntity], tuple[str, ...]]:
    sheets = read_raw_sheets(source)
    reservation_sheet = sheet_named(
        sheets, ("Rezervasyonlar", "Reservations", "Rezervasyon")
    ) or first_sheet(sheets)
    reservation_layout = locate_header(
        reservation_sheet.rows,
        RESERVATION_HEADERS,
        required=("customer_name", "reservation_date"),
        sheet_label=reservation_sheet.name,
    )
    flat = "product_name" in reservation_layout.indexes
    item_sheet = sheet_named(
        sheets, ("Rezervasyon Satırları", "Rezervasyon Satirlari", "Reservation Items")
    )
    item_layout = None
    if item_sheet is not None:
        item_layout = locate_header(
            item_sheet.rows,
            ITEM_HEADERS,
            required=("product_name",),
            sheet_label=item_sheet.name,
        )
    warnings = tuple(
        f"Tanınmayan kolon: {header}" for header in reservation_layout.unknown_headers
    )
    grouped: dict[str, dict[str, object]] = {}
    order: list[str] = []

    def key_for(raw, layout) -> str:
        number = row_value(raw, layout, "reservation_number")
        if number not in (None, ""):
            try:
                return f"no:{int(parse_decimal(number, 'Rezervasyon No'))}"
            except ValueError:
                return ""
        key = str(row_value(raw, layout, "reservation_key") or "").strip()
        return f"key:{key}" if key else ""

    for offset, raw in enumerate(
        reservation_sheet.rows[reservation_layout.row_index + 1 :], start=1
    ):
        key = key_for(raw, reservation_layout)
        if not key:
            continue
        if key not in grouped:
            grouped[key] = {
                "row_number": reservation_layout.row_index + 2 + offset,
                "raw": raw,
                "items": [],
                "errors": [],
            }
            order.append(key)
        if flat:
            grouped[key]["items"].append(  # type: ignore[index]
                {
                    "product_name": row_value(raw, reservation_layout, "product_name"),
                    "quantity": row_value(raw, reservation_layout, "quantity"),
                    "note": row_value(raw, reservation_layout, "note"),
                }
            )
    if item_sheet is not None and item_layout is not None:
        for raw in item_sheet.rows[item_layout.row_index + 1 :]:
            key = key_for(raw, item_layout)
            if key not in grouped:
                continue
            grouped[key]["items"].append(  # type: ignore[index]
                {
                    "product_name": row_value(raw, item_layout, "product_name"),
                    "quantity": row_value(raw, item_layout, "quantity"),
                    "note": row_value(raw, item_layout, "note"),
                }
            )

    with uow:
        existing_rows, _ = uow.reservations.list(limit=10_000, offset=0)
        existing_by_number = {
            reservation.reservation_number: reservation
            for reservation in existing_rows
        }
        entities: list[_ReservationEntity] = []
        for key in order:
            group = grouped[key]
            raw = group["raw"]
            assert isinstance(raw, tuple)
            errors: list[str] = list(group["errors"])  # type: ignore[arg-type]
            reservation_number = None
            number_raw = row_value(raw, reservation_layout, "reservation_number")
            if number_raw not in (None, ""):
                try:
                    reservation_number = int(
                        parse_decimal(number_raw, "Rezervasyon No")
                    )
                except ValueError as exc:
                    errors.append(str(exc))
            existing = (
                existing_by_number.get(reservation_number)
                if reservation_number is not None
                else None
            )
            customer_name = str(
                row_value(raw, reservation_layout, "customer_name") or ""
            ).strip()
            if not customer_name:
                errors.append("Müşteri adı zorunludur.")
            reservation_date = None
            try:
                date_value = parse_date(
                    row_value(raw, reservation_layout, "reservation_date"),
                    "Rezervasyon tarihi",
                )
                if date_value is None:
                    errors.append("Rezervasyon tarihi zorunludur.")
                else:
                    reservation_date = datetime(
                        date_value.year,
                        date_value.month,
                        date_value.day,
                        tzinfo=UTC,
                    )
            except ValueError as exc:
                errors.append(str(exc))
            reminder_due_at = None
            reminder_raw = row_value(raw, reservation_layout, "reminder_due_at")
            if reminder_raw not in (None, ""):
                try:
                    reminder_date = parse_date(reminder_raw, "Hatırlatma tarihi")
                    if reminder_date is not None:
                        reminder_due_at = datetime(
                            reminder_date.year,
                            reminder_date.month,
                            reminder_date.day,
                            tzinfo=UTC,
                        )
                except ValueError as exc:
                    errors.append(str(exc))
            item_rows = group["items"]  # type: ignore[assignment]
            if not item_rows:
                errors.append("En az bir ürün satırı gereklidir.")
            products_by_name = uow.products.get_by_normalized_names(
                [
                    normalize_product_name(str(item["product_name"]))
                    for item in item_rows
                    if str(item["product_name"] or "").strip()
                ]
            )
            items: list[NewReservationItem] = []
            seen: set[uuid.UUID] = set()
            for item in item_rows:
                product_name = str(item["product_name"] or "").strip()
                if not product_name:
                    continue
                product = products_by_name.get(normalize_product_name(product_name))
                if product is None:
                    errors.append(f"Ürün bulunamadı: {product_name}")
                    continue
                if product.id in seen:
                    errors.append(f"Aynı ürün tekrar ediyor: {product_name}")
                    continue
                seen.add(product.id)
                try:
                    quantity = parse_int(item["quantity"], "Miktar", minimum=1) or 1
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
                items.append(NewReservationItem(product.id, quantity))
            if existing is not None:
                warnings = (*warnings, "Mevcut rezervasyon numarası atlanacak.")
            decision = "skip" if existing is not None else (
                "error" if errors else "create"
            )
            entities.append(
                _ReservationEntity(
                    key=key,
                    row_number=int(group["row_number"]),  # type: ignore[arg-type]
                    reservation_number=reservation_number,
                    existing=existing is not None,
                    customer_name=customer_name,
                    reservation_date=reservation_date,
                    item_count=len(items),
                    items=tuple(items),
                    note=str(
                        row_value(raw, reservation_layout, "note") or ""
                    ).strip()
                    or None,
                    reminder_due_at=reminder_due_at,
                    errors=tuple(errors),
                    warnings=warnings,
                    decision=decision,
                )
            )
    entities.sort(key=lambda entity: (0 if entity.errors else 1, entity.row_number))
    return entities, warnings
