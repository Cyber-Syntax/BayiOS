from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from bayios.adapters.db.models.reservations import (
    Reservation,
    ReservationItem,
    ReservationItemEvent,
)
from bayios.application.errors import ImportFormatError
from bayios.application.imports.common import (
    ImportPreview,
    ImportResult,
    PreviewRow,
    ProductLookup,
    record_batch,
    replay_result,
)
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.reservations import STATUS_LABELS
from bayios.domain.naming import normalize_name
from bayios.domain.products import ActorContext
from bayios.domain.reservations import (
    ReminderStatus,
    ReservationStatus,
    initial_reminder_due,
)

DECISION_OPTIONS = (("skip", "Atla"),)


@dataclass(frozen=True)
class _ReservationJson:
    key: str
    row_number: int
    reservation_number: int | None
    existing: bool
    customer_name: str
    reservation_date: datetime
    reminder_due_at: datetime
    reminder_status: str
    note: str | None
    created_at: datetime | None
    item_count: int
    summary: str
    items: tuple[_ReservationJsonItem, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    decision: str


@dataclass(frozen=True)
class _ReservationJsonItem:
    product_id: uuid.UUID | None
    product_name: str
    quantity: int
    delivered_quantity: int
    cancelled_quantity: int
    status: str
    service_date: datetime | None
    other_dealer_note: str | None
    note: str | None


def preview_reservation_json(uow: UnitOfWork, source: bytes) -> ImportPreview:
    with uow:
        reservations = _parse_json(uow, source)
    return ImportPreview(
        module="reservations",
        title="Rezervasyon JSON İçe Aktarma Önizlemesi",
        entity_label="rezervasyon",
        columns=(
            ("reservation_no", "Rezervasyon No"),
            ("customer", "Müşteri"),
            ("date", "Tarih"),
            ("items", "Ürün"),
            ("summary", "Durum"),
        ),
        rows=tuple(
            PreviewRow(
                key=reservation.key,
                row_number=reservation.row_number,
                decision=reservation.decision,
                summary=reservation.customer_name,
                values={
                    "reservation_no": reservation.reservation_number or "—",
                    "customer": reservation.customer_name,
                    "date": reservation.reservation_date.strftime("%d.%m.%Y"),
                    "items": reservation.item_count,
                    "summary": reservation.summary,
                },
                errors=reservation.errors,
                warnings=reservation.warnings,
            )
            for reservation in reservations
        ),
        decision_options=DECISION_OPTIONS,
    )


def commit_reservation_json(
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
    with uow:
        replay = replay_result(uow, "reservations", commit_token)
        if replay is not None:
            return replay
        reservations = _parse_json(uow, source)
        now = datetime.now(UTC)
        created = skipped = errors = 0
        for reservation in reservations:
            if reservation.errors:
                errors += 1
                continue
            decision = decisions.get(reservation.key) or reservation.decision
            if decision == "skip" or reservation.existing:
                skipped += 1
                continue
            row = Reservation(
                id=uuid.uuid4(),
                customer_name=reservation.customer_name,
                reservation_date=reservation.reservation_date,
                reminder_due_at=reservation.reminder_due_at,
                reminder_status=reservation.reminder_status,
                note=reservation.note,
                created_at=reservation.created_at or now,
                updated_at=now,
                created_by_name=actor.worker_name,
                created_by_device=actor.device_name,
            )
            uow.reservations.add(row)
            items = [
                ReservationItem(
                    id=uuid.uuid4(),
                    reservation_id=row.id,
                    product_id=item.product_id,
                    product_name_snapshot=item.product_name,
                    quantity=item.quantity,
                    delivered_quantity=item.delivered_quantity,
                    cancelled_quantity=item.cancelled_quantity,
                    status=item.status,
                    service_date=item.service_date,
                    other_dealer_note=item.other_dealer_note,
                    note=item.note,
                    created_at=now,
                    updated_at=now,
                )
                for item in reservation.items
            ]
            uow.reservations.add_items(items)
            for item in items:
                uow.reservations.add_event(
                    ReservationItemEvent(
                        id=uuid.uuid4(),
                        reservation_item_id=item.id,
                        old_status=None,
                        new_status=item.status,
                        quantity_delta=None,
                        note="JSON içe aktarıldı",
                        event_at=now,
                        created_by_name=actor.worker_name,
                        created_by_device=actor.device_name,
                    )
                )
            created += 1
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
            total_count=len(reservations),
            actor=actor,
            now=now,
        )
        uow.commit()
        return result


def _parse_json(uow: UnitOfWork, source: bytes) -> list[_ReservationJson]:
    try:
        payload = json.loads(source.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportFormatError(
            "Rezervasyon JSON dosyası okunamadı; geçerli bir JSON yükleyin."
        ) from exc
    if not isinstance(payload, dict):
        raise ImportFormatError("Rezervasyon JSON dosyası nesne olmalıdır.")
    if str(payload.get("schema_version") or "").strip() != "1.0":
        raise ImportFormatError(
            "Desteklenmeyen rezervasyon şeması; schema_version 1.0 olmalıdır."
        )
    raw_reservations = payload.get("reservations")
    if not isinstance(raw_reservations, list):
        raise ImportFormatError(
            "Rezervasyon JSON dosyasında reservations listesi yok."
        )

    existing_rows, _total = uow.reservations.list(limit=10_000, offset=0)
    existing_numbers = {
        row.reservation_number for row in existing_rows
    }
    lookup = ProductLookup.load(uow)
    seen_numbers: set[int] = set()
    parsed: list[_ReservationJson] = []
    for offset, raw in enumerate(raw_reservations, start=2):
        if not isinstance(raw, dict):
            parsed.append(
                _error_reservation(offset, "Rezervasyon JSON satırı nesne olmalıdır.")
            )
            continue
        parsed.append(
            _parse_one(
                raw,
                row_number=offset,
                lookup=lookup,
                existing_numbers=existing_numbers,
                seen_numbers=seen_numbers,
            )
        )
    return parsed


def _parse_one(
    raw: dict[str, Any],
    *,
    row_number: int,
    lookup: ProductLookup,
    existing_numbers: set[int],
    seen_numbers: set[int],
) -> _ReservationJson:
    errors: list[str] = []
    warnings: list[str] = []
    reservation_number = _int_or_none(raw.get("reservation_number"))
    existing = (
        reservation_number is not None
        and reservation_number in existing_numbers
    )
    if reservation_number is not None and reservation_number in seen_numbers:
        errors.append("Aynı rezervasyon numarası dosyada tekrar ediyor; ilk kayıt işlendi.")
    if reservation_number is not None:
        seen_numbers.add(reservation_number)
    customer_name = _text(raw.get("customer_name"))
    if not customer_name:
        errors.append("Müşteri adı zorunludur.")

    reservation_date = _datetime(raw.get("reservation_date"), errors, "Rezervasyon tarihi")
    if reservation_date is None:
        errors.append("Rezervasyon tarihi zorunludur.")
        reservation_date = datetime.now(UTC)
    reminder_due_at = _datetime(raw.get("reminder_due_at"), warnings, "Hatırlatma tarihi")
    if reminder_due_at is None:
        reminder_due_at = initial_reminder_due(reservation_date)
    reminder_status = _text(raw.get("reminder_status")) or ReminderStatus.PENDING.value
    if reminder_status not in {item.value for item in ReminderStatus}:
        warnings.append(f"Hatırlatma durumu geçersiz; pending kullanılacak: {reminder_status}")
        reminder_status = ReminderStatus.PENDING.value

    raw_items = raw.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        errors.append("Rezervasyonda en az bir ürün satırı olmalıdır.")
        raw_items = []
    items: list[_ReservationJsonItem] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            errors.append("Rezervasyon ürün satırı nesne olmalıdır.")
            continue
        product_name = _text(raw_item.get("product_name"))
        product_id_text = _text(raw_item.get("product_id")) or None
        product = _resolve_product(lookup, product_id_text, product_name)
        if product is None:
            errors.append(f"Ürün bulunamadı: {product_name or product_id_text or '—'}")
            continue
        quantity = _int_or_none(raw_item.get("quantity"))
        delivered = _int_or_none(raw_item.get("delivered_quantity")) or 0
        cancelled = _int_or_none(raw_item.get("cancelled_quantity")) or 0
        if quantity is None or quantity <= 0:
            errors.append(f"Miktar geçersiz: {product_name}")
            continue
        if delivered < 0 or cancelled < 0 or delivered + cancelled > quantity:
            errors.append(f"Teslim/iptal miktarı toplamı geçersiz: {product_name}")
            continue
        status = _text(raw_item.get("status")) or ""
        if status not in {item.value for item in ReservationStatus}:
            if cancelled >= quantity:
                status = ReservationStatus.CANCELLED.value
            elif delivered >= quantity:
                status = ReservationStatus.DELIVERED.value
            elif delivered or cancelled:
                status = ReservationStatus.DELIVERY_REQUESTED.value
            else:
                status = ReservationStatus.RESERVED.value
        items.append(
            _ReservationJsonItem(
                product_id=product.id,
                product_name=product.name,
                quantity=quantity,
                delivered_quantity=delivered,
                cancelled_quantity=cancelled,
                status=status,
                service_date=_datetime(
                    raw_item.get("service_date"), warnings, "Servis tarihi"
                ),
                other_dealer_note=_text(raw_item.get("other_dealer_note")) or None,
                note=_text(raw_item.get("note")) or None,
            )
        )
    if not items:
        errors.append("Eşleşen ürün satırı yok; rezervasyon aktarılamaz.")

    summary = " · ".join(
        f"{item.product_name} ({STATUS_LABELS.get(ReservationStatus(item.status), item.status)})"
        for item in items
    )
    decision = "error" if errors else ("skip" if existing else "create")
    return _ReservationJson(
        key=str(reservation_number or f"row:{row_number}"),
        row_number=row_number,
        reservation_number=reservation_number,
        existing=existing,
        customer_name=customer_name,
        reservation_date=reservation_date,
        reminder_due_at=reminder_due_at,
        reminder_status=reminder_status,
        note=_text(raw.get("note")) or None,
        created_at=_datetime(raw.get("created_at"), warnings, "Oluşturma tarihi"),
        item_count=len(items),
        summary=summary,
        items=tuple(items),
        errors=tuple(errors),
        warnings=tuple(warnings),
        decision=decision,
    )


def _error_reservation(row_number: int, message: str) -> _ReservationJson:
    now = datetime.now(UTC)
    return _ReservationJson(
        key=f"row:{row_number}",
        row_number=row_number,
        reservation_number=None,
        existing=False,
        customer_name="",
        reservation_date=now,
        reminder_due_at=now,
        reminder_status=ReminderStatus.PENDING.value,
        note=None,
        created_at=None,
        item_count=0,
        summary="",
        items=(),
        errors=(message,),
        warnings=(),
        decision="error",
    )


def _resolve_product(lookup: ProductLookup, product_id: str | None, name: str) -> Any:
    if product_id:
        product = lookup.by_external_id.get(product_id) or lookup.by_alias.get(
            product_id
        )
        if product is not None:
            return product
        if _is_uuid(product_id):
            product = lookup.by_id.get(uuid.UUID(product_id))
            if product is not None:
                return product
    if not name:
        return None
    matches = lookup.by_name.get(normalize_name(name), ())
    return matches[0] if len(matches) == 1 else None


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def _text(value: object) -> str:
    return str(value or "").strip()


def _int_or_none(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed


def _datetime(
    value: object, messages: list[str], label: str
) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        messages.append(f"{label} geçersiz: {text}")
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
