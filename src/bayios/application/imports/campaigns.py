from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from bayios.application.campaigns import (
    CampaignInput,
    CampaignProductInput,
    _build_contract,
    create_campaign_in_uow,
    update_campaign_in_uow,
)
from bayios.application.errors import ImportFormatError, ValidationError
from bayios.application.imports.common import (
    ImportPreview,
    ImportResult,
    PreviewRow,
    record_batch,
    replay_result,
)
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.tabular import (
    RawSheet,
    first_sheet,
    locate_header,
    normalize_header,
    parse_bool,
    parse_date,
    parse_decimal,
    parse_enum,
    parse_int,
    read_raw_sheets,
    row_value,
    sheet_named,
)
from bayios.domain.campaigns import (
    BASE_PRICE_TYPE_LABELS,
    CAMPAIGN_TYPE_LABELS,
    DISCOUNT_TYPE_LABELS,
    PRODUCT_RELATION_TYPE_LABELS,
    BasePriceType,
    CampaignType,
    DiscountType,
    ProductRelationType,
)
from bayios.domain.products import ActorContext, normalize_product_name

CAMPAIGN_HEADERS = {
    "campaign_id": ("Kampanya ID", "campaign_id", "id"),
    "name": ("Kampanya Adı", "Kampanya Adi", "campaign_name", "name"),
    "description": ("Açıklama", "Aciklama", "description"),
    "campaign_type": ("Kampanya Tipi", "Kampanya Tipi", "campaign_type"),
    "starts_at": ("Başlangıç Tarihi", "Baslangic Tarihi", "starts_at"),
    "ends_at": ("Bitiş Tarihi", "Bitis Tarihi", "ends_at"),
    "base_price_type": ("Fiyat Tabanı", "Fiyat Tabani", "base_price_type"),
    "discount_type": ("İndirim Türü", "Indirim Turu", "discount_type"),
    "discount_value": ("İndirim Değeri", "Indirim Degeri", "discount_value"),
    "gift_description": ("Hediye Açıklaması", "Hediye Aciklamasi", "gift_description"),
    "gift_optional": ("Hediye İsteğe Bağlı", "Hediye Isteğe Bagli", "gift_optional"),
    "gift_yes_base_price_type": (
        "Hediye Varsa Taban",
        "gift_yes_base_price_type",
    ),
    "gift_no_base_price_type": (
        "Hediye Yoksa Taban",
        "gift_no_base_price_type",
    ),
    "employee_note": ("Çalışan Notu", "Calisan Notu", "employee_note"),
    "product_name": ("Ürün Adı", "Urun Adi", "product_name"),
    "relation_type": ("İlişki Türü", "Iliski Turu", "relation_type"),
    "quantity_required": ("Gerekli Adet", "quantity_required"),
}

PRODUCT_HEADERS = {
    "campaign_id": ("Kampanya ID", "campaign_id", "id"),
    "campaign_name": ("Kampanya Adı", "Kampanya Adi", "campaign_name", "name"),
    "starts_at": ("Başlangıç Tarihi", "Baslangic Tarihi", "starts_at"),
    "ends_at": ("Bitiş Tarihi", "Bitis Tarihi", "ends_at"),
    "product_name": ("Ürün Adı", "Urun Adi", "product_name"),
    "relation_type": ("İlişki Türü", "Iliski Turu", "relation_type"),
    "quantity_required": ("Gerekli Adet", "quantity_required"),
}

DECISION_OPTIONS = (
    ("create", "Yeni Kampanya"),
    ("update", "Güncelle"),
    ("skip", "Atla"),
)


@dataclass(frozen=True)
class _CampaignEntity:
    key: str
    row_number: int
    campaign_id: uuid.UUID | None
    existing_id: uuid.UUID | None
    name: str
    starts_at: datetime
    ends_at: datetime
    data: CampaignInput | None
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    decision: str
    product_count: int = 0


def preview_campaign_import(
    uow: UnitOfWork,
    source: bytes,
    *,
    target_campaign_id: uuid.UUID | None = None,
) -> ImportPreview:
    with uow:
        entities, unknown = _parse_campaigns(
            uow, source, target_campaign_id=target_campaign_id
        )
    rows = tuple(
        PreviewRow(
            key=entity.key,
            row_number=entity.row_number,
            decision=entity.decision,
            summary=entity.name,
            values={
                "name": entity.name,
                "starts_at": entity.starts_at.strftime("%d.%m.%Y"),
                "ends_at": entity.ends_at.strftime("%d.%m.%Y"),
                "type": (
                    CAMPAIGN_TYPE_LABELS[entity.data.campaign_type]
                    if entity.data is not None
                    else ""
                ),
                "discount": (
                    DISCOUNT_TYPE_LABELS[entity.data.discount_type]
                    if entity.data is not None
                    else ""
                ),
                "products": entity.product_count,
                "status": (
                    "Güncellenecek"
                    if entity.existing_id
                    else "Yeni"
                ),
            },
            errors=entity.errors,
            warnings=entity.warnings,
        )
        for entity in entities
    )
    return ImportPreview(
        module="campaigns",
        title="Kampanya Excel İçe Aktarma Önizlemesi",
        entity_label="kampanya",
        columns=(
            ("name", "Kampanya Adı"),
            ("starts_at", "Başlangıç"),
            ("ends_at", "Bitiş"),
            ("type", "Tip"),
            ("discount", "İndirim"),
            ("products", "Ürün"),
            ("status", "Durum"),
        ),
        rows=rows,
        decision_options=DECISION_OPTIONS,
        unknown_headers=unknown,
    )


def commit_campaign_import(
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
        entities, _unknown = _parse_campaigns(
            uow, source, target_campaign_id=target_campaign_id
        )
        now = datetime.now(UTC)
        created = updated = skipped = errors = 0
        for entity in entities:
            if entity.errors or entity.data is None:
                errors += 1
                continue
            decision = decisions.get(entity.key) or entity.decision
            if decision == "skip":
                skipped += 1
                continue
            if entity.existing_id is not None and decision != "create":
                _campaign, changed = update_campaign_in_uow(
                    uow,
                    entity.existing_id,
                    entity.data,
                    actor=actor,
                    now=now,
                )
                if changed:
                    updated += 1
                else:
                    skipped += 1
            else:
                create_campaign_in_uow(uow, entity.data, actor=actor, now=now)
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
            total_count=len(entities),
            actor=actor,
            now=now,
        )
        uow.commit()
        return result


def _parse_campaigns(
    uow: UnitOfWork,
    source: bytes,
    *,
    target_campaign_id: uuid.UUID | None = None,
) -> tuple[list[_CampaignEntity], tuple[str, ...]]:
    target_campaign = None
    target_version = None
    if target_campaign_id is not None:
        target_campaign = uow.campaigns.get(target_campaign_id)
        target_version = uow.campaigns.get_current_version(target_campaign_id)
        if target_campaign is None or target_version is None:
            raise ImportFormatError("Kampanya bulunamadı.")
    sheets = read_raw_sheets(source)
    campaign_sheet = sheet_named(
        sheets, ("Kampanyalar", "Campaigns", "Kampanya")
    )
    if campaign_sheet is None and target_campaign is not None and target_version is not None:
        product_source = sheet_named(
            sheets,
            (
                "Kampanya Ürünleri",
                "Kampanya Urunleri",
                "Campaign Products",
                "Ürünler",
                "Urunler",
            ),
        )
        if product_source is not None:
            campaign_sheet = RawSheet(
                name="Kampanyalar",
                rows=(
                    ("Kampanya Adı", "Başlangıç Tarihi", "Bitiş Tarihi"),
                    (
                        target_version.name,
                        target_version.starts_at.date(),
                        target_version.ends_at.date(),
                    ),
                ),
            )
        else:
            campaign_sheet = first_sheet(sheets)
    if campaign_sheet is None:
        campaign_sheet = first_sheet(sheets)
    campaign_layout = locate_header(
        campaign_sheet.rows,
        CAMPAIGN_HEADERS,
        required=("name", "starts_at", "ends_at"),
        sheet_label=campaign_sheet.name,
    )
    flat = "product_name" in campaign_layout.indexes
    product_sheet = sheet_named(
        sheets,
        ("Kampanya Ürünleri", "Kampanya Urunleri", "Campaign Products"),
    )
    product_layout = None
    if product_sheet is not None:
        product_layout = locate_header(
            product_sheet.rows,
            PRODUCT_HEADERS,
            required=("product_name",),
            sheet_label=product_sheet.name,
        )

    warnings: tuple[str, ...] = tuple(
        f"Tanınmayan kolon: {header}" for header in campaign_layout.unknown_headers
    )
    grouped: dict[str, dict[str, object]] = {}
    order: list[str] = []

    def add_product(row: dict[str, object], values: dict[str, object]) -> None:
        name = str(values.get("product_name") or "").strip()
        if not name:
            return
        raw_relation = values.get("relation_type")
        try:
            relation_value = parse_enum(
                raw_relation,
                "Ürün ilişkisi",
                {item.value: label for item, label in PRODUCT_RELATION_TYPE_LABELS.items()},
                default=ProductRelationType.RELATED.value,
            )
            relation = ProductRelationType(str(relation_value))
        except ValueError as exc:
            row.setdefault("errors", []).append(str(exc))
            return
        try:
            quantity = parse_int(
                values.get("quantity_required"), "Gerekli adet", minimum=1
            )
        except ValueError as exc:
            row.setdefault("errors", []).append(str(exc))
            return
        row.setdefault("products", []).append(
            (name, relation, quantity)
        )

    for offset, raw in enumerate(campaign_sheet.rows[campaign_layout.row_index + 1 :], start=1):
        row_number = campaign_layout.row_index + 2 + offset
        name = str(row_value(raw, campaign_layout, "name") or "").strip()
        if not name:
            continue
        starts_raw = row_value(raw, campaign_layout, "starts_at")
        ends_raw = row_value(raw, campaign_layout, "ends_at")
        if not starts_raw and not ends_raw:
            continue
        errors: list[str] = []
        try:
            starts_date = parse_date(starts_raw, "Başlangıç tarihi")
            if starts_date is None:
                errors.append("Başlangıç tarihi zorunludur.")
                starts_at = datetime.now(UTC)
            else:
                starts_at = datetime(
                    starts_date.year, starts_date.month, starts_date.day, tzinfo=UTC
                )
        except ValueError as exc:
            errors.append(str(exc))
            starts_at = datetime.now(UTC)
        try:
            ends_date = parse_date(ends_raw, "Bitiş tarihi")
            if ends_date is None:
                errors.append("Bitiş tarihi zorunludur.")
                ends_at = starts_at
            else:
                ends_at = datetime(
                    ends_date.year, ends_date.month, ends_date.day, tzinfo=UTC
                )
        except ValueError as exc:
            errors.append(str(exc))
            ends_at = starts_at
        if ends_at < starts_at:
            errors.append("Bitiş tarihi başlangıçtan önce olamaz.")

        raw_id = str(row_value(raw, campaign_layout, "campaign_id") or "").strip()
        campaign_id: uuid.UUID | None = None
        if raw_id:
            try:
                campaign_id = uuid.UUID(raw_id)
            except ValueError:
                errors.append("Kampanya ID geçersiz.")

        key = (
            str(campaign_id)
            if campaign_id is not None
            else f"{normalize_header(name)}|{starts_at.isoformat()}|{ends_at.isoformat()}"
        )
        if key not in grouped:
            grouped[key] = {
                "row_number": row_number,
                "campaign_id": campaign_id,
                "name": name,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "raw": raw,
                "errors": errors,
                "products": [],
            }
            order.append(key)
        else:
            current = grouped[key]
            if flat:
                if str(current["name"]) != name:
                    current["errors"].append("Aynı anahtarda farklı kampanya adı var.")
            else:
                current["errors"].append("Kampanya dosyada birden fazla kez var.")
            current["errors"].extend(errors)

        if flat:
            add_product(
                grouped[key],
                {
                    "product_name": row_value(raw, campaign_layout, "product_name"),
                    "relation_type": row_value(raw, campaign_layout, "relation_type"),
                    "quantity_required": row_value(
                        raw, campaign_layout, "quantity_required"
                    ),
                },
            )

    if product_sheet is not None and product_layout is not None:
        for raw in product_sheet.rows[product_layout.row_index + 1 :]:
            raw_id = str(row_value(raw, product_layout, "campaign_id") or "").strip()
            raw_name = str(
                row_value(raw, product_layout, "campaign_name") or ""
            ).strip()
            key = ""
            if raw_id:
                try:
                    key = str(uuid.UUID(raw_id))
                except ValueError:
                    pass
            if not key and raw_name:
                try:
                    raw_start = parse_date(
                        row_value(raw, product_layout, "starts_at"), "Başlangıç tarihi"
                    )
                    raw_end = parse_date(
                        row_value(raw, product_layout, "ends_at"), "Bitiş tarihi"
                    )
                    if raw_start and raw_end:
                        key = (
                            f"{normalize_header(raw_name)}|"
                            f"{datetime(raw_start.year, raw_start.month, raw_start.day, tzinfo=UTC).isoformat()}|"
                            f"{datetime(raw_end.year, raw_end.month, raw_end.day, tzinfo=UTC).isoformat()}"
                        )
                except ValueError:
                    key = ""
            if (
                target_campaign_id is not None
                and len(grouped) == 1
                and key not in grouped
            ):
                key = order[0]
            if key not in grouped:
                continue
            add_product(
                grouped[key],
                {
                    "product_name": row_value(raw, product_layout, "product_name"),
                    "relation_type": row_value(raw, product_layout, "relation_type"),
                    "quantity_required": row_value(
                        raw, product_layout, "quantity_required"
                    ),
                },
            )

    entities: list[_CampaignEntity] = []
    for key in order:
        item = grouped[key]
        errors = list(item["errors"])  # type: ignore[arg-type]
        product_links = item["products"]  # type: ignore[assignment]
        raw = item["raw"]
        assert isinstance(raw, tuple)
        try:
            campaign_type = parse_enum(
                row_value(raw, campaign_layout, "campaign_type"),
                "Kampanya tipi",
                {item.value: label for item, label in CAMPAIGN_TYPE_LABELS.items()},
                default=CampaignType.GENERAL.value,
            )
            base_price_type = parse_enum(
                row_value(raw, campaign_layout, "base_price_type"),
                "Fiyat tabanı",
                {item.value: label for item, label in BASE_PRICE_TYPE_LABELS.items()},
                default=BasePriceType.REGULAR.value,
            )
            discount_type = parse_enum(
                row_value(raw, campaign_layout, "discount_type"),
                "İndirim türü",
                {item.value: label for item, label in DISCOUNT_TYPE_LABELS.items()},
                default=DiscountType.INFO_ONLY.value,
            )
            discount_value = parse_decimal(
                row_value(raw, campaign_layout, "discount_value"), "İndirim değeri"
            )
            gift_optional = parse_bool(
                row_value(raw, campaign_layout, "gift_optional"),
                "Hediye isteğe bağlı",
            )
            gift_yes = parse_enum(
                row_value(raw, campaign_layout, "gift_yes_base_price_type"),
                "Hediye varsa taban",
                {item.value: label for item, label in BASE_PRICE_TYPE_LABELS.items()},
                default=None,
            )
            gift_no = parse_enum(
                row_value(raw, campaign_layout, "gift_no_base_price_type"),
                "Hediye yoksa taban",
                {item.value: label for item, label in BASE_PRICE_TYPE_LABELS.items()},
                default=None,
            )
        except ValueError as exc:
            errors.append(str(exc))
            campaign_type = CampaignType.GENERAL.value
            base_price_type = BasePriceType.REGULAR.value
            discount_type = DiscountType.INFO_ONLY.value
            discount_value = None
            gift_optional = None
            gift_yes = None
            gift_no = None

        product_names = [str(link[0]) for link in product_links]  # type: ignore[index]
        products_by_name = (
            uow.products.get_by_normalized_names(
                [normalize_product_name(name) for name in product_names]
            )
            if product_names
            else {}
        )
        inputs: list[CampaignProductInput] = []
        seen: set[tuple[uuid.UUID, str]] = set()
        for product_name, relation, quantity in product_links:  # type: ignore[misc]
            product = products_by_name.get(normalize_product_name(product_name))
            if product is None:
                errors.append(f"Ürün bulunamadı: {product_name}")
                continue
            relation_value = (
                relation.value if isinstance(relation, ProductRelationType) else str(relation)
            )
            key_pair = (product.id, relation_value)
            if key_pair in seen:
                errors.append(f"Aynı ürün ilişkisi tekrar ediyor: {product_name}")
                continue
            seen.add(key_pair)
            inputs.append(
                CampaignProductInput(
                    product_id=product.id,
                    relation_type=ProductRelationType(relation_value),
                    quantity_required=quantity,
                )
            )

        data = CampaignInput(
            name=str(item["name"]),
            campaign_type=CampaignType(str(campaign_type)),
            starts_at=item["starts_at"],  # type: ignore[arg-type]
            ends_at=item["ends_at"],  # type: ignore[arg-type]
            base_price_type=BasePriceType(str(base_price_type)),
            description=str(
                row_value(raw, campaign_layout, "description") or ""
            ).strip()
            or None,
            discount_type=DiscountType(str(discount_type)),
            discount_value=discount_value,
            gift_description=str(
                row_value(raw, campaign_layout, "gift_description") or ""
            ).strip()
            or None,
            gift_optional=bool(gift_optional),
            gift_yes_base_price_type=(
                BasePriceType(str(gift_yes)) if gift_yes else None
            ),
            gift_no_base_price_type=(
                BasePriceType(str(gift_no)) if gift_no else None
            ),
            employee_note=str(
                row_value(raw, campaign_layout, "employee_note") or ""
            ).strip()
            or None,
            products=tuple(inputs),
        )
        try:
            _build_contract(uow, data)
        except (ValidationError, ValueError) as exc:
            errors.append(str(exc))

        campaign_id = item["campaign_id"]  # type: ignore[assignment]
        if target_campaign_id is not None:
            if campaign_id is not None and campaign_id != target_campaign_id:
                warnings = (
                    *warnings,
                    "Kampanya ID yok sayıldı; detaydaki kampanya güncellenecek.",
                )
            campaign_id = target_campaign_id
            existing_id = target_campaign_id
            key = str(target_campaign_id)
        else:
            try:
                existing_id = _find_existing_campaign(
                    uow,
                    campaign_id=campaign_id,  # type: ignore[arg-type]
                    name=data.name,
                    starts_at=data.starts_at,
                    ends_at=data.ends_at,
                )
            except ImportFormatError as exc:
                errors.append(str(exc))
                existing_id = None
            if campaign_id is not None and existing_id is None:
                errors.append("Kampanya ID bulunamadı.")
        decision = "error" if errors else ("update" if existing_id else "create")
        entities.append(
            _CampaignEntity(
                key=key,
                row_number=int(item["row_number"]),  # type: ignore[arg-type]
                campaign_id=campaign_id,  # type: ignore[arg-type]
                existing_id=existing_id,
                name=data.name,
                starts_at=data.starts_at,
                ends_at=data.ends_at,
                data=data if not errors else None,
                errors=tuple(errors),
                warnings=warnings,
                decision=decision,
                product_count=len(inputs),
            )
        )
    if target_campaign_id is not None and len(entities) != 1:
        raise ImportFormatError(
            "Detay içe aktarması tek kampanya içermelidir."
        )
    entities.sort(key=lambda entity: (0 if entity.errors else 1, entity.row_number))
    return entities, warnings


def _find_existing_campaign(
    uow: UnitOfWork,
    *,
    campaign_id: uuid.UUID | None,
    name: str,
    starts_at: datetime,
    ends_at: datetime,
) -> uuid.UUID | None:
    if campaign_id is not None:
        campaign = uow.campaigns.get(campaign_id)
        return campaign.id if campaign is not None else None
    rows, _ = uow.campaigns.list(
        query=name, state=None, as_of=datetime.now(UTC), limit=1000
    )
    normalized_name = normalize_header(name)
    matches = [
        campaign.id
        for campaign, version in rows
        if normalize_header(version.name) == normalized_name
        and version.starts_at == starts_at
        and version.ends_at == ends_at
    ]
    if len(matches) > 1:
        raise ImportFormatError(
            f"'{name}' için birden fazla kampanya eşleşti; Kampanya ID kullanın."
        )
    return matches[0] if matches else None
