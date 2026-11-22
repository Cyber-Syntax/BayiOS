from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from bayios.adapters.db.models.inventory import StockMovement
from bayios.adapters.db.models.products import (
    Product,
    ProductCategory,
    ProductExternalIdHistory,
    ProductImportBatch,
    ProductPriceHistory,
)
from bayios.application.dealer_pricing import apply_dealer_pricing_values
from bayios.application.errors import ImportFormatError
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.tabular import (
    ColumnSpec,
    SheetSpec,
    normalize_header,
    write_xlsx,
)
from bayios.domain.commissions import commission_group_for_category_name
from bayios.domain.naming import canonical_display_name
from bayios.domain.products import (
    ActorContext,
    normalize_category_name,
    normalize_product_name,
)
from bayios.domain.products.details import ProductDetails


@dataclass(frozen=True)
class ProductImportRow:
    row_number: int
    decision: str
    external_id: str | None = None
    product_name: str | None = None
    category_name: str | None = None
    regular_price: str | None = None
    website_discounted_price: str | None = None
    quantity: str | None = None
    cost_price: str | None = None
    cash_floor_price: str | None = None
    card_floor_price: str | None = None
    active_campaigns: str | None = None
    kind: str | None = None
    kind_present: bool = False
    source_url: str | None = None
    scraped_at: str | None = None
    details: dict[str, object] | None = None
    details_present: bool = False
    details_error: str | None = None
    clear_cost_price: bool = False
    clear_cash_floor_price: bool = False
    clear_card_floor_price: bool = False
    clear_website_discounted_price: bool = False
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def is_problematic(self) -> bool:
        return bool(
            self.errors
            or self.warnings
            or self.details_error
            or self.decision == "error"
        )


@dataclass(frozen=True)
class ProductImportPreview:
    rows: tuple[ProductImportRow, ...]
    source_type: str = "csv"
    schema_version: str | None = None
    catalog_scraped_at: str | None = None


@dataclass(frozen=True)
class ProductImportCommitResult:
    batch_id: uuid.UUID
    created_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    total_count: int


WEBSITE_PRICE_HEADERS = (
    "website_discounted_price",
    "website discounted price",
    "oliz indirimli fiyat",
    "oliz fiyatı",
    "indirimli fiyat",
)
EXTERNAL_ID_HEADERS = (
    "ürün id",
    "urun id",
    "product id",
    "product_id",
    "external_id",
)
DETAILS_HEADERS = (
    "ürün özellikleri (json)",
    "urun ozellikleri (json)",
    "product details",
    "details",
    "ürün detayları",
    "urun detaylari",
)
KIND_HEADERS = ("kind", "ürün türü", "urun turu", "tür", "tur")
SOURCE_URL_HEADERS = ("source_url", "source url", "kaynak url", "kaynak")
SCRAPED_AT_HEADERS = ("scraped_at", "scraped at", "scrape tarihi")
CURRENCY_HEADERS = ("currency", "para birimi")
PRODUCT_NAME_HEADERS = ("product_name", "product name", "name", "ürün adı", "urun adi")


def preview_product_import(
    source: bytes,
    existing_names: set[str] | None = None,
    known_external_ids: set[str] | None = None,
    existing_name_counts: dict[str, int] | None = None,
) -> ProductImportPreview:
    source_type = _detect_source_type(source)
    rows: list[ProductImportRow] = []
    seen_ids: set[str] = set()
    schema_version: str | None = None
    catalog_scraped_at: str | None = None

    for row_number, raw_row in enumerate(_source_rows(source), start=2):
        if row_number == 2 and not _has_column(raw_row, *PRODUCT_NAME_HEADERS):
            raise ImportFormatError(
                "Başlık satırı tanınamadı. Ürün Adı sütunu bulunamadı."
            )
        if "_schema_version" in raw_row:
            schema_version = str(raw_row.get("_schema_version") or "") or None
            catalog_scraped_at = (
                str(raw_row.get("_catalog_scraped_at") or "") or None
            )

        raw_product_name = _value(raw_row, *PRODUCT_NAME_HEADERS)
        product_name = (
            unicodedata.normalize("NFKC", raw_product_name).strip()
            if raw_product_name
            else ""
        )
        external_id = _clean_external_id(
            _value(raw_row, *EXTERNAL_ID_HEADERS)
        )
        regular_price = _value(
            raw_row,
            "regular_price",
            "regular price",
            "perakende fiyat",
            "normal fiyat",
        )
        oliz_column_present = _has_column(raw_row, *WEBSITE_PRICE_HEADERS)
        discounted_price = _value(raw_row, *WEBSITE_PRICE_HEADERS)
        quantity = _value(
            raw_row, "quantity", "fiziksel stok", "stok", "adet"
        )
        category_name = _value(raw_row, "category", "category_name", "kategori")
        cost_raw = _value(
            raw_row, "cost_price", "cost price", "alış fiyatı", "alis fiyati", "maliyet"
        )
        cash_raw = _value(
            raw_row,
            "cash_floor_price",
            "cash floor price",
            "nakit taban fiyatı",
            "nakit taban fiyati",
        )
        card_raw = _value(
            raw_row,
            "card_floor_price",
            "card floor price",
            "kredi kartı taban fiyatı",
            "kart taban fiyatı",
        )
        active_campaigns = _value(
            raw_row,
            "active_campaigns",
            "active campaign",
            "aktif kampanya",
            "kampanya",
        )
        raw_kind = _value(raw_row, *KIND_HEADERS).strip().casefold()
        source_url = _value(raw_row, *SOURCE_URL_HEADERS).strip() or None
        scraped_at = _value(raw_row, *SCRAPED_AT_HEADERS).strip() or None
        currency = _value(raw_row, *CURRENCY_HEADERS).strip().upper()
        details_raw = _value(raw_row, *DETAILS_HEADERS)

        if category_name:
            category_name = unicodedata.normalize("NFKC", category_name).strip()
        errors: list[str] = []
        warnings: list[str] = []

        if not product_name:
            errors.append("Ürün adı zorunludur.")
        elif not re.fullmatch(r"[0-9A-Z]+(?: [0-9A-Z]+)*", product_name.upper()):
            warnings.append("Ürün adı biçimi kontrol edilmeli.")
        if currency and currency != "TRY":
            warnings.append(f"Para birimi TRY olmalıdır: {currency}")
        kind = _normalize_kind(raw_kind, category_name, warnings)
        kind_present = bool(raw_kind) or (
            bool(category_name)
            and normalize_category_name(category_name) == "ek garanti"
        )
        if scraped_at and _parse_datetime(scraped_at) is None:
            warnings.append("scraped_at geçerli bir ISO tarih değil.")
            scraped_at = None

        normalized_price = _normalize_decimal(regular_price)
        if regular_price and normalized_price is None:
            errors.append("Perakende fiyat sayısal olmalıdır.")
        if normalized_price is not None and Decimal(normalized_price) <= 0:
            normalized_price = None
        normalized_discounted_price, clear_discounted = _optional_price(
            discounted_price, "Oliz indirimli fiyat", errors, positive_only=True
        )
        if oliz_column_present and normalized_discounted_price is None:
            # An empty/zero Oliz cell means the campaign ended; update clears it.
            clear_discounted = True

        normalized_quantity = _normalize_quantity(quantity)
        if quantity and normalized_quantity is None:
            errors.append("Fiziksel stok negatif olmayan tam sayı olmalıdır.")
        normalized_cost, clear_cost = _optional_price(
            cost_raw, "Alış fiyatı", errors
        )
        normalized_cash, clear_cash = _optional_price(
            cash_raw, "Nakit taban fiyatı", errors
        )
        normalized_card, clear_card = _optional_price(
            card_raw, "Kredi kartı taban fiyatı", errors
        )

        details: dict[str, object] | None = None
        details_present = False
        details_error: str | None = None
        if details_raw:
            try:
                parsed_details = ProductDetails.from_json(json.loads(details_raw))
                details = parsed_details.to_dict()
                details_present = True
                if parsed_details.is_empty:
                    # Explicit empty lists clear existing details.
                    details = {"features": [], "specifications": []}
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                details_error = f"Ürün detayı JSON hatası: {exc}"

        if active_campaigns:
            warnings.append(
                "Aktif Kampanya salt okunurdur; kampanyalar sekmesinden yönetilir."
            )

        duplicate_id = False
        if external_id:
            if external_id in seen_ids:
                duplicate_id = True
                warnings.append(
                    "Aynı ürün ID'si dosyada tekrar etti; bu satır atlandı."
                )
            else:
                seen_ids.add(external_id)

        norm_name = (
            normalize_product_name(product_name) if product_name else ""
        )
        if errors:
            decision = "error"
        elif duplicate_id:
            decision = "skip"
        elif external_id and known_external_ids and external_id in known_external_ids:
            decision = "update"
        elif norm_name and existing_names and norm_name in existing_names:
            decision = "update"
            if external_id and not (
                known_external_ids and external_id in known_external_ids
            ):
                warnings.append(
                    "Mevcut ürün ada göre eşleşti; ürün ID'si güncellenecek."
                )
            if (
                existing_name_counts
                and existing_name_counts.get(norm_name, 0) > 1
            ):
                warnings.append(
                    "Aynı ada sahip birden fazla ürün var; ID ile eşleştirme gerekir."
                )
        else:
            decision = "create"

        rows.append(
            ProductImportRow(
                row_number=row_number,
                decision=decision,
                external_id=external_id,
                product_name=product_name or None,
                category_name=category_name or None,
                regular_price=normalized_price,
                website_discounted_price=normalized_discounted_price,
                quantity=normalized_quantity,
                cost_price=normalized_cost,
                cash_floor_price=normalized_cash,
                card_floor_price=normalized_card,
                active_campaigns=active_campaigns or None,
                kind=kind,
                kind_present=kind_present,
                source_url=source_url,
                scraped_at=scraped_at,
                details=details,
                details_present=details_present,
                details_error=details_error,
                clear_cost_price=clear_cost,
                clear_cash_floor_price=clear_cash,
                clear_card_floor_price=clear_card,
                clear_website_discounted_price=clear_discounted,
                errors=tuple(errors),
                warnings=tuple(warnings),
            )
        )

    rows.sort(key=lambda r: (0 if r.is_problematic else 1, r.row_number))
    return ProductImportPreview(
        rows=tuple(rows),
        source_type=source_type,
        schema_version=schema_version,
        catalog_scraped_at=catalog_scraped_at,
    )


def product_import_template() -> bytes:
    sheet = SheetSpec(
        title="Ürünler",
        columns=(
            ColumnSpec("Ürün ID", "external_id", "text", 18),
            ColumnSpec("Ürün Adı", "product_name", "text", 32),
            ColumnSpec("Kategori", "category", "text", 22),
            ColumnSpec("Perakende Fiyat", "regular_price", "money", 16),
            ColumnSpec("Oliz İndirimli Fiyat", "website_discounted_price", "money", 18),
            ColumnSpec("Fiziksel Stok", "physical_stock", "int", 14),
            ColumnSpec("Alış Fiyatı", "cost_price", "money", 14),
            ColumnSpec("Kredi Kartı Taban Fiyatı", "card_floor_price", "money", 22),
            ColumnSpec("Nakit Taban Fiyatı", "cash_floor_price", "money", 20),
            ColumnSpec("Aktif Kampanya", "active_campaigns", "text", 34),
            ColumnSpec("Ürün Özellikleri (JSON)", "details", "text", 60),
            ColumnSpec("scraped_at", "scraped_at", "text", 22),
        ),
        rows=(),
        instructions=(
            ("Ürün ID", "Opsiyonel", "Scraper ID'si; baştaki sıfırlar korunur. Boşsa ada göre eşleşir."),
            ("Ürün Adı", "Zorunlu", "Ürün kimliği; baştaki sıfırlar korunur."),
            ("Kategori", "Opsiyonel", "Boşsa mevcut kategori korunur; yeni ad otomatik oluşturulur."),
            ("Perakende Fiyat", "Opsiyonel", "Boşsa korunur; - yazılırsa temizlenir."),
            ("Oliz İndirimli Fiyat", "Opsiyonel", "Boş veya 0 ise güncellemede mevcut Oliz fiyatı silinir; doluysa güncellenir."),
            ("Fiziksel Stok", "Opsiyonel", "Boşsa korunur; 0 stoğu sıfırlar."),
            ("Alış Fiyatı", "Opsiyonel", "Maliyet fiyatı; boşsa korunur, - temizler."),
            ("Kredi Kartı Taban Fiyatı", "Opsiyonel", "Boşsa korunur; - temizler."),
            ("Nakit Taban Fiyatı", "Opsiyonel", "Boşsa korunur; - temizler."),
            ("Aktif Kampanya", "Salt okunur", "İçe aktarmada kullanılmaz."),
            ("Ürün Özellikleri (JSON)", "Opsiyonel", "features + specifications; boş hücre mevcut detayı korur, boş listeler temizler."),
            ("scraped_at", "Opsiyonel", "ISO tarih; yoksa mevcut değer korunur."),
        ),
    )
    return write_xlsx((sheet,), include_instructions=True)


def commit_product_import(
    uow: UnitOfWork,
    file_name: str,
    file_type: str,
    source: bytes,
    decisions: dict[int | str, str] | None = None,
    actor: ActorContext | None = None,
    commit_token: str | None = None,
) -> ProductImportCommitResult:
    actor = actor or ActorContext()
    source_checksum = hashlib.sha256(source).hexdigest()
    batch_id = uuid.uuid4()
    now = datetime.now(UTC)

    with uow:
        # Check duplicate commit by token or batch idempotency when decisions not provided
        if commit_token or decisions is None:
            check_key = commit_token or source_checksum
            existing_batch = uow.products.get_import_batch_by_checksum(check_key)
            if existing_batch and existing_batch.status == "committed":
                skipped = 0
                if existing_batch.summary and isinstance(existing_batch.summary, dict):
                    skipped = existing_batch.summary.get("skipped_count", 0)
                return ProductImportCommitResult(
                    batch_id=existing_batch.id,
                    created_count=existing_batch.created_count,
                    updated_count=existing_batch.updated_count,
                    skipped_count=skipped,
                    error_count=existing_batch.error_count,
                    total_count=existing_batch.row_count,
                )

        raw_preview = preview_product_import(source)
        all_products = list(uow.products.get_all())
        product_by_id = {product.id: product for product in all_products}
        by_name: dict[str, list[Product]] = {}
        by_external: dict[str, Product] = {}
        for product in all_products:
            by_name.setdefault(product.name_normalized, []).append(product)
            if product.external_id:
                by_external[product.external_id] = product
        by_alias: dict[str, Product] = {}
        for entry in uow.products.get_external_id_history():
            product = product_by_id.get(entry.product_id)
            if product is not None:
                by_alias[entry.external_id] = product

        categories = {c.name: c for c in uow.products.get_categories()}
        categories_by_norm = {
            getattr(category, "name_normalized", None)
            or normalize_category_name(name): category
            for name, category in categories.items()
        }

        def resolve_category(category_name: str | None) -> ProductCategory | None:
            if not category_name:
                return None
            norm = normalize_category_name(category_name)
            existing_category = categories_by_norm.get(norm)
            if existing_category is not None:
                return existing_category
            canonical = canonical_display_name(category_name)
            category = ProductCategory(
                id=uuid.uuid4(),
                name=canonical,
                name_normalized=norm,
                commission_group=commission_group_for_category_name(
                    canonical
                ).value,
            )
            uow.products.add_category(category)
            categories[category.name] = category
            categories_by_norm[norm] = category
            return category

        def remember(product: Product) -> None:
            product_by_id[product.id] = product
            by_name.setdefault(product.name_normalized, []).append(product)
            if product.external_id:
                by_external[product.external_id] = product

        def rename(product: Product, name: str) -> None:
            old_name = product.name_normalized
            bucket = by_name.get(old_name, [])
            if product in bucket:
                bucket.remove(product)
            product.name = name
            product.name_normalized = normalize_product_name(name)
            by_name.setdefault(product.name_normalized, []).append(product)

        def assign_external_id(product: Product, new_id: str) -> str | None:
            if product.external_id == new_id:
                return None
            owner = by_external.get(new_id) or by_alias.get(new_id)
            if owner is not None and owner.id != product.id:
                return f"Ürün ID başka bir üründe kullanılıyor: {new_id}"
            old_id = product.external_id
            if old_id:
                history_ids = {
                    entry.external_id
                    for entry in uow.products.get_external_id_history()
                }
                if old_id not in history_ids:
                    uow.products.add_external_id_history(
                        ProductExternalIdHistory(
                            id=uuid.uuid4(),
                            product_id=product.id,
                            external_id=old_id,
                            created_at=now,
                        )
                    )
                by_alias[old_id] = product
                by_external.pop(old_id, None)
            if new_id in by_alias:
                uow.products.delete_external_id_history(new_id)
                by_alias.pop(new_id, None)
            product.external_id = new_id
            by_external[new_id] = product
            return None

        def add_price_history(
            product: Product,
            field_name: str,
            old_value: Decimal | None,
            new_value: Decimal | None,
        ) -> None:
            uow.products.add_price_history(
                ProductPriceHistory(
                    id=uuid.uuid4(),
                    product_id=product.id,
                    field_name=field_name,
                    old_value=old_value,
                    new_value=new_value,
                    source="scraper_import",
                    changed_at=now,
                    changed_by_name=actor.worker_name,
                    changed_by_device=actor.device_name,
                )
            )

        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0
        details_error_count = 0
        seen_ids: set[str] = set()

        for row in raw_preview.rows:
            if row.errors or not row.product_name:
                error_count += 1
                continue

            chosen_decision = (
                (decisions.get(row.row_number) or decisions.get(str(row.row_number)))
                if decisions
                else row.decision
            ) or row.decision
            if chosen_decision == "skip":
                skipped_count += 1
                continue

            if row.external_id:
                if row.external_id in seen_ids:
                    error_count += 1
                    continue
                seen_ids.add(row.external_id)

            name_norm = normalize_product_name(row.product_name)
            candidates = by_name.get(name_norm, [])
            product: Product | None = None
            from_alias = False
            if row.external_id:
                product = by_external.get(row.external_id)
                if product is None:
                    product = by_alias.get(row.external_id)
                    from_alias = product is not None
                if product is None:
                    if len(candidates) == 1:
                        product = candidates[0]
                    elif len(candidates) > 1:
                        error_count += 1
                        continue
            else:
                if len(candidates) == 1:
                    product = candidates[0]
                elif len(candidates) > 1:
                    error_count += 1
                    continue

            if row.details_error:
                details_error_count += 1
                error_count += 1

            if product is None:
                category = resolve_category(row.category_name)
                scraped_at = (
                    _parse_datetime(row.scraped_at) if row.scraped_at else None
                )
                regular_price = (
                    Decimal(row.regular_price)
                    if row.regular_price
                    else None
                )
                discounted_price = (
                    Decimal(row.website_discounted_price)
                    if row.website_discounted_price
                    else None
                )
                cost_price = (
                    Decimal(row.cost_price) if row.cost_price else None
                )
                qty = int(row.quantity) if row.quantity is not None else 0
                product = Product(
                    id=uuid.uuid4(),
                    external_id=row.external_id,
                    name=row.product_name,
                    name_normalized=name_norm,
                    details=row.details if row.details_present else None,
                    source_url=row.source_url,
                    kind=row.kind or "product",
                    scraped_at=scraped_at,
                    regular_price=regular_price,
                    website_discounted_price=discounted_price,
                    cost_price=cost_price,
                    physical_stock=qty,
                    category_id=category.id if category else None,
                    last_seen_at=now,
                    last_price_changed_at=(
                        now
                        if (
                            regular_price is not None
                            or discounted_price is not None
                            or cost_price is not None
                        )
                        else None
                    ),
                )
                uow.products.add(product)
                remember(product)
                created_count += 1

                for field_name, value in (
                    ("regular_price", regular_price),
                    ("website_discounted_price", discounted_price),
                    ("cost_price", cost_price),
                ):
                    if value is not None:
                        add_price_history(product, field_name, None, value)

                cash_floor = (
                    Decimal(row.cash_floor_price)
                    if row.cash_floor_price
                    else None
                )
                card_floor = (
                    Decimal(row.card_floor_price)
                    if row.card_floor_price
                    else None
                )
                if cash_floor is not None or card_floor is not None:
                    apply_dealer_pricing_values(
                        uow,
                        product_id=product.id,
                        cash_floor_price=cash_floor,
                        card_floor_price=card_floor,
                        note=f"Dosya içe aktarma: {file_name}",
                        actor=actor,
                        now=now,
                    )
                if qty > 0:
                    uow.products.add_stock_movement(
                        StockMovement(
                            id=uuid.uuid4(),
                            product_id=product.id,
                            movement_type="csv_update",
                            quantity_delta=qty,
                            quantity_before=0,
                            quantity_after=qty,
                            note=f"Initial import from {file_name}",
                            idempotency_key=f"import:{batch_id}:{row.row_number}",
                            created_at=now,
                            created_by_name=actor.worker_name,
                            created_by_device=actor.device_name,
                        )
                    )
                continue

            # Existing product: update fields; ID is the primary key.
            product.is_archived = False
            if row.category_name:
                category = resolve_category(row.category_name)
                product.category_id = category.id if category else None

            if row.external_id:
                if from_alias:
                    if product.external_id is None:
                        product.external_id = row.external_id
                        by_external[row.external_id] = product
                else:
                    error = assign_external_id(product, row.external_id)
                    if error is not None:
                        error_count += 1
                        continue

            if product.name != row.product_name:
                rename(product, row.product_name)

            if row.regular_price is not None:
                new_regular = Decimal(row.regular_price)
                if product.regular_price != new_regular:
                    add_price_history(
                        product,
                        "regular_price",
                        product.regular_price,
                        new_regular,
                    )
                    product.regular_price = new_regular
                    product.last_price_changed_at = now

            if (
                chosen_decision == "clear_discount"
                or row.clear_website_discounted_price
            ):
                if product.website_discounted_price is not None:
                    add_price_history(
                        product,
                        "website_discounted_price",
                        product.website_discounted_price,
                        None,
                    )
                    product.website_discounted_price = None
                    product.last_price_changed_at = now
            elif row.website_discounted_price is not None:
                new_discounted = Decimal(row.website_discounted_price)
                if product.website_discounted_price != new_discounted:
                    add_price_history(
                        product,
                        "website_discounted_price",
                        product.website_discounted_price,
                        new_discounted,
                    )
                    product.website_discounted_price = new_discounted
                    product.last_price_changed_at = now

            new_cost = product.cost_price
            if row.clear_cost_price:
                new_cost = None
            elif row.cost_price is not None:
                new_cost = Decimal(row.cost_price)
            if new_cost != product.cost_price:
                add_price_history(
                    product, "cost_price", product.cost_price, new_cost
                )
                product.cost_price = new_cost
                product.last_price_changed_at = now

            current_pricing = uow.dealer_pricing.get(product.id)
            new_cash = (
                current_pricing.cash_floor_price
                if current_pricing is not None
                else None
            )
            new_card = (
                current_pricing.card_floor_price
                if current_pricing is not None
                else None
            )
            floor_touched = False
            if row.clear_cash_floor_price:
                new_cash = None
                floor_touched = True
            elif row.cash_floor_price is not None:
                new_cash = Decimal(row.cash_floor_price)
                floor_touched = True
            if row.clear_card_floor_price:
                new_card = None
                floor_touched = True
            elif row.card_floor_price is not None:
                new_card = Decimal(row.card_floor_price)
                floor_touched = True
            if floor_touched and (
                current_pricing is not None
                or new_cash is not None
                or new_card is not None
            ):
                apply_dealer_pricing_values(
                    uow,
                    product_id=product.id,
                    cash_floor_price=new_cash,
                    card_floor_price=new_card,
                    note=f"Dosya içe aktarma: {file_name}",
                    actor=actor,
                    now=now,
                )

            if row.quantity is not None:
                new_qty = int(row.quantity)
                old_qty = product.physical_stock
                if old_qty != new_qty:
                    delta = new_qty - old_qty
                    product.physical_stock = new_qty
                    uow.products.add_stock_movement(
                        StockMovement(
                            id=uuid.uuid4(),
                            product_id=product.id,
                            movement_type="csv_update",
                            quantity_delta=delta,
                            quantity_before=old_qty,
                            quantity_after=new_qty,
                            note=f"Stock update from {file_name}",
                            idempotency_key=f"import:{batch_id}:{row.row_number}",
                            created_at=now,
                            created_by_name=actor.worker_name,
                            created_by_device=actor.device_name,
                        )
                    )

            if row.details_present and row.details is not None:
                product.details = row.details
            if row.kind_present and row.kind:
                product.kind = row.kind
            if row.source_url:
                product.source_url = row.source_url
            if row.scraped_at:
                parsed = _parse_datetime(row.scraped_at)
                if parsed is not None:
                    product.scraped_at = parsed
            product.last_seen_at = now
            updated_count += 1

        batch = ProductImportBatch(
            id=batch_id,
            file_name=file_name,
            file_type=raw_preview.source_type,
            source_checksum=commit_token or source_checksum,
            status="committed",
            row_count=len(raw_preview.rows),
            created_count=created_count,
            updated_count=updated_count,
            error_count=error_count,
            summary={
                "skipped_count": skipped_count,
                "source_sha256": source_checksum,
                "details_error_count": details_error_count,
                "source_type": raw_preview.source_type,
                "schema_version": raw_preview.schema_version,
            },
            started_at=now,
            completed_at=now,
            created_by_name=actor.worker_name,
            created_by_device=actor.device_name,
        )
        uow.products.create_import_batch(batch)
        uow.commit()

    return ProductImportCommitResult(
        batch_id=batch_id,
        created_count=created_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        error_count=error_count,
        total_count=len(raw_preview.rows),
    )


def _detect_source_type(source: bytes) -> str:
    stripped = source.lstrip()
    if stripped.startswith(b"{"):
        return "json"
    if source.startswith(b"PK"):
        return "xlsx"
    return "csv"


def _source_rows(source: bytes) -> Iterable[dict[str, str | None]]:
    source_type = _detect_source_type(source)
    if source_type == "json":
        yield from _catalog_rows(source)
        return

    if source_type == "xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(source), read_only=True, data_only=True)
        try:
            rows = workbook.active.iter_rows(values_only=True)
            try:
                headers = [str(value or "").strip() for value in next(rows)]
            except StopIteration:
                return
            for values in rows:
                yield dict(
                    zip(
                        headers,
                        (
                            None if value is None else str(value)
                            for value in values
                        ),
                    )
                )
        finally:
            workbook.close()
        return

    text = _decode_source(source)
    reader = csv.DictReader(
        io.StringIO(text),
        delimiter=_detect_delimiter(text),
        restval=None,
    )
    yield from reader


def _catalog_rows(source: bytes) -> Iterable[dict[str, str | None]]:
    try:
        data = json.loads(_decode_source(source), parse_float=Decimal)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportFormatError(
            "catalog.json okunamadı; dosya geçerli JSON değil."
        ) from exc
    if not isinstance(data, dict):
        raise ImportFormatError("catalog.json kökü bir nesne olmalıdır.")
    version = str(data.get("schema_version") or "")
    if version != "1.0":
        raise ImportFormatError(
            f"Desteklenmeyen catalog.json sürümü: {version or 'yok'}."
        )
    products = data.get("products")
    if not isinstance(products, list):
        raise ImportFormatError("catalog.json içinde products listesi bulunamadı.")
    catalog_scraped_at = str(data.get("scraped_at") or "")
    for product in products:
        if not isinstance(product, dict):
            product = {}
        features = product.get("features")
        specifications = product.get("specifications")
        details = {
            "features": features if features is not None else [],
            "specifications": (
                specifications if specifications is not None else []
            ),
        }
        yield {
            "Ürün ID": str(product.get("id") or ""),
            "Ürün Adı": str(product.get("product_name") or ""),
            "Kategori": str(product.get("category") or ""),
            "Perakende Fiyat": _price_text(product.get("price")),
            "Oliz İndirimli Fiyat": _price_text(
                product.get("discounted_price")
            ),
            "Fiziksel Stok": "",
            "Alış Fiyatı": "",
            "Kredi Kartı Taban Fiyatı": "",
            "Nakit Taban Fiyatı": "",
            "Aktif Kampanya": "",
            "Ürün Özellikleri (JSON)": json.dumps(
                details, ensure_ascii=False
            ),
            "kind": str(product.get("kind") or "product"),
            "source_url": str(product.get("source_url") or ""),
            "scraped_at": str(product.get("scraped_at") or ""),
            "currency": str(product.get("currency") or "TRY"),
            "_schema_version": version,
            "_catalog_scraped_at": catalog_scraped_at,
        }


def _price_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _clean_external_id(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    if re.fullmatch(r"\d+\.0", cleaned):
        return cleaned[:-2]
    return cleaned


def _normalize_kind(
    raw_kind: str, category_name: str | None, warnings: list[str]
) -> str:
    if raw_kind:
        if raw_kind in {"product", "warranty", "explicit"}:
            return raw_kind
        warnings.append(f"Geçersiz ürün türü: {raw_kind}")
        return "product"
    if category_name and normalize_category_name(category_name) == "ek garanti":
        return "warranty"
    return "product"


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _decode_source(source: bytes) -> str:
    try:
        return source.decode("utf-8-sig")
    except UnicodeDecodeError:
        return source.decode("cp1254").lstrip("\ufeffï»¿")


def _detect_delimiter(text: str) -> str:
    sample = text.splitlines()[0] if text.splitlines() else ""
    return ";" if sample.count(";") > sample.count(",") else ","


def _has_column(row: dict[str, str | None], *headers: str) -> bool:
    normalized_headers = {normalize_header(header) for header in headers}
    return any(
        key and normalize_header(key) in normalized_headers for key in row
    )


def _value(row: dict[str, str | None], *headers: str) -> str:
    normalized_headers = {normalize_header(header) for header in headers}
    for key, value in row.items():
        if key and normalize_header(key) in normalized_headers:
            return (value or "").strip()
    return ""


def _is_clear(value: str) -> bool:
    cleaned = value.strip().casefold()
    return cleaned in {"-", "temizle", "clear", "yok", "sil"}


def _optional_price(
    value: str, label: str, errors: list[str], *, positive_only: bool = False
) -> tuple[str | None, bool]:
    if not value:
        return None, False
    if _is_clear(value):
        return None, True
    normalized = _normalize_decimal(value)
    if normalized is None:
        errors.append(f"{label} sayısal olmalıdır.")
        return None, False
    if positive_only and Decimal(normalized) <= 0:
        return None, False
    return normalized, False


def _normalize_decimal(value: str) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    cleaned = re.sub(r"(?i)\s*(?:TL|TRY|₺)\s*$", "", cleaned).strip()
    cleaned = cleaned.replace(" ", "")
    if not cleaned:
        return None

    if "." in cleaned and "," in cleaned:
        last_dot = cleaned.rfind(".")
        last_comma = cleaned.rfind(",")
        if last_comma > last_dot:
            candidate = cleaned.replace(".", "").replace(",", ".")
        else:
            candidate = cleaned.replace(",", "")
    elif "." in cleaned:
        parts = cleaned.split(".")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) >= 1):
            candidate = cleaned.replace(".", "")
        else:
            candidate = cleaned
    elif "," in cleaned:
        candidate = cleaned.replace(",", ".")
    else:
        candidate = cleaned

    try:
        number = Decimal(candidate)
    except InvalidOperation:
        return None
    if number < 0:
        return None
    return format(number, "f")


def _normalize_quantity(value: str) -> str | None:
    if not value:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if number < 0 or number != number.to_integral_value():
        return None
    return format(number, "f").split(".")[0]
