from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from bayios.adapters.db.models.inventory import (
    StockCountItem,
    StockCountSession,
    StockMovement,
)
from bayios.adapters.db.models.products import Product, ProductCategory
from bayios.application.errors import ConflictError, NotFoundError, ValidationError
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.domain.inventory import CountSession, StockSummary, complete_count_session
from bayios.domain.products import ActorContext


@dataclass(frozen=True)
class StockOverviewRow:
    product: Product
    summary: StockSummary


@dataclass(frozen=True)
class CountSessionLine:
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    system_quantity: int
    counted_quantity: int | None
    difference: int | None
    applied_at: datetime | None


@dataclass(frozen=True)
class StockCountView:
    id: uuid.UUID
    count_number: int | None
    category_id: uuid.UUID | None
    category_name: str | None
    status: str
    stock_version: int
    note: str | None
    started_at: datetime
    completed_at: datetime | None
    completed_by_name: str | None
    items: tuple[CountSessionLine, ...]
    summary: Mapping[str, object] | None

    @property
    def counted_lines(self) -> int:
        return sum(1 for item in self.items if item.counted_quantity is not None)

    @property
    def difference_lines(self) -> int:
        return sum(1 for item in self.items if item.difference not in (None, 0))

    @property
    def total_difference(self) -> int:
        return sum(item.difference or 0 for item in self.items)


@dataclass(frozen=True)
class StockCountCompletion:
    session_id: uuid.UUID
    adjusted_count: int
    unchanged_count: int
    total_difference: int


def get_stock_overview(
    uow: UnitOfWork,
    category_id: uuid.UUID | None = None,
    query: str | None = None,
    open_reservations: Mapping[uuid.UUID, int] | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[tuple[StockOverviewRow, ...], int]:
    reservations = open_reservations
    with uow:
        products, total = uow.products.search_by_category(
            category_id=category_id,
            query=query,
            limit=limit or 10_000,
            offset=offset,
        )
        if reservations is None:
            reservations = uow.reservations.open_quantity_by_product(
                [product.id for product in products]
            )
        return (
            tuple(
                StockOverviewRow(
                    product=product,
                    summary=StockSummary(
                        physical=product.physical_stock,
                        open_reservation=reservations.get(product.id, 0),
                    ),
                )
                for product in products
            ),
            total,
        )


def list_categories(uow: UnitOfWork) -> Sequence[ProductCategory]:
    with uow:
        return uow.products.get_categories()


def create_product_category(uow: UnitOfWork, name: str) -> ProductCategory:
    clean_name = name.strip()
    if not clean_name:
        raise ValidationError("Kategori adı boş olamaz.")
    with uow:
        if uow.products.get_category_by_name(clean_name) is not None:
            raise ValidationError(f"'{clean_name}' adında bir kategori zaten mevcut.")
        category = ProductCategory(id=uuid.uuid4(), name=clean_name)
        uow.products.add_category(category)
        uow.commit()
        return category


def open_stock_count_session(
    uow: UnitOfWork,
    category_id: uuid.UUID | None,
    actor: ActorContext | None = None,
    note: str | None = None,
) -> StockCountView:
    actor = actor or ActorContext()
    now = datetime.now(UTC)
    with uow:
        category = None
        if category_id is not None:
            category = uow.products.get_category(category_id)
            if category is None:
                raise NotFoundError("Kategori bulunamadı.")
        products = list(uow.products.list_by_category(category_id))
        if not products:
            raise ValidationError("Bu kategoride sayılacak aktif ürün bulunmuyor.")

        session = StockCountSession(
            id=uuid.uuid4(),
            category_id=category_id,
            status="open",
            stock_version=uow.stock_counts.stock_version(category_id),
            note=note,
            started_at=now,
            created_by_name=actor.worker_name,
            created_by_device=actor.device_name,
        )
        uow.stock_counts.add_session(session)
        items = [
            StockCountItem(
                id=uuid.uuid4(),
                session_id=session.id,
                product_id=product.id,
                product_name=product.name,
                system_quantity=product.physical_stock,
            )
            for product in products
        ]
        uow.stock_counts.add_items(items)
        uow.commit()
        return _to_view(session, items, category.name if category else None)


def get_stock_count_session(
    uow: UnitOfWork, session_id: uuid.UUID
) -> StockCountView | None:
    with uow:
        session = uow.stock_counts.get_session(session_id)
        if session is None:
            return None
        items = uow.stock_counts.get_items(session_id)
        category = (
            uow.products.get_category(session.category_id)
            if session.category_id is not None
            else None
        )
        return _to_view(session, items, category.name if category else None)


def list_recent_stock_count_sessions(
    uow: UnitOfWork, limit: int = 20
) -> tuple[StockCountSession, ...]:
    with uow:
        return tuple(uow.stock_counts.list_sessions(limit=limit))


def save_counted_quantities(
    uow: UnitOfWork,
    session_id: uuid.UUID,
    counted: Mapping[uuid.UUID, int | None],
) -> StockCountView:
    with uow:
        session = uow.stock_counts.get_session(session_id)
        if session is None:
            raise NotFoundError("Sayım oturumu bulunamadı.")
        if session.status in ("completed", "cancelled"):
            raise ValidationError("Tamamlanmış sayım oturumu değiştirilemez.")

        items = list(uow.stock_counts.get_items(session_id))
        for item in items:
            if item.product_id not in counted:
                continue
            quantity = counted[item.product_id]
            if quantity is not None and quantity < 0:
                raise ValidationError("Sayılan miktar negatif olamaz.")
            item.counted_quantity = quantity
            item.difference = (
                None if quantity is None else quantity - item.system_quantity
            )

        session.status = (
            "review"
            if items and all(item.counted_quantity is not None for item in items)
            else "open"
        )
        uow.commit()
        return _to_view(session, items, _category_name(uow, session))


def refresh_stock_count_session(
    uow: UnitOfWork,
    session_id: uuid.UUID,
) -> StockCountView:
    with uow:
        session = uow.stock_counts.get_session(session_id)
        if session is None:
            raise NotFoundError("Sayım oturumu bulunamadı.")
        if session.status in ("completed", "cancelled"):
            raise ValidationError("Tamamlanmış sayım oturumu yenilenemez.")

        items = list(uow.stock_counts.get_items(session_id))
        current_products = {
            product.id: product
            for product in uow.products.list_by_category(session.category_id)
        }
        remaining_items: list[StockCountItem] = []
        existing_product_ids: set[uuid.UUID] = set()
        for item in items:
            product = current_products.get(item.product_id)
            if product is None:
                uow.stock_counts.delete_item(item)
                continue
            existing_product_ids.add(product.id)
            item.system_quantity = product.physical_stock
            item.difference = (
                None
                if item.counted_quantity is None
                else item.counted_quantity - item.system_quantity
            )
            remaining_items.append(item)

        new_items = [
            StockCountItem(
                id=uuid.uuid4(),
                session_id=session.id,
                product_id=product.id,
                product_name=product.name,
                system_quantity=product.physical_stock,
            )
            for product in current_products.values()
            if product.id not in existing_product_ids
        ]
        if new_items:
            uow.stock_counts.add_items(new_items)
            remaining_items.extend(new_items)

        session.stock_version = uow.stock_counts.stock_version(session.category_id)
        session.status = (
            "review"
            if remaining_items
            and all(item.counted_quantity is not None for item in remaining_items)
            else "open"
        )
        uow.commit()
        return _to_view(session, remaining_items, _category_name(uow, session))


def complete_stock_count_session(
    uow: UnitOfWork,
    session_id: uuid.UUID,
    actor: ActorContext | None = None,
    *,
    acknowledge_differences: bool = False,
) -> StockCountCompletion:
    actor = actor or ActorContext()
    now = datetime.now(UTC)
    with uow:
        session = uow.stock_counts.get_session(session_id)
        if session is None:
            raise NotFoundError("Sayım oturumu bulunamadı.")
        if session.status == "completed":
            summary = session.summary or {}
            return StockCountCompletion(
                session_id=session.id,
                adjusted_count=int(summary.get("adjusted_count", 0)),
                unchanged_count=int(summary.get("unchanged_count", 0)),
                total_difference=int(summary.get("total_difference", 0)),
            )
        if session.status != "review":
            raise ValidationError(
                "Sayımı tamamlamadan önce tüm miktarları girip farkları inceleyin."
            )

        items = list(uow.stock_counts.get_items(session_id))
        if not items:
            raise ValidationError("Sayım oturumunda ürün bulunmuyor.")
        if any(item.counted_quantity is None for item in items):
            raise ValidationError("Tüm ürünlerin sayılan miktarı girilmelidir.")

        product_ids = [item.product_id for item in items]
        products = {product.id: product for product in uow.products.get_by_ids(product_ids)}
        if len(products) != len(product_ids):
            raise ConflictError(
                "Sayımdaki bazı ürünler artık mevcut değil. Sayımı yenileyin."
            )

        snapshots = {str(item.product_id): item.system_quantity for item in items}
        counted = {str(item.product_id): int(item.counted_quantity or 0) for item in items}
        current = {
            str(item.product_id): products[item.product_id].physical_stock
            for item in items
        }
        current_version = uow.stock_counts.stock_version(session.category_id)
        domain_session = CountSession(
            category_id=str(session.category_id or "all"),
            snapshots=snapshots,
            stock_version=session.stock_version,
            opened_at=session.started_at,
        )
        try:
            completion = complete_count_session(
                domain_session,
                counted_quantities=counted,
                current_quantities=current,
                current_version=current_version,
                actor_name=actor.worker_name,
                acknowledge_differences=acknowledge_differences,
                completed_at=now,
            )
        except ValueError as exc:
            if "güncel değil" in str(exc):
                raise ConflictError(
                    "Sayım açıldıktan sonra stok değişti. Farkları yenileyip tekrar inceleyin."
                ) from exc
            raise ValidationError(str(exc)) from exc

        adjusted_count = 0
        total_difference = 0
        for movement in completion.movements:
            product_id = uuid.UUID(movement.product_id)
            product = products[product_id]
            product.physical_stock = movement.quantity_after
            total_difference += movement.quantity_delta
            adjusted_count += 1
            uow.products.add_stock_movement(
                StockMovement(
                    id=uuid.uuid4(),
                    product_id=product_id,
                    movement_type="stock_count_adjustment",
                    quantity_delta=movement.quantity_delta,
                    quantity_before=movement.quantity_before,
                    quantity_after=movement.quantity_after,
                    reference_type="stock_count_session",
                    reference_id=session.id,
                    note=session.note or f"Sayım düzeltmesi #{session.count_number}",
                    idempotency_key=f"stock_count:{session.id}:{product_id}",
                    created_at=now,
                    created_by_name=actor.worker_name,
                    created_by_device=actor.device_name,
                )
            )

        for item in items:
            item.difference = item.counted_quantity - current[str(item.product_id)]
            if item.difference:
                item.applied_at = now

        session.status = "completed"
        session.completed_at = now
        session.completed_by_name = actor.worker_name
        session.completed_by_device = actor.device_name
        session.summary = {
            "adjusted_count": adjusted_count,
            "unchanged_count": len(items) - adjusted_count,
            "total_difference": total_difference,
            "line_count": len(items),
        }
        uow.commit()
        return StockCountCompletion(
            session_id=session.id,
            adjusted_count=adjusted_count,
            unchanged_count=len(items) - adjusted_count,
            total_difference=total_difference,
        )


def _to_view(
    session: StockCountSession,
    items: Sequence[StockCountItem],
    category_name: str | None,
) -> StockCountView:
    return StockCountView(
        id=session.id,
        count_number=session.count_number,
        category_id=session.category_id,
        category_name=category_name,
        status=session.status,
        stock_version=session.stock_version,
        note=session.note,
        started_at=session.started_at,
        completed_at=session.completed_at,
        completed_by_name=session.completed_by_name,
        items=tuple(
            CountSessionLine(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                system_quantity=item.system_quantity,
                counted_quantity=item.counted_quantity,
                difference=item.difference,
                applied_at=item.applied_at,
            )
            for item in items
        ),
        summary=session.summary,
    )


def _category_name(uow: UnitOfWork, session: StockCountSession) -> str | None:
    if session.category_id is None:
        return None
    category = uow.products.get_category(session.category_id)
    return category.name if category else None
