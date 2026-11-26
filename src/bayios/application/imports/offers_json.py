from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from bayios.adapters.db.models.commissions import Bank
from bayios.application.errors import ImportFormatError
from bayios.application.imports.common import (
    ImportPreview,
    ImportResult,
    PreviewRow,
    ProductLookup,
    record_batch,
    replay_result,
)
from bayios.application.offers import (
    OfferInput,
    OfferItemInput,
    create_offer,
    set_offer_status,
    update_offer,
)
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.domain.commissions import CardType, PaymentChannel
from bayios.domain.naming import canonical_display_name, normalize_name
from bayios.domain.offers import OfferStatus, PaymentType
from bayios.domain.products import ActorContext

DECISION_OPTIONS = (
    ("create", "Yeni Teklif"),
    ("update", "Güncelle"),
    ("skip", "Atla"),
)


@dataclass(frozen=True)
class _OfferJson:
    key: str
    row_number: int
    offer_number: int | None
    existing_id: uuid.UUID | None
    existing_status: str | None
    customer_name: str
    payment_label: str
    item_count: int
    data: OfferInput | None
    target_status: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    decision: str


def preview_offer_json(
    uow: UnitOfWork,
    source: bytes,
    *,
    auto_create_banks: bool = False,
) -> ImportPreview:
    with uow:
        offers = _parse_json(uow, source, auto_create_banks=auto_create_banks)
    return ImportPreview(
        module="offers",
        title="Teklif JSON İçe Aktarma Önizlemesi",
        entity_label="teklif",
        columns=(
            ("offer_no", "Teklif No"),
            ("customer", "Müşteri"),
            ("payment", "Ödeme"),
            ("items", "Ürün"),
            ("status", "Durum"),
        ),
        rows=tuple(
            PreviewRow(
                key=offer.key,
                row_number=offer.row_number,
                decision=offer.decision,
                summary=offer.customer_name or f"Teklif {offer.offer_number or '—'}",
                values={
                    "offer_no": offer.offer_number or "—",
                    "customer": offer.customer_name,
                    "payment": offer.payment_label,
                    "items": offer.item_count,
                    "status": (
                        "Güncellenecek"
                        if offer.existing_id
                        and offer.existing_status == OfferStatus.DRAFT.value
                        else (
                            "Taslak değil (atlanacak)"
                            if offer.existing_id
                            else "Yeni"
                        )
                    ),
                },
                errors=offer.errors,
                warnings=offer.warnings,
            )
            for offer in offers
        ),
        decision_options=DECISION_OPTIONS,
    )


def commit_offer_json(
    uow: UnitOfWork,
    *,
    file_name: str,
    file_type: str,
    source: bytes,
    decisions: dict[str, str],
    actor: ActorContext | None = None,
    commit_token: str | None = None,
    auto_create_banks: bool = False,
) -> ImportResult:
    actor = actor or ActorContext()
    with uow:
        replay = replay_result(uow, "offers", commit_token)
        if replay is not None:
            return replay
        offers = _parse_json(uow, source, auto_create_banks=auto_create_banks)
        uow.commit()
    created = updated = skipped = errors = 0
    for offer in offers:
        if offer.errors or offer.data is None:
            errors += 1
            continue
        decision = decisions.get(offer.key) or offer.decision
        if decision == "skip" or (
            offer.existing_id is not None
            and offer.existing_status != OfferStatus.DRAFT.value
            and decision != "create"
        ):
            skipped += 1
            continue
        if offer.existing_id is not None and decision != "create":
            update_offer(uow, offer.existing_id, offer.data, actor)
            offer_id = offer.existing_id
            updated += 1
        else:
            offer_id = create_offer(uow, offer.data, actor)
            created += 1
        if offer.target_status != OfferStatus.DRAFT.value:
            _apply_status(uow, offer_id, offer.target_status, actor)
    now = datetime.now(UTC)
    with uow:
        result = record_batch(
            uow,
            module="offers",
            file_name=file_name,
            file_type=file_type,
            source=source,
            commit_token=commit_token,
            created_count=created,
            updated_count=updated,
            skipped_count=skipped,
            error_count=errors,
            total_count=len(offers),
            actor=actor,
            now=now,
        )
        uow.commit()
        return result


def _parse_json(
    uow: UnitOfWork,
    source: bytes,
    *,
    auto_create_banks: bool,
) -> list[_OfferJson]:
    try:
        payload = json.loads(source.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportFormatError(
            "Teklif JSON dosyası okunamadı; geçerli bir JSON yükleyin."
        ) from exc
    if not isinstance(payload, dict):
        raise ImportFormatError("Teklif JSON dosyası nesne olmalıdır.")
    if str(payload.get("schema_version") or "").strip() != "1.0":
        raise ImportFormatError(
            "Desteklenmeyen teklif şeması; schema_version 1.0 olmalıdır."
        )
    raw_offers = payload.get("offers")
    if not isinstance(raw_offers, list):
        raise ImportFormatError("Teklif JSON dosyasında offers listesi yok.")

    existing_rows, _total = uow.offers.list(limit=10_000, offset=0)
    existing_by_number = {
        offer.offer_number: offer for offer in existing_rows
    }
    lookup = ProductLookup.load(uow)
    campaigns, _campaign_total = uow.campaigns.list(limit=10_000)
    campaigns_by_name = {
        normalize_name(version.name): version
        for _campaign, version in campaigns
    }
    banks = {
        normalize_name(bank.name): bank
        for bank in uow.commissions.get_banks(active_only=False)
    }
    pending_banks: dict[str, Bank] = {}
    seen_numbers: set[int] = set()
    parsed: list[_OfferJson] = []
    for offset, raw in enumerate(raw_offers, start=2):
        if not isinstance(raw, dict):
            parsed.append(_error_offer(offset, "Teklif JSON satırı nesne olmalıdır."))
            continue
        parsed.append(
            _parse_one(
                raw,
                row_number=offset,
                lookup=lookup,
                existing_by_number=existing_by_number,
                campaigns_by_name=campaigns_by_name,
                banks=banks,
                pending_banks=pending_banks,
                auto_create_banks=auto_create_banks,
                seen_numbers=seen_numbers,
            )
        )
    if pending_banks:
        for bank in pending_banks.values():
            uow.commissions.add_bank(bank)
    return parsed


def _parse_one(
    raw: dict[str, Any],
    *,
    row_number: int,
    lookup: ProductLookup,
    existing_by_number: dict[int, Any],
    campaigns_by_name: dict[str, Any],
    banks: dict[str, Any],
    pending_banks: dict[str, Bank],
    auto_create_banks: bool,
    seen_numbers: set[int],
) -> _OfferJson:
    errors: list[str] = []
    warnings: list[str] = []
    offer_number = _int_or_none(raw.get("offer_number"))
    if offer_number is not None and offer_number in seen_numbers:
        errors.append("Aynı teklif numarası dosyada tekrar ediyor; ilk kayıt işlendi.")
    if offer_number is not None:
        seen_numbers.add(offer_number)
    existing = existing_by_number.get(offer_number) if offer_number else None
    existing_id = existing.id if existing is not None else None
    existing_status = existing.status if existing is not None else None
    customer_name = _text(raw.get("customer_name"))
    if not customer_name:
        warnings.append("Müşteri adı boş; teklif isimsiz kaydedilecek.")

    payment_raw = _text(raw.get("payment_type")) or "cash"
    try:
        payment_type = PaymentType(payment_raw)
    except ValueError:
        errors.append(f"Ödeme türü geçersiz: {payment_raw}")
        payment_type = PaymentType.CASH
    channel = _enum_or_none(PaymentChannel, raw.get("channel"), errors, "Kanal")
    card_type = _enum_or_none(CardType, raw.get("card_type"), errors, "Kart tipi")
    card_network = _text(raw.get("card_network")) or None
    bank_name = _text(raw.get("bank_name"))
    bank_id = None
    if bank_name:
        bank = banks.get(normalize_name(bank_name))
        if bank is not None:
            bank_id = bank.id
        elif auto_create_banks:
            pending_banks.setdefault(
                normalize_name(bank_name),
                Bank(
                    id=uuid.uuid4(),
                    name=canonical_display_name(bank_name),
                    name_normalized=normalize_name(bank_name),
                    is_active=True,
                ),
            )
            bank_id = pending_banks[normalize_name(bank_name)].id
            warnings.append(f"Yeni banka oluşturulacak: {bank_name}")
        else:
            warnings.append(f"Banka bulunamadı; genel oran kullanılacak: {bank_name}")

    status_raw = _text(raw.get("status")) or OfferStatus.DRAFT.value
    try:
        target_status = OfferStatus(status_raw).value
    except ValueError:
        errors.append(f"Teklif durumu geçersiz: {status_raw}")
        target_status = OfferStatus.DRAFT.value

    items_raw = raw.get("items")
    if not isinstance(items_raw, list) or not items_raw:
        errors.append("Teklifte en az bir ürün satırı olmalıdır.")
        items_raw = []
    items: list[OfferItemInput] = []
    for raw_item in items_raw:
        if not isinstance(raw_item, dict):
            errors.append("Ürün satırı nesne olmalıdır.")
            continue
        if raw_item.get("is_gift"):
            continue
        product_name = _text(raw_item.get("product_name"))
        product_id = _text(raw_item.get("product_id")) or None
        product = _resolve_product(lookup, product_id, product_name)
        if product is None:
            errors.append(f"Ürün bulunamadı: {product_name or product_id or '—'}")
            continue
        quantity = _positive_int(raw_item.get("quantity"), 1)
        campaign_name = _text(raw_item.get("campaign_name"))
        campaign = (
            campaigns_by_name.get(normalize_name(campaign_name))
            if campaign_name
            else None
        )
        if campaign_name and campaign is None:
            warnings.append(f"Kampanya bulunamadı; kampanyasız aktarılacak: {campaign_name}")
        items.append(
            OfferItemInput(
                product_id=product.id,
                quantity=quantity,
                campaign_id=campaign.id if campaign is not None else None,
                gift_present=_optional_bool(raw_item.get("gift_present")),
                unit_price_cash=_decimal(raw_item.get("unit_price_cash")),
                unit_price_card=_decimal(raw_item.get("unit_price_card")),
            )
        )
    if not items:
        errors.append("Eşleşen ürün satırı yok; teklif aktarılamaz.")

    created_at = _datetime(raw.get("created_at"), warnings)
    data = None
    if not errors:
        data = OfferInput(
            customer_name=customer_name or None,
            customer_phone=_text(raw.get("customer_phone")) or None,
            payment_type=payment_type,
            channel=channel,
            bank_id=bank_id,
            card_network=card_network,
            installment_count=_positive_int_or_none(raw.get("installment_count")),
            card_type=card_type,
            dealer_discount_percent=_decimal(raw.get("dealer_discount_percent")) or Decimal(10),
            dealer_discount_cash_percent=(
                _decimal(raw.get("dealer_discount_cash_percent")) or Decimal(10)
            ),
            note=_text(raw.get("note")) or None,
            cash_total_override=_decimal(raw.get("cash_total_override")),
            card_total_override=_decimal(raw.get("card_total_override")),
            created_at=created_at,
            items=tuple(items),
        )
    if errors:
        decision = "error"
    elif existing_id is not None and existing_status != OfferStatus.DRAFT.value:
        decision = "skip"
    elif existing_id is not None:
        decision = "update"
    else:
        decision = "create"
    return _OfferJson(
        key=str(offer_number or f"row:{row_number}"),
        row_number=row_number,
        offer_number=offer_number,
        existing_id=existing_id,
        existing_status=existing_status,
        customer_name=customer_name,
        payment_label=(
            "Nakit" if payment_type is PaymentType.CASH else "Kart"
        ),
        item_count=len(items),
        data=data,
        target_status=target_status,
        errors=tuple(errors),
        warnings=tuple(warnings),
        decision=decision,
    )


def _apply_status(
    uow: UnitOfWork, offer_id: uuid.UUID, status: str, actor: ActorContext
) -> None:
    if status == OfferStatus.ACCEPTED.value:
        set_offer_status(
            uow, offer_id, OfferStatus.PRESENTED.value,
            note="JSON içe aktarıldı", actor=actor,
        )
        set_offer_status(
            uow, offer_id, OfferStatus.ACCEPTED.value,
            note="JSON içe aktarıldı", actor=actor,
        )
    else:
        set_offer_status(
            uow, offer_id, status,
            note="JSON içe aktarıldı", actor=actor,
        )


def _resolve_product(lookup: ProductLookup, product_id: str | None, name: str) -> Any:
    if product_id:
        product = lookup.by_external_id.get(product_id) or lookup.by_alias.get(product_id)
        if product is not None:
            return product
        matches = lookup.by_id.get(uuid.UUID(product_id)) if _is_uuid(product_id) else None
        if matches is not None:
            return matches
    if not name:
        return None
    matches = lookup.by_name.get(normalize_name(name), ())
    return matches[0] if len(matches) == 1 else None


def _enum_or_none(enum_type: Any, value: object, errors: list[str], label: str) -> Any:
    text = _text(value)
    if not text:
        return None
    try:
        return enum_type(text)
    except ValueError:
        errors.append(f"{label} geçersiz: {text}")
        return None


def _error_offer(row_number: int, message: str) -> _OfferJson:
    return _OfferJson(
        key=f"row:{row_number}",
        row_number=row_number,
        offer_number=None,
        existing_id=None,
        existing_status=None,
        customer_name="",
        payment_label="",
        item_count=0,
        data=None,
        target_status=OfferStatus.DRAFT.value,
        errors=(message,),
        warnings=(),
        decision="error",
    )


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def _text(value: object) -> str:
    return str(value or "").strip()


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _positive_int(value: object, default: int) -> int:
    parsed = _int_or_none(value)
    return parsed if parsed and parsed > 0 else default


def _positive_int_or_none(value: object) -> int | None:
    parsed = _int_or_none(value)
    return parsed if parsed and parsed > 0 else None


def _decimal(value: object) -> Decimal | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _optional_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "evet", "var"}:
        return True
    if text in {"0", "false", "hayır", "hayir", "yok"}:
        return False
    return None


def _datetime(value: object, warnings: list[str]) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        warnings.append(f"created_at geçersiz: {text}")
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
