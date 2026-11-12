from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from bayios.adapters.db.models.commissions import (
    CommissionLimit as CommissionLimitRow,
)
from bayios.adapters.db.models.commissions import (
    CommissionPeriod,
)
from bayios.adapters.db.models.commissions import (
    CommissionRate as CommissionRateRow,
)
from bayios.application.imports.common import (
    ImportPreview,
    ImportResult,
    PreviewRow,
    record_batch,
    replay_result,
)
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.tabular import (
    first_sheet,
    locate_header,
    normalize_header,
    parse_decimal,
    parse_enum,
    parse_int,
    read_raw_sheets,
    row_value,
)
from bayios.domain.commissions import (
    CARD_TYPE_LABELS,
    CHANNEL_LABELS,
    ODERO_TIER_LABELS,
    PRODUCT_GROUP_LABELS,
    CardType,
    CommissionLimit,
    CommissionPeriodStatus,
    CommissionRate,
    OderoTier,
    PaymentChannel,
    ProductCommissionGroup,
    period_bounds,
    validate_period,
)
from bayios.domain.products import ActorContext

RATE_HEADERS = {
    "period": ("Dönem", "Donem", "period", "period_key"),
    "channel": ("Kanal", "channel"),
    "bank": ("Banka", "bank"),
    "product_group": ("Ürün Grubu", "Urun Grubu", "product_group"),
    "amount_tier": ("Ödero Bandı", "Odero Bandi", "amount_tier"),
    "installment_count": ("Taksit", "Taksit Sayısı", "installment_count"),
    "commission_percent": ("Oran %", "Oran", "commission_percent"),
}
LIMIT_HEADERS = {
    "period": ("Dönem", "Donem", "period", "period_key"),
    "channel": ("Kanal", "channel"),
    "bank": ("Banka", "bank"),
    "product_group": ("Ürün Grubu", "Urun Grubu", "product_group"),
    "card_type": ("Kart Tipi", "card_type"),
    "max_installments": ("Max Taksit", "max_installments"),
}
DECISION_OPTIONS = (
    ("create", "Ekle"),
    ("update", "Güncelle"),
    ("skip", "Atla"),
)


@dataclass(frozen=True)
class _CommissionRow:
    key: str
    row_number: int
    period_key: str
    summary: str
    values: dict[str, object]
    decision: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    payload: object | None


def preview_commission_rates(uow: UnitOfWork, source: bytes) -> ImportPreview:
    rows, unknown = _parse_rates(uow, source)
    return ImportPreview(
        module="commission_rates",
        title="Komisyon Oranları Excel İçe Aktarma Önizlemesi",
        entity_label="oran",
        columns=(
            ("period", "Dönem"),
            ("channel", "Kanal"),
            ("bank", "Banka"),
            ("group", "Grup"),
            ("tier", "Bant"),
            ("installment", "Taksit"),
            ("percent", "Oran"),
            ("status", "Durum"),
        ),
        rows=tuple(
            PreviewRow(
                key=row.key,
                row_number=row.row_number,
                decision=row.decision,
                summary=row.summary,
                values=row.values,
                errors=row.errors,
                warnings=row.warnings,
            )
            for row in rows
        ),
        decision_options=DECISION_OPTIONS,
        unknown_headers=unknown,
    )


def preview_commission_limits(uow: UnitOfWork, source: bytes) -> ImportPreview:
    rows, unknown = _parse_limits(uow, source)
    return ImportPreview(
        module="commission_limits",
        title="Taksit Limitleri Excel İçe Aktarma Önizlemesi",
        entity_label="limit",
        columns=(
            ("period", "Dönem"),
            ("channel", "Kanal"),
            ("bank", "Banka"),
            ("group", "Grup"),
            ("card_type", "Kart Tipi"),
            ("max", "Max Taksit"),
            ("status", "Durum"),
        ),
        rows=tuple(
            PreviewRow(
                key=row.key,
                row_number=row.row_number,
                decision=row.decision,
                summary=row.summary,
                values=row.values,
                errors=row.errors,
                warnings=row.warnings,
            )
            for row in rows
        ),
        decision_options=DECISION_OPTIONS,
        unknown_headers=unknown,
    )


def commit_commission_rates(
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
        replay = replay_result(uow, "commission_rates", commit_token)
        if replay is not None:
            return replay
    rows, _unknown = _parse_rates(uow, source)
    now = datetime.now(UTC)
    created = updated = skipped = errors = 0
    periods: dict[str, CommissionPeriod] = {}
    with uow:
        for row in rows:
            if row.errors or not isinstance(row.payload, CommissionRate):
                errors += 1
                continue
            decision = decisions.get(row.key) or row.decision
            if decision == "skip":
                skipped += 1
                continue
            period = _get_or_create_period(uow, row.period_key, periods, actor, now)
            if period is None:
                errors += 1
                continue
            existing = {
                rate.scope_key: rate
                for rate in uow.commissions.get_rates(period.id)
            }.get(row.payload.scope_key)
            if existing is not None:
                if existing.commission_percent == row.payload.commission_percent:
                    skipped += 1
                else:
                    uow.commissions.update_rate(
                        existing.id, row.payload.commission_percent
                    )
                    updated += 1
            else:
                _add_rate(uow, period.id, row.payload)
                created += 1
        result = record_batch(
            uow,
            module="commission_rates",
            file_name=file_name,
            file_type=file_type,
            source=source,
            commit_token=commit_token,
            created_count=created,
            updated_count=updated,
            skipped_count=skipped,
            error_count=errors,
            total_count=len(rows),
            actor=actor,
            now=now,
        )
        uow.commit()
        return result


def commit_commission_limits(
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
        replay = replay_result(uow, "commission_limits", commit_token)
        if replay is not None:
            return replay
    rows, _unknown = _parse_limits(uow, source)
    now = datetime.now(UTC)
    created = updated = skipped = errors = 0
    periods: dict[str, CommissionPeriod] = {}
    with uow:
        for row in rows:
            if row.errors or not isinstance(row.payload, CommissionLimit):
                errors += 1
                continue
            decision = decisions.get(row.key) or row.decision
            if decision == "skip":
                skipped += 1
                continue
            period = _get_or_create_period(uow, row.period_key, periods, actor, now)
            if period is None:
                errors += 1
                continue
            existing = {
                limit.scope_key: limit
                for limit in uow.commissions.get_limits(period.id)
            }.get(row.payload.scope_key)
            if existing is not None:
                if existing.max_installments == row.payload.max_installments:
                    skipped += 1
                else:
                    uow.commissions.update_limit(
                        existing.id, row.payload.max_installments
                    )
                    updated += 1
            else:
                _add_limit(uow, period.id, row.payload)
                created += 1
        result = record_batch(
            uow,
            module="commission_limits",
            file_name=file_name,
            file_type=file_type,
            source=source,
            commit_token=commit_token,
            created_count=created,
            updated_count=updated,
            skipped_count=skipped,
            error_count=errors,
            total_count=len(rows),
            actor=actor,
            now=now,
        )
        uow.commit()
        return result


def _parse_rates(
    uow: UnitOfWork, source: bytes
) -> tuple[list[_CommissionRow], tuple[str, ...]]:
    sheet = first_sheet(read_raw_sheets(source))
    layout = locate_header(
        sheet.rows,
        RATE_HEADERS,
        required=("period", "channel", "installment_count", "commission_percent"),
        sheet_label=sheet.name,
    )
    warnings = tuple(
        f"Tanınmayan kolon: {header}" for header in layout.unknown_headers
    )
    with uow:
        banks = uow.commissions.get_banks(active_only=False)
        bank_by_name = {normalize_header(bank.name): bank for bank in banks}
        rows: list[_CommissionRow] = []
        for offset, raw in enumerate(sheet.rows[layout.row_index + 1 :], start=1):
            row_number = layout.row_index + 2 + offset
            period_key = str(row_value(raw, layout, "period") or "").strip()
            if not period_key:
                continue
            errors: list[str] = []
            if not (
                len(period_key) == 7
                and period_key[4] == "-"
                and period_key[:4].isdigit()
                and period_key[5:].isdigit()
            ):
                errors.append("Dönem YYYY-MM biçiminde olmalıdır.")
            try:
                channel_value = parse_enum(
                    row_value(raw, layout, "channel"),
                    "Kanal",
                    {item.value: label for item, label in CHANNEL_LABELS.items()},
                )
                if channel_value is None:
                    raise ValueError("Kanal zorunludur.")
                channel = PaymentChannel(str(channel_value))
            except ValueError as exc:
                errors.append(str(exc))
                channel = None
            bank_name = str(row_value(raw, layout, "bank") or "").strip()
            bank = bank_by_name.get(normalize_header(bank_name)) if bank_name else None
            if bank_name and bank is None:
                errors.append("Banka bulunamadı.")
            group_raw = row_value(raw, layout, "product_group")
            try:
                group_value = parse_enum(
                    group_raw,
                    "Ürün grubu",
                    {
                        item.value: label
                        for item, label in PRODUCT_GROUP_LABELS.items()
                    },
                    default=None,
                )
                group = (
                    ProductCommissionGroup(str(group_value))
                    if group_value
                    else None
                )
            except ValueError as exc:
                errors.append(str(exc))
                group = None
            tier_raw = row_value(raw, layout, "amount_tier")
            try:
                tier_value = parse_enum(
                    tier_raw,
                    "Ödero bandı",
                    {item.value: label for item, label in ODERO_TIER_LABELS.items()},
                    default=None,
                )
                tier = OderoTier(str(tier_value)) if tier_value else None
            except ValueError as exc:
                errors.append(str(exc))
                tier = None
            try:
                installment = parse_int(
                    row_value(raw, layout, "installment_count"),
                    "Taksit",
                    minimum=1,
                )
                if installment is None:
                    raise ValueError("Taksit zorunludur.")
            except ValueError as exc:
                errors.append(str(exc))
                installment = 1
            try:
                percent = parse_decimal(
                    row_value(raw, layout, "commission_percent"), "Oran"
                )
                if percent is None:
                    raise ValueError("Oran zorunludur.")
            except ValueError as exc:
                errors.append(str(exc))
                percent = Decimal(0)
            domain_rate: CommissionRate | None = None
            if channel is not None and not errors:
                try:
                    domain_rate = CommissionRate(
                        channel=channel,
                        bank_id=str(bank.id) if bank is not None else None,
                        product_group=group,
                        installment_count=installment,
                        commission_percent=percent,
                        amount_tier=tier,
                    )
                except ValueError as exc:
                    errors.append(str(exc))
            decision = _decision_for_period(uow, period_key, errors)
            if domain_rate is not None:
                existing = {
                    rate.scope_key: rate
                    for rate in (
                        uow.commissions.get_rates(
                            uow.commissions.get_period_by_key(period_key).id
                        )
                        if uow.commissions.get_period_by_key(period_key)
                        else []
                    )
                }.get(domain_rate.scope_key)
                if existing is None:
                    decision = "create"
                elif existing.commission_percent == domain_rate.commission_percent:
                    decision = "skip"
                else:
                    decision = "update"
            rows.append(
                _CommissionRow(
                    key=f"{period_key}|{domain_rate.scope_key if domain_rate else row_number}",
                    row_number=row_number,
                    period_key=period_key,
                    summary=f"{period_key} · {CHANNEL_LABELS.get(channel, '')}",
                    values={
                        "period": period_key,
                        "channel": CHANNEL_LABELS.get(channel, ""),
                        "bank": bank.name if bank is not None else bank_name,
                        "group": PRODUCT_GROUP_LABELS.get(group, "")
                        if group
                        else "",
                        "tier": ODERO_TIER_LABELS.get(tier, "") if tier else "",
                        "installment": installment,
                        "percent": f"{percent:.2f}",
                        "status": _decision_label(decision),
                    },
                    decision=decision,
                    errors=tuple(errors),
                    warnings=warnings,
                    payload=domain_rate if not errors else None,
                )
            )
    rows.sort(key=lambda row: (0 if row.errors else 1, row.row_number))
    return rows, warnings


def _parse_limits(
    uow: UnitOfWork, source: bytes
) -> tuple[list[_CommissionRow], tuple[str, ...]]:
    sheet = first_sheet(read_raw_sheets(source))
    layout = locate_header(
        sheet.rows,
        LIMIT_HEADERS,
        required=("period", "max_installments"),
        sheet_label=sheet.name,
    )
    warnings = tuple(
        f"Tanınmayan kolon: {header}" for header in layout.unknown_headers
    )
    with uow:
        banks = uow.commissions.get_banks(active_only=False)
        bank_by_name = {normalize_header(bank.name): bank for bank in banks}
        rows: list[_CommissionRow] = []
        for offset, raw in enumerate(sheet.rows[layout.row_index + 1 :], start=1):
            row_number = layout.row_index + 2 + offset
            period_key = str(row_value(raw, layout, "period") or "").strip()
            if not period_key:
                continue
            errors: list[str] = []
            if not (
                len(period_key) == 7
                and period_key[4] == "-"
                and period_key[:4].isdigit()
                and period_key[5:].isdigit()
            ):
                errors.append("Dönem YYYY-MM biçiminde olmalıdır.")
            try:
                channel_value = parse_enum(
                    row_value(raw, layout, "channel"),
                    "Kanal",
                    {item.value: label for item, label in CHANNEL_LABELS.items()},
                    default=None,
                )
                channel = PaymentChannel(str(channel_value)) if channel_value else None
            except ValueError as exc:
                errors.append(str(exc))
                channel = None
            bank_name = str(row_value(raw, layout, "bank") or "").strip()
            bank = bank_by_name.get(normalize_header(bank_name)) if bank_name else None
            if bank_name and bank is None:
                errors.append("Banka bulunamadı.")
            try:
                group_value = parse_enum(
                    row_value(raw, layout, "product_group"),
                    "Ürün grubu",
                    {item.value: label for item, label in PRODUCT_GROUP_LABELS.items()},
                    default=None,
                )
                group = ProductCommissionGroup(str(group_value)) if group_value else None
            except ValueError as exc:
                errors.append(str(exc))
                group = None
            try:
                card_value = parse_enum(
                    row_value(raw, layout, "card_type"),
                    "Kart tipi",
                    {item.value: label for item, label in CARD_TYPE_LABELS.items()},
                    default=None,
                )
                card_type = CardType(str(card_value)) if card_value else None
            except ValueError as exc:
                errors.append(str(exc))
                card_type = None
            try:
                max_installments = parse_int(
                    row_value(raw, layout, "max_installments"),
                    "Max taksit",
                    minimum=1,
                )
                if max_installments is None:
                    raise ValueError("Max taksit zorunludur.")
            except ValueError as exc:
                errors.append(str(exc))
                max_installments = 1
            domain_limit: CommissionLimit | None = None
            if not errors:
                try:
                    domain_limit = CommissionLimit(
                        max_installments=max_installments,
                        channel=channel,
                        bank_id=str(bank.id) if bank is not None else None,
                        product_group=group,
                        card_type=card_type,
                    )
                except ValueError as exc:
                    errors.append(str(exc))
            decision = _decision_for_period(uow, period_key, errors)
            if domain_limit is not None:
                period = uow.commissions.get_period_by_key(period_key)
                existing = {
                    limit.scope_key: limit
                    for limit in (
                        uow.commissions.get_limits(period.id) if period else []
                    )
                }.get(domain_limit.scope_key)
                if existing is None:
                    decision = "create"
                else:
                    decision = (
                        "skip"
                        if existing.max_installments == domain_limit.max_installments
                        else "update"
                    )
            rows.append(
                _CommissionRow(
                    key=f"{period_key}|{domain_limit.scope_key if domain_limit else row_number}",
                    row_number=row_number,
                    period_key=period_key,
                    summary=f"{period_key} · {CHANNEL_LABELS.get(channel, '')}",
                    values={
                        "period": period_key,
                        "channel": CHANNEL_LABELS.get(channel, ""),
                        "bank": bank.name if bank is not None else bank_name,
                        "group": PRODUCT_GROUP_LABELS.get(group, "")
                        if group
                        else "",
                        "card_type": CARD_TYPE_LABELS.get(card_type, "")
                        if card_type
                        else "",
                        "max": max_installments,
                        "status": _decision_label(decision),
                    },
                    decision=decision,
                    errors=tuple(errors),
                    warnings=warnings,
                    payload=domain_limit if not errors else None,
                )
            )
    rows.sort(key=lambda row: (0 if row.errors else 1, row.row_number))
    return rows, warnings


def _decision_for_period(
    uow: UnitOfWork, period_key: str, errors: list[str]
) -> str:
    period = uow.commissions.get_period_by_key(period_key)
    if period is None:
        return "create"
    if period.status == "archived":
        errors.append("Arşivlenmiş dönem içe aktarılamaz.")
        return "error"
    return "update"


def _decision_label(decision: str) -> str:
    return {"create": "Eklenecek", "update": "Güncellenecek", "skip": "Değişmeyecek"}.get(
        decision, "Hatalı"
    )


def _get_or_create_period(
    uow: UnitOfWork,
    period_key: str,
    cache: dict[str, CommissionPeriod],
    actor: ActorContext,
    now: datetime,
) -> CommissionPeriod | None:
    period = cache.get(period_key) or uow.commissions.get_period_by_key(period_key)
    if period is not None:
        if period.status == "archived":
            return None
        return period
    try:
        year_text, month_text = period_key.split("-")
        year, month = int(year_text), int(month_text)
        start, end = period_bounds(year, month)
        validate_period(
            period_key=period_key,
            valid_from=start,
            valid_until=end,
            status=CommissionPeriodStatus.DRAFT,
        )
    except (ValueError, AttributeError):
        return None
    period = CommissionPeriod(
        id=uuid.uuid4(),
        period_key=period_key,
        valid_from=start,
        valid_until=end,
        status=CommissionPeriodStatus.DRAFT.value,
        created_at=now,
        created_by_name=actor.worker_name,
        created_by_device=actor.device_name,
    )
    uow.commissions.add_period(period)
    cache[period_key] = period
    return period


def _add_rate(uow: UnitOfWork, period_id: uuid.UUID, rate: CommissionRate) -> None:
    uow.commissions.add_rate(
        CommissionRateRow(
            id=uuid.uuid4(),
            period_id=period_id,
            channel=rate.channel.value,
            bank_id=uuid.UUID(rate.bank_id) if rate.bank_id else None,
            product_group=rate.product_group.value if rate.product_group else None,
            amount_tier=rate.amount_tier.value if rate.amount_tier else None,
            installment_count=rate.installment_count,
            commission_percent=rate.commission_percent,
            scope_key=rate.scope_key,
        )
    )


def _add_limit(uow: UnitOfWork, period_id: uuid.UUID, limit: CommissionLimit) -> None:
    uow.commissions.add_limit(
        CommissionLimitRow(
            id=uuid.uuid4(),
            period_id=period_id,
            channel=limit.channel.value if limit.channel else None,
            bank_id=uuid.UUID(limit.bank_id) if limit.bank_id else None,
            product_group=limit.product_group.value if limit.product_group else None,
            card_type=limit.card_type.value if limit.card_type else None,
            max_installments=limit.max_installments,
            scope_key=limit.scope_key,
        )
    )
