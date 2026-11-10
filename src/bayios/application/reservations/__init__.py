from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from bayios.adapters.db.models.inventory import StockMovement
from bayios.adapters.db.models.reservations import (
    Reservation as ReservationRow,
)
from bayios.adapters.db.models.reservations import (
    ReservationItem as ReservationItemRow,
)
from bayios.adapters.db.models.reservations import (
    ReservationItemEvent,
    ReservationReminder,
)
from bayios.application.errors import NotFoundError, ValidationError
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.domain.products import ActorContext
from bayios.domain.reservations import (
    ReminderStatus,
    ReservationStatus,
    ReservationSummary,
    add_reservation_line,
    default_snooze_due,
    initial_reminder_due,
    next_reminder_status,
    summarize_reservation,
    transition_item,
)
from bayios.domain.reservations import (
    ReservationItem as DomainReservationItem,
)

STATUS_LABELS: Mapping[ReservationStatus, str] = {
    ReservationStatus.RESERVED: "Rezerveli",
    ReservationStatus.DELIVERY_REQUESTED: "Teslimat istendi",
    ReservationStatus.DEPOT_READY: "Depo hazır",
    ReservationStatus.SERVICE_ASSIGNED: "Servis atandı",
    ReservationStatus.DELIVERED: "Teslim edildi",
    ReservationStatus.CANCELLED: "İptal",
}

REMINDER_LABELS: Mapping[ReminderStatus, str] = {
    ReminderStatus.PENDING: "Bekliyor",
    ReminderStatus.SNOOZED: "Ertelendi",
    ReminderStatus.RESOLVED: "Tamamlandı",
}

REMINDER_OVERDUE_LABEL = "Gecikmiş"


@dataclass(frozen=True)
class NewReservationItem:
    product_id: uuid.UUID
    quantity: int


@dataclass(frozen=True)
class ReservationEventView:
    event_at: datetime
    old_status: str | None
    new_status: str
    quantity_delta: int | None
    note: str | None
    created_by_name: str | None


@dataclass(frozen=True)
class ReservationItemView:
    id: uuid.UUID
    product_id: uuid.UUID | None
    product_name: str
    quantity: int
    delivered_quantity: int
    cancelled_quantity: int
    open_quantity: int
    status: str
    status_label: str
    service_date: datetime | None
    other_dealer_note: str | None
    note: str | None
    events: tuple[ReservationEventView, ...]

    @property
    def is_terminal(self) -> bool:
        return self.open_quantity == 0


@dataclass(frozen=True)
class ReminderView:
    previous_due_at: datetime
    new_due_at: datetime
    note: str | None
    created_at: datetime
    created_by_name: str | None


@dataclass(frozen=True)
class ReservationView:
    id: uuid.UUID
    reservation_number: int | None
    customer_name: str
    reservation_date: datetime
    reminder_due_at: datetime
    reminder_status: str
    reminder_label: str
    is_overdue: bool
    note: str | None
    created_by_name: str | None
    items: tuple[ReservationItemView, ...]
    reminders: tuple[ReminderView, ...]
    summary: ReservationSummary


@dataclass(frozen=True)
class ReservationListItem:
    id: uuid.UUID
    reservation_number: int | None
    customer_name: str
    reservation_date: datetime
    reminder_due_at: datetime
    reminder_status: str
    reminder_label: str
    is_overdue: bool
    summary: ReservationSummary

    @property
    def open_quantity(self) -> int:
        return self.summary.open_quantity


def create_reservation(
    uow: UnitOfWork,
    customer_name: str,
    items: Sequence[NewReservationItem],
    reservation_date: datetime | None = None,
    note: str | None = None,
    actor: ActorContext | None = None,
) -> ReservationView:
    actor = actor or ActorContext()
    clean_name = customer_name.strip()
    if not clean_name:
        raise ValidationError("Müşteri adı zorunludur.")
    if not items:
        raise ValidationError("En az bir ürün satırı gereklidir.")

    requested: dict[uuid.UUID, int] = {}
    for item in items:
        if item.quantity <= 0:
            raise ValidationError("Ürün miktarı sıfırdan büyük olmalıdır.")
        requested[item.product_id] = requested.get(item.product_id, 0) + item.quantity

    now = datetime.now(UTC)
    moment = _ensure_utc(reservation_date) if reservation_date else now

    with uow:
        products = {
            product.id: product
            for product in uow.products.get_by_ids(list(requested))
        }
        missing = [product_id for product_id in requested if product_id not in products]
        if missing:
            raise ValidationError(
                f"{len(missing)} ürün bulunamadı; rezervasyon oluşturulmadı."
            )

        reservation = ReservationRow(
            id=uuid.uuid4(),
            customer_name=clean_name,
            reservation_date=moment,
            reminder_due_at=initial_reminder_due(moment),
            reminder_status=ReminderStatus.PENDING.value,
            note=note,
            created_by_name=actor.worker_name,
            created_by_device=actor.device_name,
        )
        uow.reservations.add(reservation)

        lines = [
            ReservationItemRow(
                id=uuid.uuid4(),
                reservation_id=reservation.id,
                product_id=product_id,
                product_name_snapshot=products[product_id].name,
                quantity=quantity,
                delivered_quantity=0,
                cancelled_quantity=0,
                status=ReservationStatus.RESERVED.value,
            )
            for product_id, quantity in requested.items()
        ]
        uow.reservations.add_items(lines)

        events = [
            _new_event(
                line,
                old_status=None,
                new_status=ReservationStatus.RESERVED,
                quantity_delta=None,
                note="Rezervasyon oluşturuldu",
                actor=actor,
                event_at=now,
            )
            for line in lines
        ]
        for event in events:
            uow.reservations.add_event(event)
        uow.commit()

        return _build_view(reservation, lines, events, (), now)


def get_reservation_detail(
    uow: UnitOfWork,
    reservation_id: uuid.UUID,
    now: datetime | None = None,
) -> ReservationView | None:
    reference = now or datetime.now(UTC)
    with uow:
        reservation = uow.reservations.get(reservation_id)
        if reservation is None:
            return None
        return _load_view(uow, reservation, reference)


def list_reservations(
    uow: UnitOfWork,
    *,
    status: str | None = None,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
    now: datetime | None = None,
) -> tuple[tuple[ReservationListItem, ...], int]:
    reference = now or datetime.now(UTC)
    with uow:
        reservations, total = uow.reservations.list(
            status=status,
            query=query,
            limit=limit,
            offset=offset,
            now=reference,
        )
        items_by_reservation = uow.reservations.get_items_for_reservations(
            [reservation.id for reservation in reservations]
        )
        return (
            tuple(
                _build_list_item(
                    reservation,
                    items_by_reservation.get(reservation.id, ()),
                    reference,
                )
                for reservation in reservations
            ),
            total,
        )


def list_home_reminders(
    uow: UnitOfWork,
    now: datetime | None = None,
    horizon_days: int = 30,
    limit: int = 10,
) -> tuple[ReservationListItem, ...]:
    reference = now or datetime.now(UTC)
    with uow:
        reservations = uow.reservations.list_reminders(
            due_before=reference + timedelta(days=horizon_days), limit=limit
        )
        items_by_reservation = uow.reservations.get_items_for_reservations(
            [reservation.id for reservation in reservations]
        )
        return tuple(
            _build_list_item(
                reservation,
                items_by_reservation.get(reservation.id, ()),
                reference,
            )
            for reservation in reservations
        )


def update_reservation(
    uow: UnitOfWork,
    reservation_id: uuid.UUID,
    customer_name: str,
    note: str | None = None,
    reservation_date: datetime | None = None,
) -> uuid.UUID:
    clean_name = customer_name.strip()
    if not clean_name:
        raise ValidationError("Müşteri adı zorunludur.")

    with uow:
        reservation = _require_reservation(uow, reservation_id)
        reservation.customer_name = clean_name
        reservation.note = note
        if reservation_date is not None:
            moment = _ensure_utc(reservation_date)
            reservation.reservation_date = moment
            if reservation.reminder_status == ReminderStatus.PENDING.value:
                reservation.reminder_due_at = initial_reminder_due(moment)
        uow.commit()
        return reservation.id


def add_reservation_item(
    uow: UnitOfWork,
    reservation_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int,
    actor: ActorContext | None = None,
) -> uuid.UUID:
    actor = actor or ActorContext()
    if quantity <= 0:
        raise ValidationError("Ürün miktarı sıfırdan büyük olmalıdır.")
    now = datetime.now(UTC)

    with uow:
        reservation = _require_reservation(uow, reservation_id)
        product = uow.products.get_by_id(product_id)
        if product is None:
            raise ValidationError("Ürün bulunamadı.")

        lines = list(uow.reservations.get_items(reservation_id))
        try:
            add_reservation_line(
                tuple(_domain_item(line) for line in lines),
                DomainReservationItem(
                    product_id=str(product.id),
                    quantity=quantity,
                    product_name=product.name,
                ),
            )
        except ValueError as exc:
            raise ValidationError(
                "Bu ürün rezervasyonda zaten var; miktarını güncelleyin."
            ) from exc

        line = ReservationItemRow(
            id=uuid.uuid4(),
            reservation_id=reservation.id,
            product_id=product.id,
            product_name_snapshot=product.name,
            quantity=quantity,
            delivered_quantity=0,
            cancelled_quantity=0,
            status=ReservationStatus.RESERVED.value,
        )
        uow.reservations.add_item(line)
        uow.reservations.add_event(
            _new_event(
                line,
                old_status=None,
                new_status=ReservationStatus.RESERVED,
                quantity_delta=None,
                note="Rezervasyona satır eklendi",
                actor=actor,
                event_at=now,
            )
        )
        _sync_reminder_status(reservation, [*lines, line])
        uow.commit()
        return line.id


def update_reservation_item_quantity(
    uow: UnitOfWork,
    item_id: uuid.UUID,
    new_quantity: int,
    note: str | None = None,
    actor: ActorContext | None = None,
) -> uuid.UUID:
    actor = actor or ActorContext()
    now = datetime.now(UTC)

    with uow:
        line = uow.reservations.get_item(item_id)
        if line is None:
            raise NotFoundError("Rezervasyon satırı bulunamadı.")
        old_quantity = line.quantity
        try:
            updated = _domain_item(line).change_quantity(new_quantity)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        line.quantity = updated.quantity
        uow.reservations.add_event(
            _new_event(
                line,
                old_status=ReservationStatus(line.status),
                new_status=ReservationStatus(line.status),
                quantity_delta=updated.quantity - old_quantity,
                note=note or f"Miktar güncellendi: {old_quantity} → {updated.quantity}",
                actor=actor,
                event_at=now,
            )
        )
        reservation = _require_reservation(uow, line.reservation_id)
        _sync_reminder_status(
            reservation, list(uow.reservations.get_items(line.reservation_id))
        )
        uow.commit()
        return line.reservation_id


def remove_reservation_item(
    uow: UnitOfWork,
    item_id: uuid.UUID,
    actor: ActorContext | None = None,
) -> uuid.UUID:
    actor = actor or ActorContext()

    with uow:
        line = uow.reservations.get_item(item_id)
        if line is None:
            raise NotFoundError("Rezervasyon satırı bulunamadı.")
        try:
            _domain_item(line).ensure_removable()
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        reservation_id = line.reservation_id
        uow.reservations.delete_item(line)
        reservation = _require_reservation(uow, reservation_id)
        _sync_reminder_status(
            reservation, list(uow.reservations.get_items(reservation_id))
        )
        uow.commit()
        return reservation_id


def change_item_status(
    uow: UnitOfWork,
    item_id: uuid.UUID,
    target_status: ReservationStatus | str,
    note: str | None = None,
    service_date: datetime | None = None,
    other_dealer_note: str | None = None,
    actor: ActorContext | None = None,
) -> uuid.UUID:
    actor = actor or ActorContext()
    now = datetime.now(UTC)
    try:
        target = ReservationStatus(target_status)
    except ValueError as exc:
        raise ValidationError("Geçersiz rezervasyon durumu.") from exc
    if target in (ReservationStatus.DELIVERED, ReservationStatus.CANCELLED):
        raise ValidationError(
            "Teslim ve iptal işlemleri kendi akışlarından yapılmalıdır."
        )

    with uow:
        line = uow.reservations.get_item(item_id)
        if line is None:
            raise NotFoundError("Rezervasyon satırı bulunamadı.")
        old_status = ReservationStatus(line.status)
        try:
            transition_item(_domain_item(line), target)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        line.status = target.value
        if service_date is not None:
            line.service_date = _ensure_utc(service_date)
        if other_dealer_note is not None:
            line.other_dealer_note = other_dealer_note
        uow.reservations.add_event(
            _new_event(
                line,
                old_status=old_status,
                new_status=target,
                quantity_delta=None,
                note=note,
                actor=actor,
                event_at=now,
            )
        )
        uow.commit()
        return line.reservation_id


def deliver_item(
    uow: UnitOfWork,
    item_id: uuid.UUID,
    quantity: int,
    idempotency_key: str,
    low_stock_reason: str | None = None,
    note: str | None = None,
    actor: ActorContext | None = None,
) -> uuid.UUID:
    actor = actor or ActorContext()
    now = datetime.now(UTC)
    if not idempotency_key or not idempotency_key.strip():
        raise ValidationError("Teslim işlemi için idempotency anahtarı gereklidir.")

    with uow:
        line = uow.reservations.lock_item(item_id)
        if line is None:
            raise NotFoundError("Rezervasyon satırı bulunamadı.")
        if uow.reservations.find_stock_movement(idempotency_key) is not None:
            return line.reservation_id
        if line.product_id is None:
            raise ValidationError(
                "Ürün kaydı silinmiş; teslimat için ürünü yeniden ekleyin."
            )

        product = uow.reservations.lock_product(line.product_id)
        if product is None:
            raise ValidationError("Ürün bulunamadı.")

        old_status = ReservationStatus(line.status)
        stock_before = product.physical_stock
        try:
            outcome = _domain_item(line).deliver(
                quantity=quantity,
                physical_stock=stock_before,
                idempotency_key=idempotency_key,
                low_stock_reason=low_stock_reason,
            )
        except ValueError as exc:
            message = str(exc)
            if "reason" in message:
                message = "Fiziksel stok yetersiz; teslim için gerekçe giriniz."
            raise ValidationError(message) from exc

        line.delivered_quantity = outcome.item.delivered_quantity
        line.status = outcome.item.status.value
        product.physical_stock = outcome.physical_stock

        uow.products.add_stock_movement(
            StockMovement(
                id=uuid.uuid4(),
                product_id=product.id,
                movement_type="delivery_out",
                quantity_delta=-quantity,
                quantity_before=stock_before,
                quantity_after=outcome.physical_stock,
                reference_type="reservation_item",
                reference_id=line.id,
                note=low_stock_reason or note or "Rezervasyon teslimatı",
                idempotency_key=idempotency_key,
                created_at=now,
                created_by_name=actor.worker_name,
                created_by_device=actor.device_name,
            )
        )
        event_note = note
        if low_stock_reason:
            event_note = f"{event_note + ' · ' if event_note else ''}Gerekçe: {low_stock_reason}"
        uow.reservations.add_event(
            _new_event(
                line,
                old_status=old_status,
                new_status=ReservationStatus(line.status),
                quantity_delta=-quantity,
                note=event_note or "Teslim edildi",
                actor=actor,
                event_at=now,
            )
        )
        reservation = _require_reservation(uow, line.reservation_id)
        _sync_reminder_status(
            reservation, list(uow.reservations.get_items(line.reservation_id))
        )
        uow.commit()
        return line.reservation_id


def cancel_item(
    uow: UnitOfWork,
    item_id: uuid.UUID,
    quantity: int,
    note: str | None = None,
    actor: ActorContext | None = None,
) -> uuid.UUID:
    actor = actor or ActorContext()
    now = datetime.now(UTC)

    with uow:
        line = uow.reservations.lock_item(item_id)
        if line is None:
            raise NotFoundError("Rezervasyon satırı bulunamadı.")
        old_status = ReservationStatus(line.status)
        try:
            cancelled = _domain_item(line).cancel(quantity)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        line.cancelled_quantity = cancelled.cancelled_quantity
        line.status = cancelled.status.value
        uow.reservations.add_event(
            _new_event(
                line,
                old_status=old_status,
                new_status=cancelled.status,
                quantity_delta=-quantity,
                note=note or "İptal edildi",
                actor=actor,
                event_at=now,
            )
        )
        reservation = _require_reservation(uow, line.reservation_id)
        _sync_reminder_status(
            reservation, list(uow.reservations.get_items(line.reservation_id))
        )
        uow.commit()
        return line.reservation_id


def snooze_reminder(
    uow: UnitOfWork,
    reservation_id: uuid.UUID,
    new_due_at: datetime | None = None,
    note: str | None = None,
    actor: ActorContext | None = None,
    now: datetime | None = None,
) -> uuid.UUID:
    actor = actor or ActorContext()
    reference = now or datetime.now(UTC)

    with uow:
        reservation = _require_reservation(uow, reservation_id)
        if reservation.reminder_status == ReminderStatus.RESOLVED.value:
            raise ValidationError(
                "Tüm satırları kapanmış rezervasyonun hatırlatması ertelenemez."
            )
        due = _ensure_utc(new_due_at) if new_due_at else default_snooze_due(reference)
        if due <= reference:
            raise ValidationError("Yeni hatırlatma tarihi ileri bir tarih olmalıdır.")

        previous_due = reservation.reminder_due_at
        uow.reservations.add_reminder(
            ReservationReminder(
                id=uuid.uuid4(),
                reservation_id=reservation.id,
                previous_due_at=previous_due,
                new_due_at=due,
                note=note,
                created_at=reference,
                created_by_name=actor.worker_name,
                created_by_device=actor.device_name,
            )
        )
        reservation.reminder_due_at = due
        reservation.reminder_status = ReminderStatus.SNOOZED.value
        uow.commit()
        return reservation.id


def get_open_reservation_totals(
    uow: UnitOfWork, product_ids: Sequence[uuid.UUID]
) -> Mapping[uuid.UUID, int]:
    if not product_ids:
        return {}
    with uow:
        return uow.reservations.open_quantity_by_product(list(product_ids))


def get_products_with_open_reservations(
    uow: UnitOfWork, product_ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    if not product_ids:
        return set()
    with uow:
        return uow.reservations.open_product_ids(list(product_ids))


def _require_reservation(
    uow: UnitOfWork, reservation_id: uuid.UUID
) -> ReservationRow:
    reservation = uow.reservations.get(reservation_id)
    if reservation is None:
        raise NotFoundError("Rezervasyon bulunamadı.")
    return reservation


def _new_event(
    line: ReservationItemRow,
    *,
    old_status: ReservationStatus | None,
    new_status: ReservationStatus,
    quantity_delta: int | None,
    note: str | None,
    actor: ActorContext,
    event_at: datetime,
) -> ReservationItemEvent:
    return ReservationItemEvent(
        id=uuid.uuid4(),
        reservation_item_id=line.id,
        old_status=old_status.value if old_status else None,
        new_status=new_status.value,
        quantity_delta=quantity_delta,
        note=note,
        event_at=event_at,
        created_by_name=actor.worker_name,
        created_by_device=actor.device_name,
    )


def _domain_item(line: ReservationItemRow) -> DomainReservationItem:
    return DomainReservationItem(
        product_id=str(line.product_id) if line.product_id else None,
        quantity=line.quantity,
        delivered_quantity=line.delivered_quantity,
        cancelled_quantity=line.cancelled_quantity,
        status=ReservationStatus(line.status),
        product_name=line.product_name_snapshot,
    )


def _sync_reminder_status(
    reservation: ReservationRow, lines: Sequence[ReservationItemRow]
) -> None:
    status = next_reminder_status(
        ReminderStatus(reservation.reminder_status),
        tuple(_domain_item(line) for line in lines),
    )
    reservation.reminder_status = status.value


def _load_view(
    uow: UnitOfWork, reservation: ReservationRow, now: datetime
) -> ReservationView:
    lines = uow.reservations.get_items(reservation.id)
    events = uow.reservations.get_events(reservation.id)
    reminders = uow.reservations.get_reminders(reservation.id)
    return _build_view(reservation, lines, events, reminders, now)


def _summary_for(lines: Sequence[ReservationItemRow]) -> ReservationSummary:
    return summarize_reservation(tuple(_domain_item(line) for line in lines))


def _reminder_state(
    reminder_status: str, reminder_due_at: datetime, now: datetime
) -> tuple[str, bool]:
    status = ReminderStatus(reminder_status)
    overdue = status is not ReminderStatus.RESOLVED and reminder_due_at <= now
    label = REMINDER_OVERDUE_LABEL if overdue else REMINDER_LABELS[status]
    return label, overdue


def _build_view(
    reservation: ReservationRow,
    lines: Sequence[ReservationItemRow],
    events: Sequence[ReservationItemEvent],
    reminders: Sequence[ReservationReminder],
    now: datetime,
) -> ReservationView:
    reminder_label, is_overdue = _reminder_state(
        reservation.reminder_status, reservation.reminder_due_at, now
    )
    events_by_item: dict[uuid.UUID, list[ReservationItemEvent]] = {}
    for event in events:
        events_by_item.setdefault(event.reservation_item_id, []).append(event)

    return ReservationView(
        id=reservation.id,
        reservation_number=reservation.reservation_number,
        customer_name=reservation.customer_name,
        reservation_date=reservation.reservation_date,
        reminder_due_at=reservation.reminder_due_at,
        reminder_status=reservation.reminder_status,
        reminder_label=reminder_label,
        is_overdue=is_overdue,
        note=reservation.note,
        created_by_name=reservation.created_by_name,
        items=tuple(
            _build_item_view(line, events_by_item.get(line.id, ()))
            for line in lines
        ),
        reminders=tuple(
            ReminderView(
                previous_due_at=reminder.previous_due_at,
                new_due_at=reminder.new_due_at,
                note=reminder.note,
                created_at=reminder.created_at,
                created_by_name=reminder.created_by_name,
            )
            for reminder in reminders
        ),
        summary=_summary_for(lines),
    )


def _build_item_view(
    line: ReservationItemRow, events: Sequence[ReservationItemEvent]
) -> ReservationItemView:
    status = ReservationStatus(line.status)
    open_quantity = line.quantity - line.delivered_quantity - line.cancelled_quantity
    return ReservationItemView(
        id=line.id,
        product_id=line.product_id,
        product_name=line.product_name_snapshot,
        quantity=line.quantity,
        delivered_quantity=line.delivered_quantity,
        cancelled_quantity=line.cancelled_quantity,
        open_quantity=open_quantity,
        status=line.status,
        status_label=STATUS_LABELS[status],
        service_date=line.service_date,
        other_dealer_note=line.other_dealer_note,
        note=line.note,
        events=tuple(
            ReservationEventView(
                event_at=event.event_at,
                old_status=event.old_status,
                new_status=event.new_status,
                quantity_delta=event.quantity_delta,
                note=event.note,
                created_by_name=event.created_by_name,
            )
            for event in events
        ),
    )


def _build_list_item(
    reservation: ReservationRow,
    lines: Sequence[ReservationItemRow],
    now: datetime,
) -> ReservationListItem:
    reminder_label, is_overdue = _reminder_state(
        reservation.reminder_status, reservation.reminder_due_at, now
    )
    return ReservationListItem(
        id=reservation.id,
        reservation_number=reservation.reservation_number,
        customer_name=reservation.customer_name,
        reservation_date=reservation.reservation_date,
        reminder_due_at=reservation.reminder_due_at,
        reminder_status=reservation.reminder_status,
        reminder_label=reminder_label,
        is_overdue=is_overdue,
        summary=_summary_for(lines),
    )


def _ensure_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)
