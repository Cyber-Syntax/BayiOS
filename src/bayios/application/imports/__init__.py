from __future__ import annotations

import csv
import hashlib
import io
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
    ProductImportBatch,
    ProductPriceHistory,
)
from bayios.application.dealer_pricing import apply_dealer_pricing_values
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.tabular import (
    ColumnSpec,
    SheetSpec,
    normalize_header,
    write_xlsx,
)
from bayios.domain.commissions import commission_group_for_category_name
from bayios.domain.products import (
    ActorContext,
    normalize_category_name,
    normalize_product_name,
)


@dataclass(frozen=True)
class ProductImportRow:
    row_number: int
    decision: str
    product_name: str | None = None
    category_name: str | None = None
    regular_price: str | None = None
    website_discounted_price: str | None = None
    quantity: str | None = None
    cost_price: str | None = None
    cash_floor_price: str | None = None
    card_floor_price: str | None = None
    active_campaigns: str | None = None
    clear_cost_price: bool = False
    clear_cash_floor_price: bool = False
    clear_card_floor_price: bool = False
    clear_website_discounted_price: bool = False
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def is_problematic(self) -> bool:
        return bool(self.errors or self.warnings or self.decision == "error")


@dataclass(frozen=True)
class ProductImportPreview:
    rows: tuple[ProductImportRow, ...]


@dataclass(frozen=True)
class ProductImportCommitResult:
    batch_id: uuid.UUID
    created_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    total_count: int


def preview_product_import(
    source: bytes, existing_names: set[str] | None = None
) -> ProductImportPreview:
    rows: list[ProductImportRow] = []

    for row_number, raw_row in enumerate(_source_rows(source), start=2):
        raw_product_name = _value(
            raw_row, "product_name", "product name", "name", "ürün adı", "urun adi"
        )
        product_name = (
            unicodedata.normalize("NFKC", raw_product_name).strip()
            if raw_product_name
            else ""
        )
        regular_price = _value(
            raw_row,
            "regular_price",
            "regular price",
            "perakende fiyat",
            "normal fiyat",
        )
        discounted_price = _value(
            raw_row,
            "website_discounted_price",
            "website discounted price",
            "oliz indirimli fiyat",
            "oliz fiyatı",
            "indirimli fiyat",
        )
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
        if category_name:
            category_name = unicodedata.normalize("NFKC", category_name).strip()
        errors: list[str] = []
        warnings: list[str] = []

        if not product_name:
            errors.append("Ürün adı zorunludur.")
        elif not re.fullmatch(r"[0-9A-Z]+(?: [0-9A-Z]+)*", product_name.upper()):
            warnings.append("Ürün adı biçimi kontrol edilmeli.")
        normalized_price = _normalize_decimal(regular_price)
        if regular_price and normalized_price is None:
            errors.append("Perakende fiyat sayısal olmalıdır.")
        normalized_discounted_price, clear_discounted = _optional_price(
            discounted_price, "Oliz indirimli fiyat", errors
        )
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
        if active_campaigns:
            warnings.append(
                "Aktif Kampanya salt okunurdur; kampanyalar sekmesinden yönetilir."
            )

        if errors:
            decision = "error"
        elif existing_names and normalize_product_name(product_name) in existing_names:
            decision = "update"
        else:
            decision = "create"

        rows.append(
            ProductImportRow(
                row_number=row_number,
                decision=decision,
                product_name=product_name or None,
                category_name=category_name or None,
                regular_price=normalized_price,
                website_discounted_price=normalized_discounted_price,
                quantity=normalized_quantity,
                cost_price=normalized_cost,
                cash_floor_price=normalized_cash,
                card_floor_price=normalized_card,
                active_campaigns=active_campaigns or None,
                clear_cost_price=clear_cost,
                clear_cash_floor_price=clear_cash,
                clear_card_floor_price=clear_card,
                clear_website_discounted_price=clear_discounted,
                errors=tuple(errors),
                warnings=tuple(warnings),
            )
        )

    rows.sort(key=lambda r: (0 if r.is_problematic else 1, r.row_number))
    return ProductImportPreview(rows=tuple(rows))


def product_import_template() -> bytes:
    sheet = SheetSpec(
        title="Ürünler",
        columns=(
            ColumnSpec("Ürün Adı", "product_name", "text", 32),
            ColumnSpec("Kategori", "category", "text", 22),
            ColumnSpec("Perakende Fiyat", "regular_price", "money", 16),
            ColumnSpec("Oliz İndirimli Fiyat", "website_discounted_price", "money", 18),
            ColumnSpec("Fiziksel Stok", "physical_stock", "int", 14),
            ColumnSpec("Alış Fiyatı", "cost_price", "money", 14),
            ColumnSpec("Kredi Kartı Taban Fiyatı", "card_floor_price", "money", 22),
            ColumnSpec("Nakit Taban Fiyatı", "cash_floor_price", "money", 20),
            ColumnSpec("Aktif Kampanya", "active_campaigns", "text", 34),
        ),
        rows=(),
        instructions=(
            ("Ürün Adı", "Zorunlu", "Ürün kimliği; baştaki sıfırlar korunur."),
            ("Kategori", "Opsiyonel", "Boşsa mevcut kategori korunur; yeni ad otomatik oluşturulur."),
            ("Perakende Fiyat", "Opsiyonel", "Boşsa korunur; - yazılırsa temizlenir."),
            ("Oliz İndirimli Fiyat", "Opsiyonel", "Boşsa korunur; - yazılırsa temizlenir."),
            ("Fiziksel Stok", "Opsiyonel", "Boşsa korunur; 0 stoğu sıfırlar."),
            ("Alış Fiyatı", "Opsiyonel", "Maliyet fiyatı; boşsa korunur, - temizler."),
            ("Kredi Kartı Taban Fiyatı", "Opsiyonel", "Boşsa korunur; - temizler."),
            ("Nakit Taban Fiyatı", "Opsiyonel", "Boşsa korunur; - temizler."),
            ("Aktif Kampanya", "Salt okunur", "İçe aktarmada kullanılmaz."),
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

        # First fetch existing products for matching by reading names
        raw_rows = list(_source_rows(source))
        raw_names = [
            _value(r, "product_name", "product name", "name", "ürün adı", "urun adi")
            for r in raw_rows
        ]
        normalized_names = [
            normalize_product_name(unicodedata.normalize("NFKC", n).strip())
            for n in raw_names
            if n
        ]
        existing_products = uow.products.get_by_normalized_names(normalized_names)
        existing_names = set(existing_products.keys())

        categories = {c.name: c for c in uow.products.get_categories()}
        categories_by_norm = {
            normalize_category_name(name): category for name, category in categories.items()
        }

        def resolve_category(category_name: str | None) -> ProductCategory | None:
            if not category_name:
                return None
            norm = normalize_category_name(category_name)
            existing_category = categories_by_norm.get(norm)
            if existing_category is not None:
                return existing_category
            category = ProductCategory(
                id=uuid.uuid4(),
                name=category_name.strip(),
                commission_group=commission_group_for_category_name(
                    category_name
                ).value,
            )
            uow.products.add_category(category)
            categories[category.name] = category
            categories_by_norm[norm] = category
            return category

        raw_preview = preview_product_import(source, existing_names=existing_names)

        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0

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

            norm_name = normalize_product_name(row.product_name)
            existing = existing_products.get(norm_name)

            if existing is None:
                reg_price = Decimal(row.regular_price) if row.regular_price else None
                disc_price = (
                    Decimal(row.website_discounted_price)
                    if row.website_discounted_price
                    else None
                )
                cost_price = Decimal(row.cost_price) if row.cost_price else None
                cash_floor = (
                    Decimal(row.cash_floor_price) if row.cash_floor_price else None
                )
                card_floor = (
                    Decimal(row.card_floor_price) if row.card_floor_price else None
                )
                qty = int(row.quantity) if row.quantity is not None else 0

                prod_id = uuid.uuid4()
                category = resolve_category(row.category_name)
                product = Product(
                    id=prod_id,
                    name=row.product_name,
                    name_normalized=norm_name,
                    regular_price=reg_price,
                    website_discounted_price=disc_price,
                    cost_price=cost_price,
                    physical_stock=qty,
                    category_id=category.id if category else None,
                    last_seen_at=now,
                    last_price_changed_at=(
                        now
                        if (reg_price or disc_price or cost_price)
                        else None
                    ),
                )
                uow.products.add(product)
                existing_products[norm_name] = product
                created_count += 1

                if reg_price is not None:
                    uow.products.add_price_history(
                        ProductPriceHistory(
                            id=uuid.uuid4(),
                            product_id=prod_id,
                            field_name="regular_price",
                            old_value=None,
                            new_value=reg_price,
                            source="csv_import",
                            changed_at=now,
                            changed_by_name=actor.worker_name,
                            changed_by_device=actor.device_name,
                        )
                    )
                if disc_price is not None:
                    uow.products.add_price_history(
                        ProductPriceHistory(
                            id=uuid.uuid4(),
                            product_id=prod_id,
                            field_name="website_discounted_price",
                            old_value=None,
                            new_value=disc_price,
                            source="csv_import",
                            changed_at=now,
                            changed_by_name=actor.worker_name,
                            changed_by_device=actor.device_name,
                        )
                    )
                if cost_price is not None:
                    uow.products.add_price_history(
                        ProductPriceHistory(
                            id=uuid.uuid4(),
                            product_id=prod_id,
                            field_name="cost_price",
                            old_value=None,
                            new_value=cost_price,
                            source="csv_import",
                            changed_at=now,
                            changed_by_name=actor.worker_name,
                            changed_by_device=actor.device_name,
                        )
                    )
                if cash_floor is not None or card_floor is not None:
                    apply_dealer_pricing_values(
                        uow,
                        product_id=prod_id,
                        cash_floor_price=cash_floor,
                        card_floor_price=card_floor,
                        note=f"Excel içe aktarma: {file_name}",
                        actor=actor,
                        now=now,
                    )
                if qty > 0:
                    uow.products.add_stock_movement(
                        StockMovement(
                            id=uuid.uuid4(),
                            product_id=prod_id,
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
            else:
                # A product present in the current catalog file is active again.
                existing.is_archived = False

                if row.category_name:
                    category = resolve_category(row.category_name)
                    existing.category_id = category.id if category else None

                if row.regular_price is not None:
                    new_reg = Decimal(row.regular_price)
                    if existing.regular_price != new_reg:
                        uow.products.add_price_history(
                            ProductPriceHistory(
                                id=uuid.uuid4(),
                                product_id=existing.id,
                                field_name="regular_price",
                                old_value=existing.regular_price,
                                new_value=new_reg,
                                source="csv_import",
                                changed_at=now,
                                changed_by_name=actor.worker_name,
                                changed_by_device=actor.device_name,
                            )
                        )
                        existing.regular_price = new_reg
                        existing.last_price_changed_at = now

                if (
                    chosen_decision == "clear_discount"
                    or row.clear_website_discounted_price
                ):
                    if existing.website_discounted_price is not None:
                        uow.products.add_price_history(
                            ProductPriceHistory(
                                id=uuid.uuid4(),
                                product_id=existing.id,
                                field_name="website_discounted_price",
                                old_value=existing.website_discounted_price,
                                new_value=None,
                                source="csv_import",
                                changed_at=now,
                                changed_by_name=actor.worker_name,
                                changed_by_device=actor.device_name,
                            )
                        )
                        existing.website_discounted_price = None
                        existing.last_price_changed_at = now
                elif row.website_discounted_price is not None:
                    new_disc = Decimal(row.website_discounted_price)
                    if existing.website_discounted_price != new_disc:
                        uow.products.add_price_history(
                            ProductPriceHistory(
                                id=uuid.uuid4(),
                                product_id=existing.id,
                                field_name="website_discounted_price",
                                old_value=existing.website_discounted_price,
                                new_value=new_disc,
                                source="csv_import",
                                changed_at=now,
                                changed_by_name=actor.worker_name,
                                changed_by_device=actor.device_name,
                            )
                        )
                        existing.website_discounted_price = new_disc
                        existing.last_price_changed_at = now

                new_cost: Decimal | None = existing.cost_price
                if row.clear_cost_price:
                    new_cost = None
                elif row.cost_price is not None:
                    new_cost = Decimal(row.cost_price)
                if new_cost != existing.cost_price:
                    uow.products.add_price_history(
                        ProductPriceHistory(
                            id=uuid.uuid4(),
                            product_id=existing.id,
                            field_name="cost_price",
                            old_value=existing.cost_price,
                            new_value=new_cost,
                            source="csv_import",
                            changed_at=now,
                            changed_by_name=actor.worker_name,
                            changed_by_device=actor.device_name,
                        )
                    )
                    existing.cost_price = new_cost
                    existing.last_price_changed_at = now

                current_pricing = uow.dealer_pricing.get(existing.id)
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
                        product_id=existing.id,
                        cash_floor_price=new_cash,
                        card_floor_price=new_card,
                        note=f"Excel içe aktarma: {file_name}",
                        actor=actor,
                        now=now,
                    )

                new_cost: Decimal | None = existing.cost_price
                if row.clear_cost_price:
                    new_cost = None
                elif row.cost_price is not None:
                    new_cost = Decimal(row.cost_price)
                if new_cost != existing.cost_price:
                    uow.products.add_price_history(
                        ProductPriceHistory(
                            id=uuid.uuid4(),
                            product_id=existing.id,
                            field_name="cost_price",
                            old_value=existing.cost_price,
                            new_value=new_cost,
                            source="csv_import",
                            changed_at=now,
                            changed_by_name=actor.worker_name,
                            changed_by_device=actor.device_name,
                        )
                    )
                    existing.cost_price = new_cost
                    existing.last_price_changed_at = now

                current_pricing = uow.dealer_pricing.get(existing.id)
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
                        product_id=existing.id,
                        cash_floor_price=new_cash,
                        card_floor_price=new_card,
                        note=f"Excel içe aktarma: {file_name}",
                        actor=actor,
                        now=now,
                    )

                if row.quantity is not None:
                    new_qty = int(row.quantity)
                    old_qty = existing.physical_stock
                    if old_qty != new_qty:
                        delta = new_qty - old_qty
                        existing.physical_stock = new_qty
                        uow.products.add_stock_movement(
                            StockMovement(
                                id=uuid.uuid4(),
                                product_id=existing.id,
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

                existing.last_seen_at = now
                updated_count += 1

        batch = ProductImportBatch(
            id=batch_id,
            file_name=file_name,
            file_type=file_type,
            source_checksum=commit_token or source_checksum,
            status="committed",
            row_count=len(raw_preview.rows),
            created_count=created_count,
            updated_count=updated_count,
            error_count=error_count,
            summary={"skipped_count": skipped_count, "source_sha256": source_checksum},
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


def _source_rows(source: bytes) -> Iterable[dict[str, str | None]]:
    if source.startswith(b"PK"):
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(source), read_only=True, data_only=True)
        try:
            rows = workbook.active.iter_rows(values_only=True)
            headers = [str(value or "").strip() for value in next(rows)]
            for values in rows:
                yield dict(zip(headers, (None if value is None else str(value) for value in values)))
        finally:
            workbook.close()
        return

    text = _decode_source(source)
    reader = csv.DictReader(io.StringIO(text), delimiter=_detect_delimiter(text), restval=None)
    yield from reader


def _decode_source(source: bytes) -> str:
    try:
        return source.decode("utf-8-sig")
    except UnicodeDecodeError:
        return source.decode("cp1254").lstrip("\ufeffï»¿")


def _detect_delimiter(text: str) -> str:
    sample = text.splitlines()[0] if text.splitlines() else ""
    return ";" if sample.count(";") > sample.count(",") else ","


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
    value: str, label: str, errors: list[str]
) -> tuple[str | None, bool]:
    if not value:
        return None, False
    if _is_clear(value):
        return None, True
    normalized = _normalize_decimal(value)
    if normalized is None:
        errors.append(f"{label} sayısal olmalıdır.")
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
