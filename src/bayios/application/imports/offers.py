from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from bayios.application.imports.common import (
    ImportPreview,
    ImportResult,
    PreviewRow,
    record_batch,
    replay_result,
)
from bayios.application.offers import (
    OfferInput,
    OfferItemInput,
    create_offer,
    update_offer,
)
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.tabular import (
    first_sheet,
    locate_header,
    normalize_header,
    parse_bool,
    parse_decimal,
    parse_enum,
    parse_int,
    read_raw_sheets,
    row_value,
    sheet_named,
)
from bayios.domain.commissions import (
    CARD_TYPE_LABELS,
    CHANNEL_LABELS,
    CardType,
    PaymentChannel,
)
from bayios.domain.offers import PAYMENT_TYPE_LABELS, PaymentType
from bayios.domain.products import ActorContext, normalize_product_name

OFFER_HEADERS = {
    "offer_number": ("Teklif No", "Teklif Numarası", "offer_number"),
    "offer_key": ("Teklif Anahtarı", "Teklif Anahtari", "offer_key"),
    "customer_name": ("Müşteri Adı", "Musteri Adi", "customer_name"),
    "customer_phone": ("Telefon", "Telefon No", "customer_phone"),
    "payment_type": ("Ödeme Türü", "Odeme Turu", "payment_type"),
    "channel": ("Kanal", "channel"),
    "bank": ("Banka", "bank"),
    "installment_count": ("Taksit", "Taksit Sayısı", "installment_count"),
    "card_type": ("Kart Tipi", "Kart Tipi", "card_type"),
    "dealer_discount_percent": (
        "Bayi İndirimi %",
        "Bayi Indirimi",
        "dealer_discount_percent",
    ),
    "note": ("Not", "note"),
    "product_name": ("Ürün Adı", "Urun Adi", "product_name"),
    "quantity": ("Adet", "Miktar", "quantity"),
    "campaign": ("Kampanya", "campaign", "campaign_name"),
    "gift_present": ("Hediye Durumu", "gift_present"),
    "unit_price_cash": ("Nakit Birim Fiyat", "unit_price_cash"),
    "unit_price_card": ("Kart Birim Fiyat", "unit_price_card"),
}

ITEM_HEADERS = {
    "offer_number": ("Teklif No", "Teklif Numarası", "offer_number"),
    "offer_key": ("Teklif Anahtarı", "Teklif Anahtari", "offer_key"),
    "product_name": ("Ürün Adı", "Urun Adi", "product_name"),
    "quantity": ("Adet", "Miktar", "quantity"),
    "campaign": ("Kampanya", "campaign", "campaign_name"),
    "gift_present": ("Hediye Durumu", "gift_present"),
    "unit_price_cash": ("Nakit Birim Fiyat", "unit_price_cash"),
    "unit_price_card": ("Kart Birim Fiyat", "unit_price_card"),
}

DECISION_OPTIONS = (
    ("create", "Yeni Teklif"),
    ("update", "Güncelle"),
    ("skip", "Atla"),
)


@dataclass(frozen=True)
class _OfferEntity:
    key: str
    row_number: int
    offer_number: int | None
    existing_id: uuid.UUID | None
    existing_status: str | None
    customer_name: str
    payment_label: str
    item_count: int
    data: OfferInput | None
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    decision: str


def preview_offer_import(uow: UnitOfWork, source: bytes) -> ImportPreview:
    entities, unknown = _parse_offers(uow, source)
    rows = tuple(
        PreviewRow(
            key=entity.key,
            row_number=entity.row_number,
            decision=entity.decision,
            summary=entity.customer_name or f"Teklif {entity.key}",
            values={
                "offer_no": entity.offer_number or "",
                "customer": entity.customer_name,
                "payment": entity.payment_label,
                "items": entity.item_count,
                "status": (
                    "Güncellenecek"
                    if entity.existing_id and entity.existing_status == "draft"
                    else "Yeni"
                ),
            },
            errors=entity.errors,
            warnings=entity.warnings,
        )
        for entity in entities
    )
    return ImportPreview(
        module="offers",
        title="Teklif Excel İçe Aktarma Önizlemesi",
        entity_label="teklif",
        columns=(
            ("offer_no", "Teklif No"),
            ("customer", "Müşteri"),
            ("payment", "Ödeme"),
            ("items", "Satır"),
            ("status", "Durum"),
        ),
        rows=rows,
        decision_options=DECISION_OPTIONS,
        unknown_headers=unknown,
    )


def commit_offer_import(
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
        replay = replay_result(uow, "offers", commit_token)
        if replay is not None:
            return replay
    entities, _unknown = _parse_offers(uow, source)
    created = updated = skipped = errors = 0
    for entity in entities:
        if entity.errors or entity.data is None:
            errors += 1
            continue
        decision = decisions.get(entity.key) or entity.decision
        if decision == "skip" or (
            entity.existing_id is not None
            and entity.existing_status != "draft"
            and decision != "create"
        ):
            skipped += 1
            continue
        if entity.existing_id is not None and decision != "create":
            update_offer(uow, entity.existing_id, entity.data, actor)
            updated += 1
        else:
            create_offer(uow, entity.data, actor)
            created += 1
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
            total_count=len(entities),
            actor=actor,
            now=now,
        )
        uow.commit()
    return result


def _parse_offers(
    uow: UnitOfWork, source: bytes
) -> tuple[list[_OfferEntity], tuple[str, ...]]:
    sheets = read_raw_sheets(source)
    offer_sheet = sheet_named(sheets, ("Teklifler", "Offers", "Teklif")) or first_sheet(
        sheets
    )
    offer_layout = locate_header(
        offer_sheet.rows,
        OFFER_HEADERS,
        required=("customer_name", "payment_type"),
        sheet_label=offer_sheet.name,
    )
    flat = "product_name" in offer_layout.indexes
    item_sheet = sheet_named(
        sheets, ("Teklif Satırları", "Teklif Satirlari", "Offer Items")
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
        f"Tanınmayan kolon: {header}" for header in offer_layout.unknown_headers
    )
    grouped: dict[str, dict[str, object]] = {}
    order: list[str] = []

    def resolve_key(raw, layout) -> str:
        number_raw = row_value(raw, layout, "offer_number")
        key_raw = row_value(raw, layout, "offer_key")
        if number_raw is not None and str(number_raw).strip():
            return f"no:{int(parse_decimal(number_raw, 'Teklif No'))}"
        key = str(key_raw or "").strip()
        return f"key:{key}" if key else ""

    for offset, raw in enumerate(offer_sheet.rows[offer_layout.row_index + 1 :], start=1):
        key = resolve_key(raw, offer_layout)
        if not key:
            continue
        if key not in grouped:
            grouped[key] = {
                "row_number": offer_layout.row_index + 2 + offset,
                "raw": raw,
                "items": [],
                "errors": [],
            }
            order.append(key)
        item = {
            "product_name": row_value(raw, offer_layout, "product_name"),
            "quantity": row_value(raw, offer_layout, "quantity"),
            "campaign": row_value(raw, offer_layout, "campaign"),
            "gift_present": row_value(raw, offer_layout, "gift_present"),
            "unit_price_cash": row_value(raw, offer_layout, "unit_price_cash"),
            "unit_price_card": row_value(raw, offer_layout, "unit_price_card"),
        }
        if flat and str(item["product_name"] or "").strip():
            grouped[key]["items"].append(item)  # type: ignore[index]

    if item_sheet is not None and item_layout is not None:
        for raw in item_sheet.rows[item_layout.row_index + 1 :]:
            key = resolve_key(raw, item_layout)
            if key not in grouped:
                key = _fallback_key(raw, item_layout)
            if key not in grouped:
                continue
            grouped[key]["items"].append(  # type: ignore[index]
                {
                    "product_name": row_value(raw, item_layout, "product_name"),
                    "quantity": row_value(raw, item_layout, "quantity"),
                    "campaign": row_value(raw, item_layout, "campaign"),
                    "gift_present": row_value(raw, item_layout, "gift_present"),
                    "unit_price_cash": row_value(raw, item_layout, "unit_price_cash"),
                    "unit_price_card": row_value(raw, item_layout, "unit_price_card"),
                }
            )

    with uow:
        banks = uow.commissions.get_banks(active_only=False)
        bank_by_name = {normalize_header(bank.name): bank for bank in banks}
        offers, _ = uow.offers.list(limit=10_000, offset=0)
        offers_by_number = {offer.offer_number: offer for offer in offers}

        entities: list[_OfferEntity] = []
        for key in order:
            group = grouped[key]
            raw = group["raw"]
            assert isinstance(raw, tuple)
            errors: list[str] = list(group["errors"])  # type: ignore[arg-type]
            try:
                offer_number = (
                    int(parse_decimal(row_value(raw, offer_layout, "offer_number"), "Teklif No"))
                    if row_value(raw, offer_layout, "offer_number") not in (None, "")
                    else None
                )
            except ValueError as exc:
                errors.append(str(exc))
                offer_number = None
            existing = offers_by_number.get(offer_number) if offer_number else None
            if offer_number and existing is None:
                errors.append("Teklif No bulunamadı; yeni teklif için boş bırakın.")
            customer_name = str(
                row_value(raw, offer_layout, "customer_name") or ""
            ).strip()
            if not customer_name:
                errors.append("Müşteri adı zorunludur.")
            try:
                payment_value = parse_enum(
                    row_value(raw, offer_layout, "payment_type"),
                    "Ödeme türü",
                    {item.value: label for item, label in PAYMENT_TYPE_LABELS.items()},
                    default=PaymentType.CASH.value,
                )
                payment_type = PaymentType(str(payment_value))
            except ValueError as exc:
                errors.append(str(exc))
                payment_type = PaymentType.CASH
            try:
                channel_value = parse_enum(
                    row_value(raw, offer_layout, "channel"),
                    "Kanal",
                    {item.value: label for item, label in CHANNEL_LABELS.items()},
                    default=None,
                )
                channel = PaymentChannel(str(channel_value)) if channel_value else None
            except ValueError as exc:
                errors.append(str(exc))
                channel = None
            try:
                card_value = parse_enum(
                    row_value(raw, offer_layout, "card_type"),
                    "Kart tipi",
                    {item.value: label for item, label in CARD_TYPE_LABELS.items()},
                    default=None,
                )
                card_type = CardType(str(card_value)) if card_value else None
            except ValueError as exc:
                errors.append(str(exc))
                card_type = None
            try:
                installment_count = parse_int(
                    row_value(raw, offer_layout, "installment_count"),
                    "Taksit",
                    minimum=1,
                )
            except ValueError as exc:
                errors.append(str(exc))
                installment_count = None
            try:
                discount = parse_decimal(
                    row_value(raw, offer_layout, "dealer_discount_percent"),
                    "Bayi indirimi",
                ) or Decimal(10)
            except ValueError as exc:
                errors.append(str(exc))
                discount = Decimal(10)
            if not (Decimal(0) <= discount <= Decimal(100)):
                errors.append("Bayi indirimi %0 ile %100 arasında olmalıdır.")
            bank_name = normalize_header(row_value(raw, offer_layout, "bank"))
            bank = bank_by_name.get(bank_name) if bank_name else None
            if bank_name and bank is None:
                errors.append("Banka bulunamadı.")
            if payment_type is PaymentType.CARD:
                if channel is None or installment_count is None or card_type is None:
                    errors.append("Kart teklifi için kanal, taksit ve kart tipi zorunludur.")
                if channel in (PaymentChannel.POS, PaymentChannel.ODERO) and bank is None:
                    errors.append("POS/Ödero için banka zorunludur.")
                if channel is PaymentChannel.CHIPPIN and bank is not None:
                    errors.append("Chippin için banka seçilemez.")
            else:
                channel = None
                card_type = None
                installment_count = None
                bank = None

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
            offer_items: list[OfferItemInput] = []
            for item in item_rows:
                product_name = str(item["product_name"] or "").strip()
                if not product_name:
                    errors.append("Ürün adı zorunludur.")
                    continue
                product = products_by_name.get(normalize_product_name(product_name))
                if product is None:
                    errors.append(f"Ürün bulunamadı: {product_name}")
                    continue
                try:
                    quantity = parse_int(item["quantity"], "Adet", minimum=1) or 1
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
                campaign_id = None
                campaign_name = str(item["campaign"] or "").strip()
                if campaign_name:
                    campaigns, _ = uow.campaigns.list(
                        query=campaign_name,
                        state="active",
                        as_of=datetime.now(UTC),
                        limit=100,
                    )
                    matches = [
                        campaign
                        for campaign, version in campaigns
                        if normalize_header(version.name) == normalize_header(campaign_name)
                    ]
                    if len(matches) != 1:
                        errors.append(
                            f"Kampanya bulunamadı veya birden fazla eşleşti: {campaign_name}"
                        )
                    else:
                        campaign_id = matches[0].id
                gift_present = None
                try:
                    gift_present = parse_bool(item["gift_present"], "Hediye durumu")
                except ValueError as exc:
                    errors.append(str(exc))
                try:
                    unit_cash = parse_decimal(item["unit_price_cash"], "Nakit birim fiyat")
                    unit_card = parse_decimal(item["unit_price_card"], "Kart birim fiyat")
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
                offer_items.append(
                    OfferItemInput(
                        product_id=product.id,
                        quantity=quantity,
                        campaign_id=campaign_id,
                        gift_present=gift_present,
                        unit_price_cash=unit_cash,
                        unit_price_card=unit_card,
                    )
                )
            data = OfferInput(
                customer_name=customer_name or None,
                customer_phone=str(
                    row_value(raw, offer_layout, "customer_phone") or ""
                ).strip()
                or None,
                payment_type=payment_type,
                dealer_discount_percent=discount,
                items=tuple(offer_items),
                channel=channel,
                bank_id=bank.id if bank is not None else None,
                installment_count=installment_count,
                card_type=card_type,
                note=str(row_value(raw, offer_layout, "note") or "").strip() or None,
            )
            if existing is not None and existing.status != "draft":
                errors.append("Yalnızca taslak teklifler güncellenebilir.")
            decision = "error" if errors else ("update" if existing else "create")
            entities.append(
                _OfferEntity(
                    key=key,
                    row_number=int(group["row_number"]),  # type: ignore[arg-type]
                    offer_number=offer_number,
                    existing_id=existing.id if existing is not None else None,
                    existing_status=existing.status if existing is not None else None,
                    customer_name=customer_name,
                    payment_label=PAYMENT_TYPE_LABELS[payment_type],
                    item_count=len(offer_items),
                    data=data if not errors else None,
                    errors=tuple(errors),
                    warnings=warnings,
                    decision=decision,
                )
            )
    entities.sort(key=lambda entity: (0 if entity.errors else 1, entity.row_number))
    return entities, warnings


def _fallback_key(raw, layout) -> str:
    number = row_value(raw, layout, "offer_number")
    if number not in (None, ""):
        try:
            return f"no:{int(parse_decimal(number, 'Teklif No'))}"
        except ValueError:
            return ""
    key = str(row_value(raw, layout, "offer_key") or "").strip()
    return f"key:{key}" if key else ""
