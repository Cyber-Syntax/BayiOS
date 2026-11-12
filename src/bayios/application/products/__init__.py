from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from bayios.adapters.db.models.inventory import StockMovement
from bayios.adapters.db.models.products import Product, ProductPriceHistory
from bayios.application.errors import (
    ProductAlreadyExistsError,
    ProductHasOpenReservationsError,
)
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.tabular import (
    ColumnSpec,
    SheetSpec,
    write_csv,
    write_xlsx,
)
from bayios.domain.inventory import StockSummary
from bayios.domain.products import ActorContext, normalize_product_name


@dataclass(frozen=True)
class ProductDetail:
    product: Product
    price_history: Sequence[ProductPriceHistory]
    stock_movements: Sequence[StockMovement]
    open_reservation: int


def get_product(uow: UnitOfWork, product_id: uuid.UUID) -> Product | None:
    with uow:
        return uow.products.get_by_id(product_id)


def search_products(
    uow: UnitOfWork,
    query: str | None = None,
    category_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    include_archived: bool = False,
    only_archived: bool = False,
) -> tuple[Sequence[Product], int]:
    with uow:
        return uow.products.search(
            query=query,
            category_id=category_id,
            limit=limit,
            offset=offset,
            include_archived=include_archived,
            only_archived=only_archived,
        )


def create_manual_product(
    uow: UnitOfWork,
    name: str,
    regular_price: Decimal | None = None,
    website_discounted_price: Decimal | None = None,
    cost_price: Decimal | None = None,
    physical_stock: int = 0,
    category_id: uuid.UUID | None = None,
    actor: ActorContext | None = None,
) -> Product:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Ürün adı boş olamaz.")
    norm_name = normalize_product_name(clean_name)
    now = datetime.now(UTC)
    actor = actor or ActorContext()

    with uow:
        existing = uow.products.get_by_normalized_name(norm_name)
        if existing is not None:
            raise ProductAlreadyExistsError(
                f"'{clean_name}' adında bir ürün zaten mevcut."
            )
        if category_id is not None and uow.products.get_category(category_id) is None:
            raise ValueError("Seçilen kategori bulunamadı.")

        prod_id = uuid.uuid4()
        product = Product(
            id=prod_id,
            name=clean_name,
            name_normalized=norm_name,
            regular_price=regular_price,
            website_discounted_price=website_discounted_price,
            cost_price=cost_price,
            physical_stock=physical_stock,
            category_id=category_id,
            last_seen_at=now,
            last_price_changed_at=now
            if (regular_price is not None or website_discounted_price is not None)
            else None,
        )
        uow.products.add(product)

        if regular_price is not None:
            uow.products.add_price_history(
                ProductPriceHistory(
                    id=uuid.uuid4(),
                    product_id=prod_id,
                    field_name="regular_price",
                    old_value=None,
                    new_value=regular_price,
                    source="manual",
                    changed_at=now,
                    changed_by_name=actor.worker_name,
                    changed_by_device=actor.device_name,
                )
            )
        if website_discounted_price is not None:
            uow.products.add_price_history(
                ProductPriceHistory(
                    id=uuid.uuid4(),
                    product_id=prod_id,
                    field_name="website_discounted_price",
                    old_value=None,
                    new_value=website_discounted_price,
                    source="manual",
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
                    source="manual",
                    changed_at=now,
                    changed_by_name=actor.worker_name,
                    changed_by_device=actor.device_name,
                )
            )
        if physical_stock != 0:
            uow.products.add_stock_movement(
                StockMovement(
                    id=uuid.uuid4(),
                    product_id=prod_id,
                    movement_type="manual_adjustment",
                    quantity_delta=physical_stock,
                    quantity_before=0,
                    quantity_after=physical_stock,
                    note="Manuel ürün ekleme başlangıç stoku",
                    created_at=now,
                    created_by_name=actor.worker_name,
                    created_by_device=actor.device_name,
                )
            )
        uow.commit()
        return product


def update_product(
    uow: UnitOfWork,
    product_id: uuid.UUID,
    name: str,
    regular_price: Decimal | None = None,
    website_discounted_price: Decimal | None = None,
    cost_price: Decimal | None = None,
    category_id: uuid.UUID | None = None,
    actor: ActorContext | None = None,
) -> Product:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Ürün adı boş olamaz.")
    norm_name = normalize_product_name(clean_name)
    now = datetime.now(UTC)
    actor = actor or ActorContext()

    with uow:
        product = uow.products.get_by_id(product_id)
        if product is None:
            raise ValueError("Ürün bulunamadı.")
        if category_id is not None and uow.products.get_category(category_id) is None:
            raise ValueError("Seçilen kategori bulunamadı.")

        if norm_name != product.name_normalized:
            duplicate = uow.products.get_by_normalized_name(norm_name)
            if duplicate is not None and duplicate.id != product.id:
                raise ProductAlreadyExistsError(
                    f"'{clean_name}' adında bir ürün zaten mevcut."
                )
            product.name = clean_name
            product.name_normalized = norm_name

        price_changes = (
            ("regular_price", product.regular_price, regular_price),
            (
                "website_discounted_price",
                product.website_discounted_price,
                website_discounted_price,
            ),
            ("cost_price", product.cost_price, cost_price),
        )
        price_changed = False
        for field_name, old_value, new_value in price_changes:
            if old_value == new_value:
                continue
            uow.products.add_price_history(
                ProductPriceHistory(
                    id=uuid.uuid4(),
                    product_id=product.id,
                    field_name=field_name,
                    old_value=old_value,
                    new_value=new_value,
                    source="manual",
                    changed_at=now,
                    changed_by_name=actor.worker_name,
                    changed_by_device=actor.device_name,
                )
            )
            setattr(product, field_name, new_value)
            price_changed = True

        if price_changed:
            product.last_price_changed_at = now

        product.category_id = category_id

        uow.commit()
        return product


def archive_products(
    uow: UnitOfWork, product_ids: Sequence[uuid.UUID], archive: bool = True
) -> int:
    with uow:
        count = uow.products.set_archived(product_ids, archived=archive)
        uow.commit()
        return count


def delete_products(uow: UnitOfWork, product_ids: Sequence[uuid.UUID]) -> int:
    with uow:
        blocked = uow.reservations.open_product_ids(list(product_ids))
        if blocked:
            raise ProductHasOpenReservationsError(
                f"{len(blocked)} ürün açık rezervasyonda olduğu için silinemez. "
                "Önce ilgili rezervasyon satırlarını teslim edin veya iptal edin."
            )
        count = uow.products.delete_products(product_ids)
        uow.commit()
        return count


def assign_products_category(
    uow: UnitOfWork,
    product_ids: Sequence[uuid.UUID],
    category_id: uuid.UUID | None,
) -> int:
    with uow:
        if category_id is not None and uow.products.get_category(category_id) is None:
            raise ValueError("Seçilen kategori bulunamadı.")
        count = uow.products.set_category(product_ids, category_id)
        uow.commit()
        return count


def adjust_product_stock(
    uow: UnitOfWork,
    product_id: uuid.UUID,
    new_physical_stock: int,
    note: str | None = None,
    actor: ActorContext | None = None,
) -> Product:
    now = datetime.now(UTC)
    actor = actor or ActorContext()

    with uow:
        product = uow.products.get_by_id(product_id)
        if product is None:
            raise ValueError("Ürün bulunamadı.")

        old_stock = product.physical_stock
        delta = new_physical_stock - old_stock
        product.physical_stock = new_physical_stock

        if delta != 0:
            uow.products.add_stock_movement(
                StockMovement(
                    id=uuid.uuid4(),
                    product_id=product.id,
                    movement_type="manual_adjustment",
                    quantity_delta=delta,
                    quantity_before=old_stock,
                    quantity_after=new_physical_stock,
                    note=note or "Manuel stok düzeltmesi",
                    created_at=now,
                    created_by_name=actor.worker_name,
                    created_by_device=actor.device_name,
                )
            )
        uow.commit()
        return product


def get_product_detail(
    uow: UnitOfWork,
    product_id: uuid.UUID,
    open_reservations: dict[uuid.UUID, int] | None = None,
) -> ProductDetail | None:
    with uow:
        product = uow.products.get_by_id(product_id)
        if product is None:
            return None
        price_history = uow.products.get_price_history(product_id)
        stock_movements = uow.products.get_stock_movements(product_id)

        if open_reservations is None:
            open_reservations = dict(
                uow.reservations.open_quantity_by_product([product.id])
            )

        summary = StockSummary(
            physical=product.physical_stock,
            open_reservation=open_reservations.get(product.id, 0),
        )

        return ProductDetail(
            product=product,
            price_history=price_history,
            stock_movements=stock_movements,
            open_reservation=summary.open_reservation,
        )


PRODUCT_EXPORT_HEADERS = (
    "Ürün Adı",
    "Kategori",
    "Perakende Fiyat",
    "Oliz İndirimli Fiyat",
    "Fiziksel Stok",
    "Alış Fiyatı",
    "Kredi Kartı Taban Fiyatı",
    "Nakit Taban Fiyatı",
    "Aktif Kampanya",
)


def export_products_csv(uow: UnitOfWork) -> bytes:
    rows = _product_export_rows(uow)
    return write_csv(
        PRODUCT_EXPORT_HEADERS,
        [
            (
                row["product_name"],
                row["category"],
                row["regular_price"],
                row["website_discounted_price"],
                row["physical_stock"],
                row["cost_price"],
                row["card_floor_price"],
                row["cash_floor_price"],
                row["active_campaigns"],
            )
            for row in rows
        ],
    )


def export_products_xlsx(uow: UnitOfWork) -> bytes:
    rows = _product_export_rows(uow)
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
        rows=rows,
        instructions=(
            ("Ürün Adı", "Zorunlu", "Ürün kimliği; baştaki sıfırlar korunur."),
            ("Kategori", "Opsiyonel", "Boşsa mevcut kategori korunur; yeni ad otomatik oluşturulur."),
            ("Perakende Fiyat", "Opsiyonel", "Boşsa korunur; - yazılırsa temizlenir."),
            ("Oliz İndirimli Fiyat", "Opsiyonel", "Boşsa korunur; - yazılırsa temizlenir."),
            ("Fiziksel Stok", "Opsiyonel", "Boşsa korunur; 0 stoğu sıfırlar."),
            ("Alış Fiyatı", "Opsiyonel", "Maliyet fiyatı; boşsa korunur, - temizler."),
            ("Kredi Kartı Taban Fiyatı", "Opsiyonel", "Boşsa korunur; - temizler."),
            ("Nakit Taban Fiyatı", "Opsiyonel", "Boşsa korunur; - temizler."),
            ("Aktif Kampanya", "Salt okunur", "Sadece bilgi amaçlıdır; içe aktarmada kullanılmaz."),
        ),
    )
    return write_xlsx((sheet,))


def _product_export_rows(uow: UnitOfWork) -> list[dict[str, object]]:
    now = datetime.now(UTC)
    with uow:
        products = uow.products.get_all()
        category_names = {c.id: c.name for c in uow.products.get_categories()}
        pricing = uow.dealer_pricing.get_many([product.id for product in products])
        campaigns, _ = uow.campaigns.list(
            state="active", as_of=now, limit=10_000
        )
        links_by_version = uow.campaigns.get_version_products_for_versions(
            [version.id for _, version in campaigns]
        )
        active_campaigns: dict[uuid.UUID, set[str]] = {}
        for _campaign, version in campaigns:
            if not (version.starts_at <= now <= version.ends_at):
                continue
            for link in links_by_version.get(version.id, ()):
                if link.product_id is not None:
                    active_campaigns.setdefault(link.product_id, set()).add(
                        version.name
                    )

    rows: list[dict[str, object]] = []
    for product in products:
        dealer = pricing.get(product.id)
        rows.append(
            {
                "product_name": product.name,
                "category": category_names.get(product.category_id, ""),
                "regular_price": product.regular_price,
                "website_discounted_price": product.website_discounted_price,
                "physical_stock": product.physical_stock,
                "cost_price": product.cost_price,
                "card_floor_price": (
                    dealer.card_floor_price if dealer is not None else None
                ),
                "cash_floor_price": (
                    dealer.cash_floor_price if dealer is not None else None
                ),
                "active_campaigns": "; ".join(
                    sorted(active_campaigns.get(product.id, set()))
                ),
            }
        )
    return rows
