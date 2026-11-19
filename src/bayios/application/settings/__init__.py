from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from bayios.adapters.db.models.commissions import Bank
from bayios.adapters.db.models.products import ProductCategory
from bayios.application.errors import NotFoundError, ValidationError
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.domain.commissions import commission_group_for_category_name
from bayios.domain.naming import canonical_display_name, normalize_name

MAX_BULK_LINES = 500


@dataclass(frozen=True)
class BankOverview:
    bank: Bank
    rate_count: int
    limit_count: int
    offer_count: int


@dataclass(frozen=True)
class CategoryOverview:
    category: ProductCategory
    product_count: int
    limit_count: int


@dataclass(frozen=True)
class BulkItem:
    raw: str
    canonical: str
    normalized: str
    status: str
    message: str = ""


@dataclass(frozen=True)
class BulkPreview:
    kind: str
    items: tuple[BulkItem, ...]
    new_count: int
    existing_count: int
    error_count: int


@dataclass(frozen=True)
class BulkResult:
    created: int
    skipped: int


@dataclass(frozen=True)
class MasterImportResult:
    created: int
    updated: int
    skipped: int


def list_bank_overviews(
    uow: UnitOfWork, query: str | None = None
) -> Sequence[BankOverview]:
    with uow:
        banks = uow.commissions.get_banks(active_only=False)
        usage = uow.commissions.bank_usage_counts()
        rows: list[BankOverview] = []
        for bank in banks:
            if query and normalize_name(query) not in bank.name_normalized:
                continue
            rate_count, limit_count = usage.get(bank.id, (0, 0))
            rows.append(
                BankOverview(
                    bank=bank,
                    rate_count=rate_count,
                    limit_count=limit_count,
                    offer_count=uow.offers.count_by_bank(bank.id),
                )
            )
        return rows


def list_category_overviews(
    uow: UnitOfWork, query: str | None = None
) -> Sequence[CategoryOverview]:
    with uow:
        categories = uow.products.get_categories()
        product_counts = uow.products.category_usage_counts()
        limit_counts = uow.commissions.category_limit_counts()
        rows: list[CategoryOverview] = []
        for category in categories:
            if query and normalize_name(query) not in category.name_normalized:
                continue
            rows.append(
                CategoryOverview(
                    category=category,
                    product_count=product_counts.get(category.id, 0),
                    limit_count=limit_counts.get(category.id, 0),
                )
            )
        return rows


def _split_lines(raw_text: str) -> list[str]:
    lines = [line.strip() for line in raw_text.splitlines()]
    names = [line for line in lines if line]
    if not names:
        raise ValidationError("En az bir ad girilmelidir.")
    if len(names) > MAX_BULK_LINES:
        raise ValidationError(
            f"Tek seferde en fazla {MAX_BULK_LINES} satır eklenebilir."
        )
    return names


def _bulk_preview(
    names: Sequence[str],
    existing: dict[str, object],
    *,
    kind: str,
) -> BulkPreview:
    items: list[BulkItem] = []
    seen: set[str] = set()
    new_count = existing_count = error_count = 0
    for raw in names:
        canonical = canonical_display_name(
            raw, always_title=kind == "banks"
        )
        normalized = normalize_name(canonical)
        if not normalized:
            status, message = "error", "Ad boş olamaz."
        elif normalized in seen:
            status, message = "error", "Aynı ad dosyada birden fazla kez var."
        elif normalized in existing:
            status, message = "existing", "Zaten kayıtlı; atlanacak."
        else:
            status, message = "new", ""
        seen.add(normalized)
        if status == "new":
            new_count += 1
        elif status == "existing":
            existing_count += 1
        else:
            error_count += 1
        items.append(
            BulkItem(
                raw=raw,
                canonical=canonical,
                normalized=normalized,
                status=status,
                message=message,
            )
        )
    return BulkPreview(
        kind=kind,
        items=tuple(items),
        new_count=new_count,
        existing_count=existing_count,
        error_count=error_count,
    )


def preview_banks(uow: UnitOfWork, raw_text: str) -> BulkPreview:
    with uow:
        existing = {
            bank.name_normalized: bank
            for bank in uow.commissions.get_banks(active_only=False)
        }
    return _bulk_preview(_split_lines(raw_text), existing, kind="banks")


def preview_categories(uow: UnitOfWork, raw_text: str) -> BulkPreview:
    with uow:
        existing = {
            category.name_normalized: category
            for category in uow.products.get_categories()
        }
    return _bulk_preview(_split_lines(raw_text), existing, kind="categories")


def create_banks_bulk(uow: UnitOfWork, raw_text: str) -> BulkResult:
    preview = preview_banks(uow, raw_text)
    if preview.error_count:
        first = next(item for item in preview.items if item.status == "error")
        raise ValidationError(f"{first.raw}: {first.message}")
    created = 0
    with uow:
        for item in preview.items:
            if item.status != "new":
                continue
            uow.commissions.add_bank(
                Bank(
                    id=uuid.uuid4(),
                    name=item.canonical,
                    name_normalized=item.normalized,
                    is_active=True,
                )
            )
            created += 1
        try:
            uow.commit()
        except IntegrityError as exc:
            raise ValidationError(
                "Aynı adlı banka bu sırada eklendi; listeyi yenileyin."
            ) from exc
    return BulkResult(created=created, skipped=preview.existing_count)


def create_categories_bulk(uow: UnitOfWork, raw_text: str) -> BulkResult:
    preview = preview_categories(uow, raw_text)
    if preview.error_count:
        first = next(item for item in preview.items if item.status == "error")
        raise ValidationError(f"{first.raw}: {first.message}")
    created = 0
    with uow:
        for item in preview.items:
            if item.status != "new":
                continue
            uow.products.add_category(
                ProductCategory(
                    id=uuid.uuid4(),
                    name=item.canonical,
                    name_normalized=item.normalized,
                    commission_group=commission_group_for_category_name(
                        item.canonical
                    ).value,
                )
            )
            created += 1
        try:
            uow.commit()
        except IntegrityError as exc:
            raise ValidationError(
                "Aynı adlı kategori bu sırada eklendi; listeyi yenileyin."
            ) from exc
    return BulkResult(created=created, skipped=preview.existing_count)


def rename_bank(uow: UnitOfWork, bank_id: uuid.UUID, raw_name: str) -> Bank:
    canonical = canonical_display_name(raw_name, always_title=True)
    normalized = normalize_name(canonical)
    if not normalized:
        raise ValidationError("Banka adı boş olamaz.")
    with uow:
        bank = uow.commissions.get_bank(bank_id)
        if bank is None:
            raise NotFoundError("Banka bulunamadı.")
        existing = uow.commissions.get_bank_by_normalized(normalized)
        if existing is not None and existing.id != bank_id:
            raise ValidationError(
                f"'{canonical}' adında bir banka zaten mevcut."
            )
        bank.name = canonical
        bank.name_normalized = normalized
        uow.commit()
        return bank


def set_bank_active(
    uow: UnitOfWork, bank_id: uuid.UUID, active: bool
) -> Bank:
    with uow:
        bank = uow.commissions.get_bank(bank_id)
        if bank is None:
            raise NotFoundError("Banka bulunamadı.")
        bank.is_active = active
        uow.commit()
        return bank


def merge_banks(
    uow: UnitOfWork, source_id: uuid.UUID, target_id: uuid.UUID
) -> None:
    if source_id == target_id:
        raise ValidationError("Banka kendisiyle birleştirilemez.")
    with uow:
        source = uow.commissions.get_bank(source_id)
        target = uow.commissions.get_bank(target_id)
        if source is None or target is None:
            raise NotFoundError("Birleştirilecek banka bulunamadı.")
        uow.commissions.merge_bank_rates_limits(source_id, target_id)
        uow.commissions.repoint_offers_bank(source_id, target_id)
        uow.commissions.delete_bank(source_id)
        uow.commit()


def delete_bank(
    uow: UnitOfWork,
    bank_id: uuid.UUID,
    *,
    confirm: bool,
    force: bool = False,
) -> None:
    with uow:
        bank = uow.commissions.get_bank(bank_id)
        if bank is None:
            raise NotFoundError("Banka bulunamadı.")
        if not confirm:
            raise ValidationError("Silme için ikinci onay gerekli.")
        rate_count, limit_count = uow.commissions.bank_usage_counts().get(
            bank_id, (0, 0)
        )
        offer_count = uow.offers.count_by_bank(bank_id)
        if offer_count:
            raise ValidationError(
                "Bu banka tekliflerde kullanılıyor; silinemez. "
                "Pasifleştirin veya başka bankayla birleştirin."
            )
        if (rate_count or limit_count) and not force:
            raise ValidationError(
                f"Bu banka {rate_count} oran ve {limit_count} limitte "
                "kullanılıyor. Bağlı kayıtlarla birlikte silmek için "
                "silme onayını verin."
            )
        if force and (rate_count or limit_count):
            uow.commissions.delete_bank_rates_limits(bank_id)
        uow.commissions.delete_bank(bank_id)
        uow.commit()


def rename_category(
    uow: UnitOfWork, category_id: uuid.UUID, raw_name: str
) -> ProductCategory:
    canonical = canonical_display_name(raw_name)
    normalized = normalize_name(canonical)
    if not normalized:
        raise ValidationError("Kategori adı boş olamaz.")
    with uow:
        category = uow.products.get_category(category_id)
        if category is None:
            raise NotFoundError("Kategori bulunamadı.")
        existing = uow.products.get_category_by_normalized(normalized)
        if existing is not None and existing.id != category_id:
            raise ValidationError(
                f"'{canonical}' adında bir kategori zaten mevcut."
            )
        category.name = canonical
        category.name_normalized = normalized
        uow.commit()
        return category


def update_category_group(
    uow: UnitOfWork, category_id: uuid.UUID, commission_group: str
) -> None:
    if commission_group not in {"klima", "other"}:
        raise ValidationError("Geçersiz komisyon grubu.")
    with uow:
        category = uow.products.get_category(category_id)
        if category is None:
            raise NotFoundError("Kategori bulunamadı.")
        category.commission_group = commission_group
        uow.commit()


def merge_categories(
    uow: UnitOfWork, source_id: uuid.UUID, target_id: uuid.UUID
) -> None:
    if source_id == target_id:
        raise ValidationError("Kategori kendisiyle birleştirilemez.")
    with uow:
        source = uow.products.get_category(source_id)
        target = uow.products.get_category(target_id)
        if source is None or target is None:
            raise NotFoundError("Birleştirilecek kategori bulunamadı.")
        uow.products.reassign_category(source_id, target_id)
        uow.commissions.merge_category_limits(source_id, target_id)
        uow.products.delete_category(source_id)
        uow.commit()


def delete_category(
    uow: UnitOfWork, category_id: uuid.UUID, *, confirm: bool
) -> None:
    with uow:
        category = uow.products.get_category(category_id)
        if category is None:
            raise NotFoundError("Kategori bulunamadı.")
        if not confirm:
            raise ValidationError("Silme için ikinci onay gerekli.")
        product_count = uow.products.category_usage_counts().get(category_id, 0)
        limit_count = uow.commissions.category_limit_counts().get(category_id, 0)
        if product_count or limit_count:
            raise ValidationError(
                "Bu kategori ürünlerde veya taksit limitlerinde kullanılıyor; "
                "silmek yerine başka kategoriyle birleştirin."
            )
        uow.products.delete_category(category_id)
        uow.commit()
