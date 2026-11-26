from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any

from bayios.adapters.db.models.products import Product
from bayios.application.campaigns import (
    CampaignInput,
    CampaignProductInput,
    create_campaign_in_uow,
    update_campaign_in_uow,
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
from bayios.application.tabular import normalize_header, parse_decimal
from bayios.domain.campaigns import (
    BasePriceType,
    CampaignPaymentCondition,
    CampaignType,
    DiscountType,
    ProductRelationType,
)
from bayios.domain.naming import normalize_name
from bayios.domain.products import (
    ActorContext,
    normalize_category_name,
    normalize_product_name,
)

DECISION_OPTIONS = (
    ("create", "Yeni Kampanya"),
    ("update", "Güncelle"),
    ("skip", "Atla"),
)

_RELATION_LABELS = {
    "sart urunu": ProductRelationType.QUALIFYING,
    "fayda urunu": ProductRelationType.BENEFIT,
    "hediye urunu": ProductRelationType.GIFT,
    "ilgili urun": ProductRelationType.RELATED,
}


@dataclass(frozen=True)
class _JsonCampaign:
    key: str
    row_number: int
    external_id: str | None
    name: str
    starts_at: datetime
    ends_at: datetime
    date_text: str
    source_category: str | None
    conditions: tuple[str, ...]
    source_product_count: int | None
    resolved_product_count: int
    existing_id: uuid.UUID | None
    data: CampaignInput | None
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    decision: str


def preview_campaign_json(
    uow: UnitOfWork,
    source: bytes,
    *,
    target_campaign_id: uuid.UUID | None = None,
) -> ImportPreview:
    with uow:
        campaigns = _parse_json(
            uow,
            source,
            target_campaign_id=target_campaign_id,
        )
    rows = tuple(
        PreviewRow(
            key=campaign.key,
            row_number=campaign.row_number,
            decision=campaign.decision,
            summary=campaign.name,
            values={
                "name": campaign.name,
                "category": campaign.source_category or "—",
                "dates": campaign.date_text,
                "conditions": len(campaign.conditions),
                "products": (
                    f"{campaign.resolved_product_count} / "
                    f"{campaign.source_product_count or 0}"
                ),
                "status": (
                    "Güncellenecek" if campaign.existing_id else "Yeni"
                ),
            },
            errors=campaign.errors,
            warnings=campaign.warnings,
        )
        for campaign in campaigns
    )
    return ImportPreview(
        module="campaigns",
        title="Kampanya JSON İçe Aktarma Önizlemesi",
        entity_label="kampanya",
        columns=(
            ("name", "Kampanya"),
            ("category", "Kategori"),
            ("dates", "Tarih"),
            ("conditions", "Koşul"),
            ("products", "Ürün (eşleşen / kaynak)"),
            ("status", "Durum"),
        ),
        rows=rows,
        decision_options=DECISION_OPTIONS,
    )


def commit_campaign_json(
    uow: UnitOfWork,
    *,
    file_name: str,
    file_type: str,
    source: bytes,
    decisions: dict[str, str],
    actor: ActorContext | None = None,
    commit_token: str | None = None,
    target_campaign_id: uuid.UUID | None = None,
) -> ImportResult:
    actor = actor or ActorContext()
    with uow:
        replay = replay_result(uow, "campaigns", commit_token)
        if replay is not None:
            return replay
        campaigns = _parse_json(
            uow,
            source,
            target_campaign_id=target_campaign_id,
            auto_create_products=True,
        )
        now = datetime.now(UTC)
        created = updated = skipped = errors = 0
        for campaign in campaigns:
            if campaign.errors or campaign.data is None:
                errors += 1
                continue
            decision = decisions.get(campaign.key) or campaign.decision
            if decision == "skip":
                skipped += 1
                continue
            if campaign.existing_id is not None and decision != "create":
                _campaign, changed = update_campaign_in_uow(
                    uow,
                    campaign.existing_id,
                    campaign.data,
                    actor=actor,
                    now=now,
                )
                if changed:
                    updated += 1
                else:
                    skipped += 1
            else:
                create_campaign_in_uow(
                    uow, campaign.data, actor=actor, now=now
                )
                created += 1
        result = record_batch(
            uow,
            module="campaigns",
            file_name=file_name,
            file_type=file_type,
            source=source,
            commit_token=commit_token,
            created_count=created,
            updated_count=updated,
            skipped_count=skipped,
            error_count=errors,
            total_count=len(campaigns),
            actor=actor,
            now=now,
        )
        uow.commit()
        return result


def _parse_json(
    uow: UnitOfWork,
    source: bytes,
    *,
    target_campaign_id: uuid.UUID | None,
    auto_create_products: bool = False,
) -> list[_JsonCampaign]:
    try:
        payload = json.loads(source.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportFormatError(
            "Kampanya JSON dosyası okunamadı; geçerli bir JSON yükleyin."
        ) from exc
    if not isinstance(payload, dict):
        raise ImportFormatError("Kampanya JSON dosyası nesne olmalıdır.")
    schema_version = str(payload.get("schema_version") or "").strip()
    if schema_version != "1.0":
        raise ImportFormatError(
            "Desteklenmeyen kampanya şeması; schema_version 1.0 olmalıdır."
        )
    raw_campaigns = payload.get("campaigns")
    if not isinstance(raw_campaigns, list):
        raise ImportFormatError("Kampanya JSON dosyasında campaigns listesi yok.")

    target_campaign = None
    target_version = None
    if target_campaign_id is not None:
        target_campaign = uow.campaigns.get(target_campaign_id)
        target_version = uow.campaigns.get_current_version(target_campaign_id)
        if target_campaign is None or target_version is None:
            raise ImportFormatError("Kampanya bulunamadı.")
        if len(raw_campaigns) != 1:
            raise ImportFormatError(
                "Kampanya detayından yalnızca tek kampanyalı JSON yüklenebilir."
            )

    existing_rows, _total = uow.campaigns.list(limit=10_000)
    existing_by_key: dict[tuple[str, date, date], Any] = {}
    for campaign, version in existing_rows:
        existing_by_key[
            (
                normalize_product_name(version.name),
                version.starts_at.date(),
                version.ends_at.date(),
            )
        ] = campaign

    lookup = ProductLookup.load(uow)
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    parsed: list[_JsonCampaign] = []
    for offset, raw in enumerate(raw_campaigns, start=2):
        if not isinstance(raw, dict):
            parsed.append(
                _error_campaign(
                    offset,
                    "Kampanya JSON satırı nesne olmalıdır.",
                )
            )
            continue
        parsed.append(
            _parse_one(
                uow,
                raw,
                row_number=offset,
                lookup=lookup,
                existing_by_key=existing_by_key,
                target_campaign=target_campaign,
                target_version=target_version,
                seen_ids=seen_ids,
                seen_keys=seen_keys,
                auto_create_products=auto_create_products,
            )
        )
    return parsed


def _parse_one(
    uow: UnitOfWork,
    raw: dict[str, Any],
    *,
    row_number: int,
    lookup: ProductLookup,
    existing_by_key: dict[tuple[str, date, date], Any],
    target_campaign: Any,
    target_version: Any,
    seen_ids: set[str],
    seen_keys: set[str],
    auto_create_products: bool,
) -> _JsonCampaign:
    errors: list[str] = []
    warnings: list[str] = []
    external_id = _text(raw.get("id")) or None
    name = _text(raw.get("name"))
    if not name:
        errors.append("Kampanya adı zorunludur.")

    start_value = _parse_date(raw.get("start_date"), "Başlangıç tarihi", errors)
    end_value = _parse_date(raw.get("end_date"), "Bitiş tarihi", errors)
    if start_value is None or end_value is None:
        errors.append("Başlangıç ve bitiş tarihi zorunludur.")
    starts_at = (
        datetime.combine(start_value, time.min, tzinfo=UTC)
        if start_value is not None
        else datetime.now(UTC)
    )
    ends_at = (
        datetime.combine(end_value, time.max, tzinfo=UTC)
        if end_value is not None
        else starts_at
    )
    if end_value is not None and start_value is not None and ends_at < starts_at:
        errors.append("Bitiş tarihi başlangıçtan önce olamaz.")

    source_category = _text(raw.get("category")) or None
    source_url = _text(raw.get("url")) or None
    scraped_at = _parse_datetime(raw.get("scraped_at"), warnings)
    conditions = _text_list(raw.get("conditions"), warnings, "Koşullar")
    product_count = _int_or_none(raw.get("product_count"))
    combines_with_others = raw.get("combines_with_others", True)
    if not isinstance(combines_with_others, bool):
        combines_with_others = True
    exclusion_group = _text(raw.get("exclusion_group")) or None
    min_basket_total = _decimal_or_none(
        raw.get("min_basket_total"), warnings, "Sepet alt sınırı"
    )
    payment_conditions = _parse_payment_conditions(
        uow, raw.get("payment_conditions"), warnings
    )
    has_payment_conditions_key = "payment_conditions" in raw
    campaign_type_value = _enum_or_default(
        raw.get("campaign_type"), CampaignType, CampaignType.GENERAL, warnings
    )
    campaign_base_price_type_value = _enum_or_default(
        raw.get("base_price_type"),
        BasePriceType,
        BasePriceType.REGULAR,
        warnings,
    )
    campaign_discount_type_value = _enum_or_default(
        raw.get("discount_type"), DiscountType, DiscountType.INFO_ONLY, warnings
    )
    campaign_discount_value = _decimal_or_none(
        raw.get("discount_value"), warnings, "İndirim değeri"
    )
    gift_description = _text(raw.get("gift_description")) or None
    gift_optional = raw.get("gift_optional", False)
    if not isinstance(gift_optional, bool):
        gift_optional = False
    gift_yes_base_price_type = _parse_optional_enum(
        raw.get("gift_yes_base_price_type"), BasePriceType, warnings
    )
    gift_no_base_price_type = _parse_optional_enum(
        raw.get("gift_no_base_price_type"), BasePriceType, warnings
    )
    employee_note = _text(raw.get("employee_note")) or None

    raw_products = raw.get("products")
    if raw_products is None:
        raw_products = []
    if not isinstance(raw_products, list):
        warnings.append("Ürünler listesi geçersiz; ürünler atlandı.")
        raw_products = []
    has_explicit_rules = any(
        isinstance(item, dict)
        and (
            "target_type" in item
            or "discount_type" in item
            or item.get("category_id")
        )
        for item in raw_products
    )

    products: list[CampaignProductInput] = []
    seen_product_relations: set[tuple[uuid.UUID, str]] = set()
    missing_products = 0
    missing_names: list[str] = []
    created_product_names: list[str] = []
    can_create = (
        bool(name)
        and start_value is not None
        and end_value is not None
        and not errors
    )
    for raw_product in raw_products:
        if not isinstance(raw_product, dict):
            missing_products += 1
            continue
        product_name = _text(raw_product.get("name"))
        product_id = _text(raw_product.get("product_id")) or None
        relation = _parse_relation(raw_product.get("relationship"), warnings)
        quantity = _positive_int_or_none(raw_product.get("required_quantity"))
        discount_type = _parse_optional_enum(
            raw_product.get("discount_type"),
            DiscountType,
            warnings,
        )
        discount_value = _decimal_or_none(
            raw_product.get("discount_value"), warnings, "İndirim değeri"
        )
        base_price_type = _parse_optional_enum(
            raw_product.get("base_price_type"),
            BasePriceType,
            warnings,
        )
        applies_per_unit = raw_product.get("applies_per_unit")
        if not isinstance(applies_per_unit, bool):
            applies_per_unit = None
        gift_price = _decimal_or_none(
            raw_product.get("gift_price"), warnings, "Hediye fiyatı"
        )
        target_type = _text(raw_product.get("target_type")) or (
            "category"
            if raw_product.get("category_id")
            or raw_product.get("category_name")
            else "product"
        )
        if target_type == "category":
            category = _resolve_category(
                uow,
                raw_product.get("category_id"),
                _text(raw_product.get("category_name")) or product_name,
            )
            if category is None:
                warnings.append(
                    f"Kategori bulunamadı: {product_name or raw_product.get('category_id')}"
                )
                continue
            key = (category.id, relation.value)
            if key in seen_product_relations:
                continue
            seen_product_relations.add(key)
            products.append(
                CampaignProductInput(
                    category_id=category.id,
                    relation_type=relation,
                    discount_type=discount_type,
                    discount_value=discount_value,
                    base_price_type=base_price_type,
                    applies_per_unit=applies_per_unit,
                    gift_price=gift_price,
                )
            )
            continue
        product = _resolve_product(lookup, product_id, product_name)
        if product is None:
            if can_create and auto_create_products:
                product = _create_missing_product(
                    uow, lookup, product_id, product_name
                )
                if product is not None:
                    created_product_names.append(product.name)
            if product is None:
                missing_products += 1
                if product_name or product_id:
                    missing_names.append(product_name or product_id or "—")
                continue
        key = (product.id, relation.value)
        if key in seen_product_relations:
            continue
        seen_product_relations.add(key)
        products.append(
            CampaignProductInput(
                product_id=product.id,
                relation_type=relation,
                quantity_required=quantity,
                discount_type=discount_type,
                discount_value=discount_value,
                base_price_type=base_price_type,
                applies_per_unit=applies_per_unit,
                gift_price=gift_price,
            )
        )
    if missing_products:
        sample = ", ".join(missing_names[:3])
        if len(missing_names) > 3:
            sample += "…"
        action = (
            "içe aktarımda otomatik oluşturulacak"
            if not auto_create_products
            else "atlandı (ad/ID eksik)"
        )
        warnings.append(
            f"{missing_products} ürün Bayios kataloğunda bulunamadı "
            f"({sample}); {action}."
        )
    if created_product_names:
        sample = ", ".join(created_product_names[:3])
        if len(created_product_names) > 3:
            sample += "…"
        warnings.append(
            f"{len(created_product_names)} ürün otomatik oluşturuldu: {sample}."
        )
    if not products and raw_products:
        warnings.append("Hiçbir kampanya ürünü eşleşmedi; yalnızca koşullar aktarılacak.")

    date_text = (
        _text(raw.get("date_text"))
        or f"{_format_date(start_value)} – {_format_date(end_value)}"
    )

    existing_id: uuid.UUID | None = None
    if target_campaign is not None and target_version is not None:
        existing_id = target_campaign.id
        if (
            external_id
            and target_campaign.external_id
            and external_id != target_campaign.external_id
        ):
            warnings.append(
                "JSON ID'si hedef kampanyanın ID'sinden farklı; hedef kampanya güncellenecek."
            )
        if (
            name
            and name != target_version.name
        ):
            warnings.append(
                "JSON adı hedef kampanyadan farklı; hedef kampanyanın adı güncellenecek."
            )
    elif external_id:
        owner = uow.campaigns.get_by_external_id(external_id)
        if owner is not None:
            existing_id = owner.id
        if external_id in seen_ids:
            warnings.append(
                "Aynı kampanya ID'si dosyada tekrar ediyor; ilk kayıt işlendi."
            )
            errors.append("Tekrarlanan kampanya ID'si atlandı.")
    if existing_id is None and name and start_value and end_value:
        match = existing_by_key.get(
            (normalize_product_name(name), start_value, end_value)
        )
        if match is not None:
            existing_id = match.id
    if external_id:
        seen_ids.add(external_id)
    key = (
        external_id
        or f"{normalize_product_name(name)}|{start_value}|{end_value}"
    )
    if key in seen_keys:
        warnings.append("Aynı kampanya dosyada tekrar ediyor; ilk kayıt işlendi.")
        errors.append("Tekrarlanan kampanya satırı atlandı.")
    seen_keys.add(key)

    if existing_id is not None and not has_explicit_rules:
        current_version = uow.campaigns.get_current_version(existing_id)
        if current_version is not None:
            existing_links = uow.campaigns.get_version_products(
                current_version.id
            )
            by_product = {
                link.product_id: link
                for link in existing_links
                if link.product_id is not None
                and getattr(link, "category_id", None) is None
            }
            preserved: list[CampaignProductInput] = []
            for input_item in products:
                link = (
                    by_product.get(input_item.product_id)
                    if input_item.product_id is not None
                    else None
                )
                if link is None:
                    preserved.append(input_item)
                    continue
                preserved.append(
                    CampaignProductInput(
                        product_id=input_item.product_id,
                        relation_type=ProductRelationType(link.relation_type),
                        quantity_required=input_item.quantity_required,
                        discount_type=(
                            DiscountType(link.discount_type)
                            if getattr(link, "discount_type", None)
                            else None
                        ),
                        discount_value=getattr(link, "discount_value", None),
                        base_price_type=(
                            BasePriceType(link.base_price_type)
                            if getattr(link, "base_price_type", None)
                            else None
                        ),
                        applies_per_unit=getattr(
                            link, "applies_per_unit", None
                        ),
                    )
                )
            for link in existing_links:
                if getattr(link, "category_id", None) is None:
                    continue
                preserved.append(
                    CampaignProductInput(
                        category_id=link.category_id,
                        relation_type=ProductRelationType(link.relation_type),
                        discount_type=(
                            DiscountType(link.discount_type)
                            if getattr(link, "discount_type", None)
                            else None
                        ),
                        discount_value=getattr(link, "discount_value", None),
                        base_price_type=(
                            BasePriceType(link.base_price_type)
                            if getattr(link, "base_price_type", None)
                            else None
                        ),
                        applies_per_unit=getattr(
                            link, "applies_per_unit", None
                        ),
                    )
                )
            products = preserved
            combines_with_others = (
                True
                if getattr(current_version, "combines_with_others", True)
                is None
                else bool(current_version.combines_with_others)
            )
            exclusion_group = getattr(
                current_version, "exclusion_group", None
            )
            min_basket_total = getattr(
                current_version, "min_basket_total", None
            )
            if not has_payment_conditions_key:
                payment_conditions = _parse_payment_conditions(
                    uow,
                    getattr(current_version, "payment_conditions", None),
                    warnings,
                )
            warnings.append(
                "Mevcut kampanya kuralları (şart/fayda ve kategori hedefleri) korundu."
            )

    if existing_id is not None and not has_payment_conditions_key:
        current_version = uow.campaigns.get_current_version(existing_id)
        if current_version is not None:
            payment_conditions = _parse_payment_conditions(
                uow,
                getattr(current_version, "payment_conditions", None),
                warnings,
            )

    data: CampaignInput | None = None
    if not errors:
        data = CampaignInput(
            name=name,
            campaign_type=CampaignType(str(campaign_type_value)),
            starts_at=starts_at,
            ends_at=ends_at,
            base_price_type=BasePriceType(
                str(campaign_base_price_type_value)
            ),
            description=None,
            discount_type=DiscountType(str(campaign_discount_type_value)),
            discount_value=campaign_discount_value,
            gift_description=gift_description,
            gift_optional=gift_optional,
            gift_yes_base_price_type=(
                BasePriceType(str(gift_yes_base_price_type))
                if gift_yes_base_price_type is not None
                else None
            ),
            gift_no_base_price_type=(
                BasePriceType(str(gift_no_base_price_type))
                if gift_no_base_price_type is not None
                else None
            ),
            employee_note=employee_note,
            external_id=external_id,
            source_url=source_url,
            conditions=conditions,
            source_category=source_category,
            source_product_count=(
                product_count if product_count is not None else len(raw_products)
            ),
            combines_with_others=combines_with_others,
            exclusion_group=exclusion_group,
            min_basket_total=min_basket_total,
            payment_conditions=payment_conditions,
            scraped_at=scraped_at,
            products=tuple(products),
        )
    decision = "error" if errors else ("update" if existing_id else "create")
    return _JsonCampaign(
        key=key,
        row_number=row_number,
        external_id=external_id,
        name=name or "—",
        starts_at=starts_at,
        ends_at=ends_at,
        date_text=date_text,
        source_category=source_category,
        conditions=conditions,
        source_product_count=(
            product_count if product_count is not None else len(raw_products)
        ),
        resolved_product_count=len(products),
        existing_id=existing_id,
        data=data,
        errors=tuple(errors),
        warnings=tuple(warnings),
        decision=decision,
    )


def _error_campaign(row_number: int, message: str) -> _JsonCampaign:
    now = datetime.now(UTC)
    return _JsonCampaign(
        key=f"row:{row_number}",
        row_number=row_number,
        external_id=None,
        name="—",
        starts_at=now,
        ends_at=now,
        date_text="—",
        source_category=None,
        conditions=(),
        source_product_count=0,
        resolved_product_count=0,
        existing_id=None,
        data=None,
        errors=(message,),
        warnings=(),
        decision="error",
    )


def _resolve_product(
    lookup: ProductLookup, product_id: str | None, product_name: str
) -> Any | None:
    if product_id:
        product = lookup.by_external_id.get(product_id) or lookup.by_alias.get(
            product_id
        )
        if product is not None:
            return product
    if not product_name:
        return None
    matches = lookup.by_name.get(normalize_product_name(product_name), ())
    if len(matches) == 1:
        return matches[0]
    return None


def _create_missing_product(
    uow: UnitOfWork,
    lookup: ProductLookup,
    product_id: str | None,
    product_name: str,
) -> Product | None:
    name = (product_name or product_id or "").strip()
    if not name:
        return None
    if not product_id:
        matches = lookup.by_name.get(normalize_product_name(name), ())
        if len(matches) > 1:
            return None
    now = datetime.now(UTC)
    product = Product(
        id=uuid.uuid4(),
        external_id=product_id or None,
        name=name,
        name_normalized=normalize_product_name(name),
        regular_price=None,
        website_discounted_price=None,
        cost_price=None,
        physical_stock=0,
        kind="product",
        is_archived=False,
        created_at=now,
        updated_at=now,
        last_seen_at=now,
        last_price_changed_at=None,
    )
    uow.products.add(product)
    if product_id:
        lookup.by_external_id[product_id] = product
    lookup.by_name.setdefault(product.name_normalized, []).append(product)
    lookup.by_id[product.id] = product
    return product


def _parse_relation(
    value: object, warnings: list[str]
) -> ProductRelationType:
    normalized = normalize_header(value)
    if not normalized:
        return ProductRelationType.RELATED
    relation = _RELATION_LABELS.get(normalized)
    if relation is None:
        warnings.append(f"Bilinmeyen ürün ilişkisi: {_text(value)}; ilgili ürün sayıldı.")
        return ProductRelationType.RELATED
    return relation


def _parse_date(
    value: object, label: str, errors: list[str]
) -> date | None:
    text = _text(value)
    if not text:
        errors.append(f"{label} zorunludur.")
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        errors.append(f"{label} geçerli bir ISO tarih değil: {text}")
        return None


def _parse_datetime(value: object, warnings: list[str]) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        warnings.append(f"scraped_at geçersiz: {text}")
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _text_list(
    value: object, warnings: list[str], label: str
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        warnings.append(f"{label} listesi geçersiz; yok sayıldı.")
        return ()
    result = []
    for item in value:
        text = _text(item)
        if text:
            result.append(text)
    return tuple(result)


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _positive_int_or_none(value: object) -> int | None:
    parsed = _int_or_none(value)
    return parsed if parsed and parsed > 0 else None


def _resolve_payment_banks(
    uow: UnitOfWork, raw: dict, warnings: list[str]
) -> tuple[str, ...]:
    bank_ids: list[str] = []
    for raw_id in raw.get("bank_ids") or ():
        value = str(raw_id).strip()
        if value:
            bank_ids.append(value)
    for raw_name in raw.get("bank_names") or ():
        name = str(raw_name).strip()
        if not name:
            continue
        bank = uow.commissions.get_bank_by_normalized(normalize_name(name))
        if bank is None:
            warnings.append(f"Ödeme koşulundaki banka bulunamadı: {name}")
            continue
        bank_ids.append(str(bank.id))
    return tuple(dict.fromkeys(bank_ids))


def _parse_payment_conditions(
    uow: UnitOfWork, value: object, warnings: list[str]
) -> tuple[CampaignPaymentCondition, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        warnings.append("Ödeme koşulları listesi geçersiz; atlandı.")
        return ()
    conditions: list[CampaignPaymentCondition] = []
    for raw in value:
        if not isinstance(raw, dict):
            warnings.append("Ödeme koşulu satırı geçersiz; atlandı.")
            continue
        try:
            conditions.append(
                CampaignPaymentCondition(
                    channel=_text(raw.get("channel")) or None,
                    bank_ids=_resolve_payment_banks(uow, raw, warnings),
                    card_type=_text(raw.get("card_type")) or None,
                    card_network=_text(raw.get("card_network")) or None,
                    installment_count=_int_or_none(
                        raw.get("installment_count")
                    ),
                )
            )
        except ValueError as exc:
            warnings.append(f"Ödeme koşulu geçersiz: {exc}")
    return tuple(conditions)


def _enum_or_default(
    value: object,
    enum_type: type,
    default: object,
    warnings: list[str],
) -> object:
    parsed = _parse_optional_enum(value, enum_type, warnings)
    return default if parsed is None else parsed


def _parse_optional_enum(
    value: object,
    enum_type: type,
    warnings: list[str],
) -> object | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        return enum_type(raw)
    except ValueError:
        labels = getattr(enum_type, "__members__", {})
        lowered = raw.strip().lower()
        for member in labels.values():
            if member.value.lower() == lowered or member.name.lower() == lowered:
                return member
        warnings.append(f"Geçersiz değer: {raw}")
        return None


def _decimal_or_none(
    value: object, warnings: list[str], label: str
) -> object | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return parse_decimal(value, label)
    except (TypeError, ValueError) as exc:
        warnings.append(str(exc))
        return None


def _resolve_category(
    uow: UnitOfWork,
    raw_category_id: object,
    category_name: str,
) -> object | None:
    raw_id = _text(raw_category_id)
    if raw_id:
        try:
            category = uow.products.get_category(uuid.UUID(raw_id))
        except ValueError:
            category = None
        if category is not None:
            return category
    if category_name:
        normalized = normalize_category_name(category_name)
        for category in uow.products.get_categories():
            if getattr(category, "name_normalized", None) == normalized:
                return category
            if normalize_category_name(category.name) == normalized:
                return category
    return None


def _text(value: object) -> str:
    return str(value or "").strip()


def _format_date(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value is not None else "—"
