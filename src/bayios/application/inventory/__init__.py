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
from bayios.domain.commissions import commission_group_for_category_name
from bayios.domain.inventory import (
    CountSession,
    MovementType,
    StockSummary,
    complete_count_session,
    reverse_count_session,
)
from bayios.domain.inventory import StockMovement as DomainStockMovement
from bayios.domain.naming import canonical_display_name
from bayios.domain.products import ActorContext, normalize_category_name

COUNT_MODES = ("category", "quick")


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
    mode: str
    stock_version: int
    note: str | None
    started_at: datetime
    completed_at: datetime | None
    completed_by_name: str | None
    cancelled_at: datetime | None
    cancelled_by_name: str | None
    cancel_reason: str | None
    reversed_at: datetime | None
    items: tuple[CountSessionLine, ...]
    summary: Mapping[str, object] | None

    @property
    def counted_lines(self) -> int:
        return sum(1 for item in self.items if item.counted_quantity is not None)

    @property
    def skipped_lines(self) -> int:
        return len(self.items) - self.counted_lines

    @property
    def has_counted(self) -> bool:
        return self.counted_lines > 0

    @property
    def all_counted(self) -> bool:
        return bool(self.items) and self.skipped_lines == 0

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
    counted_count: int = 0
    skipped_count: int = 0


def get_stock_overview(
    uow: UnitOfWork,
    category_id: uuid.UUID | None = None,
    query: str | None = None,
    open_reservations: Mapping[uuid.UUID, int] | None = None,
    limit: int | None = None,
    offset: int = 0,
    only_in_stock: bool = False,
) -> tuple[tuple[StockOverviewRow, ...], int]:
    reservations = open_reservations
    with uow:
        products, total = uow.products.search_by_category(
            category_id=category_id,
            query=query,
            limit=limit or 10_000,
            offset=offset,
            in_stock_only=only_in_stock,
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


def create_product_category(
    uow: UnitOfWork,
    name: str,
    commission_group: str | None = None,
) -> ProductCategory:
    clean_name = name.strip()
    if not clean_name:
        raise ValidationError("Kategori adı boş olamaz.")
    normalized = normalize_category_name(clean_name)
    canonical = canonical_display_name(clean_name)
    if commission_group is None:
        commission_group = commission_group_for_category_name(canonical).value
    if commission_group not in {"klima", "other"}:
        raise ValidationError("Geçersiz komisyon grubu.")
    with uow:
        if uow.products.get_category_by_normalized(normalized) is not None:
            raise ValidationError(f"'{canonical}' adında bir kategori zaten mevcut.")
        category = ProductCategory(
            id=uuid.uuid4(),
            name=canonical,
            name_normalized=normalized,
            commission_group=commission_group,
        )
        uow.products.add_category(category)
        uow.commit()
        return category


def update_product_category_group(
    uow: UnitOfWork,
    category_id: uuid.UUID,
    commission_group: str,
) -> None:
    if commission_group not in {"klima", "other"}:
        raise ValidationError("Geçersiz komisyon grubu.")
    with uow:
        category = uow.products.get_category(category_id)
        if category is None:
            raise NotFoundError("Kategori bulunamadı.")
        category.commission_group = commission_group
        uow.commit()


def open_stock_count_session(
    uow: UnitOfWork,
    category_id: uuid.UUID | None,
    actor: ActorContext | None = None,
    note: str | None = None,
    mode: str = "category",
) -> StockCountView:
    actor = actor or ActorContext()
    if mode not in COUNT_MODES:
        raise ValidationError("Geçersiz sayım türü.")
    now = datetime.now(UTC)
    with uow:
        category = None
        if category_id is not None:
            category = uow.products.get_category(category_id)
            if category is None:
                raise NotFoundError("Kategori bulunamadı.")
        products: list[Product] = []
        if mode == "category":
            products = list(uow.products.list_by_category(category_id))
            if not products:
                raise ValidationError("Bu kategoride sayılacak aktif ürün bulunmuyor.")

        session = StockCountSession(
            id=uuid.uuid4(),
            category_id=category_id,
            status="open",
            mode=mode,
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
        if items:
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


def add_stock_count_line(
    uow: UnitOfWork,
    session_id: uuid.UUID,
    product_id: uuid.UUID,
) -> StockCountView:
    with uow:
        session = uow.stock_counts.get_session(session_id)
        if session is None:
            raise NotFoundError("Sayım oturumu bulunamadı.")
        if session.status in ("completed", "cancelled"):
            raise ValidationError("Tamamlanmış veya iptal edilmiş sayıma ürün eklenemez.")
        if session.mode != "quick":
            raise ValidationError("Ürün ekleme yalnızca hızlı sayımda kullanılabilir.")
        product = uow.products.get_by_id(product_id)
        if product is None:
            raise NotFoundError("Ürün bulunamadı.")
        if product.is_archived:
            raise ValidationError("Arşivlenmiş ürün sayıma eklenemez.")
        if session.category_id is not None and product.category_id != session.category_id:
            raise ValidationError("Ürün bu sayımın kategorisinde değil.")

        items = list(uow.stock_counts.get_items(session_id))
        if any(item.product_id == product_id for item in items):
            return _to_view(session, items, _category_name(uow, session))
        item = StockCountItem(
            id=uuid.uuid4(),
            session_id=session.id,
            product_id=product.id,
            product_name=product.name,
            system_quantity=product.physical_stock,
        )
        uow.stock_counts.add_items([item])
        items.append(item)
        uow.commit()
        return _to_view(session, items, _category_name(uow, session))


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
            raise ValidationError("Tamamlanmış veya iptal edilmiş sayım değiştirilemez.")

        items = list(uow.stock_counts.get_items(session_id))
        for item in items:
            if item.product_id not in counted:
                continue
            quantity = counted[item.product_id]
            if quantity is not None and quantity < 0:
                raise ValidationError("Sayılan miktar negatif olamaz.")
            if quantity is not None and quantity == 0:
                quantity = None
            item.counted_quantity = quantity
            item.difference = (
                None if quantity is None else quantity - item.system_quantity
            )

        session.status = "open"
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
            raise ValidationError("Tamamlanmış veya iptal edilmiş sayım yenilenemez.")

        items = list(uow.stock_counts.get_items(session_id))
        if session.mode == "quick":
            product_ids = [item.product_id for item in items]
            products = {
                product.id: product
                for product in uow.products.get_by_ids(product_ids)
            }
            remaining_items: list[StockCountItem] = []
            for item in items:
                product = products.get(item.product_id)
                if product is None or product.is_archived:
                    uow.stock_counts.delete_item(item)
                    continue
                item.system_quantity = product.physical_stock
                item.difference = (
                    None
                    if item.counted_quantity is None
                    else item.counted_quantity - item.system_quantity
                )
                remaining_items.append(item)
        else:
            current_products = {
                product.id: product
                for product in uow.products.list_by_category(session.category_id)
            }
            remaining_items = []
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
        session.status = "open"
        uow.commit()
        return _to_view(session, remaining_items, _category_name(uow, session))


def save_and_complete_stock_count(
    uow: UnitOfWork,
    session_id: uuid.UUID,
    counted: Mapping[uuid.UUID, int | None],
    actor: ActorContext | None = None,
) -> StockCountCompletion:
    """Entered positive counts are applied; blank/zero/uncounted lines are skipped."""
    actor = actor or ActorContext()
    now = datetime.now(UTC)
    with uow:
        session = uow.stock_counts.get_session(session_id)
        if session is None:
            raise NotFoundError("Sayım oturumu bulunamadı.")
        return _complete_stock_count(uow, session, counted, actor, now)


def complete_stock_count_session(
    uow: UnitOfWork,
    session_id: uuid.UUID,
    actor: ActorContext | None = None,
    *,
    acknowledge_differences: bool = False,
) -> StockCountCompletion:
    """Compatibility entry point: applies the quantities already saved as draft."""
    del acknowledge_differences
    actor = actor or ActorContext()
    now = datetime.now(UTC)
    with uow:
        session = uow.stock_counts.get_session(session_id)
        if session is None:
            raise NotFoundError("Sayım oturumu bulunamadı.")
        return _complete_stock_count(uow, session, None, actor, now)


def _complete_stock_count(
    uow: UnitOfWork,
    session: StockCountSession,
    counted: Mapping[uuid.UUID, int | None] | None,
    actor: ActorContext,
    now: datetime,
) -> StockCountCompletion:
    if session.status == "completed":
        summary = session.summary or {}
        return StockCountCompletion(
            session_id=session.id,
            adjusted_count=int(summary.get("adjusted_count", 0)),
            unchanged_count=int(summary.get("unchanged_count", 0)),
            total_difference=int(summary.get("total_difference", 0)),
            counted_count=int(summary.get("counted_count", 0)),
            skipped_count=int(summary.get("skipped_count", 0)),
        )
    if session.status == "cancelled":
        raise ValidationError("İptal edilmiş sayım kaydedilemez.")

    items = list(uow.stock_counts.get_items(session.id))
    if not items:
        raise ValidationError("Sayım oturumunda ürün bulunmuyor.")

    # Preserve drafts saved on other pagination pages; only submitted fields replace them.
    merged = {item.product_id: item.counted_quantity for item in items}
    if counted is not None:
        item_ids = set(merged)
        merged.update(
            {
                product_id: quantity
                for product_id, quantity in counted.items()
                if product_id in item_ids
            }
        )
    positive = _normalize_counted(merged)

    product_ids = list(positive)
    products = {
        product.id: product for product in uow.products.get_by_ids(product_ids)
    }
    if len(products) != len(product_ids):
        raise ConflictError(
            "Sayımdaki bazı ürünler artık mevcut değil. Sayımı yenileyin."
        )

    current = {
        str(product_id): products[product_id].physical_stock
        for product_id in product_ids
    }
    snapshots = {str(item.product_id): item.system_quantity for item in items}
    domain_session = CountSession(
        category_id=str(session.category_id or "all"),
        snapshots=snapshots,
        stock_version=session.stock_version,
        opened_at=session.started_at,
    )
    try:
        completion = complete_count_session(
            domain_session,
            counted_quantities={
                str(product_id): quantity for product_id, quantity in positive.items()
            },
            current_quantities=current,
            actor_name=actor.worker_name,
            completed_at=now,
        )
    except ValueError as exc:
        message = str(exc)
        if "stok değişti" in message or "güncel değil" in message:
            raise ConflictError(message) from exc
        raise ValidationError(message) from exc

    for movement in completion.movements:
        product_id = uuid.UUID(movement.product_id)
        product = products[product_id]
        product.physical_stock = movement.quantity_after
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

    adjusted_ids = {uuid.UUID(product_id) for product_id in completion.adjustments}
    for item in items:
        quantity = positive.get(item.product_id)
        if quantity is None:
            item.counted_quantity = None
            item.difference = None
            item.applied_at = None
            continue
        item.counted_quantity = quantity
        item.difference = quantity - int(current[str(item.product_id)])
        item.applied_at = now if item.product_id in adjusted_ids else None

    adjusted_count = len(completion.adjustments)
    counted_count = len(positive)
    skipped_count = len(items) - counted_count
    session.status = "completed"
    session.completed_at = now
    session.completed_by_name = actor.worker_name
    session.completed_by_device = actor.device_name
    session.summary = {
        "adjusted_count": adjusted_count,
        "unchanged_count": counted_count - adjusted_count,
        "counted_count": counted_count,
        "skipped_count": skipped_count,
        "total_difference": completion.total_difference,
        "line_count": len(items),
    }
    uow.commit()
    return StockCountCompletion(
        session_id=session.id,
        adjusted_count=adjusted_count,
        unchanged_count=counted_count - adjusted_count,
        total_difference=completion.total_difference,
        counted_count=counted_count,
        skipped_count=skipped_count,
    )


def cancel_stock_count_session(
    uow: UnitOfWork,
    session_id: uuid.UUID,
    actor: ActorContext | None = None,
    reason: str | None = None,
) -> StockCountView:
    """Cancel an open count without touching stock.

    A completed count is reversed with compensating movements, so stock returns
    to its pre-count value. If stock changed after the count, reversal is refused.
    """
    actor = actor or ActorContext()
    now = datetime.now(UTC)
    with uow:
        session = uow.stock_counts.get_session(session_id)
        if session is None:
            raise NotFoundError("Sayım oturumu bulunamadı.")
        if session.status == "cancelled":
            return _to_view(
                session,
                uow.stock_counts.get_items(session_id),
                _category_name(uow, session),
            )

        if session.status == "completed":
            stored_movements = tuple(
                uow.products.get_stock_movements_for_reference(
                    "stock_count_session", session.id
                )
            )
            if stored_movements:
                movements = tuple(
                    DomainStockMovement(
                        product_id=str(movement.product_id),
                        movement_type=MovementType(movement.movement_type),
                        quantity_delta=movement.quantity_delta,
                        quantity_before=movement.quantity_before,
                        quantity_after=movement.quantity_after,
                        created_at=movement.created_at,
                        actor_name=movement.created_by_name,
                    )
                    for movement in stored_movements
                )
                product_ids = [uuid.UUID(movement.product_id) for movement in movements]
                products = {
                    product.id: product
                    for product in uow.products.get_by_ids(product_ids)
                }
                if len(products) != len(product_ids):
                    raise ConflictError(
                        "Sayımdaki bazı ürünler artık mevcut değil; sayım geri alınamaz."
                    )
                current = {
                    movement.product_id: products[
                        uuid.UUID(movement.product_id)
                    ].physical_stock
                    for movement in movements
                }
                domain_session = CountSession(
                    category_id=str(session.category_id or "all"),
                    snapshots={},
                    stock_version=session.stock_version,
                    opened_at=session.started_at,
                    completed=True,
                )
                try:
                    reversal = reverse_count_session(
                        domain_session,
                        movements,
                        current,
                        actor.worker_name,
                        reversed_at=now,
                    )
                except ValueError as exc:
                    raise ConflictError(str(exc)) from exc
                for movement in reversal.movements:
                    product_id = uuid.UUID(movement.product_id)
                    products[product_id].physical_stock = movement.quantity_after
                    uow.products.add_stock_movement(
                        StockMovement(
                            id=uuid.uuid4(),
                            product_id=product_id,
                            movement_type="reversal",
                            quantity_delta=movement.quantity_delta,
                            quantity_before=movement.quantity_before,
                            quantity_after=movement.quantity_after,
                            reference_type="stock_count_session",
                            reference_id=session.id,
                            note=reason
                            or f"Sayım geri alındı #{session.count_number}",
                            idempotency_key=(
                                f"stock_count_reverse:{session.id}:{product_id}"
                            ),
                            created_at=now,
                            created_by_name=actor.worker_name,
                            created_by_device=actor.device_name,
                        )
                    )
                summary = dict(session.summary or {})
                summary["reversed"] = True
                summary["reversed_at"] = now.isoformat()
                summary["reversal_count"] = len(reversal.movements)
                session.summary = summary
                session.reversed_at = now

        session.status = "cancelled"
        session.cancelled_at = now
        session.cancelled_by_name = actor.worker_name
        session.cancelled_by_device = actor.device_name
        cleaned_reason = (reason or "").strip()
        session.cancel_reason = cleaned_reason or None
        uow.commit()
        return _to_view(
            session,
            uow.stock_counts.get_items(session_id),
            _category_name(uow, session),
        )


def _normalize_counted(
    counted: Mapping[uuid.UUID, int | None],
) -> dict[uuid.UUID, int]:
    normalized: dict[uuid.UUID, int] = {}
    for product_id, quantity in counted.items():
        if quantity is None:
            continue
        if quantity < 0:
            raise ValidationError("Sayılan miktar negatif olamaz.")
        if quantity == 0:
            continue
        normalized[product_id] = quantity
    return normalized


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
        mode=getattr(session, "mode", None) or "category",
        stock_version=session.stock_version,
        note=session.note,
        started_at=session.started_at,
        completed_at=session.completed_at,
        completed_by_name=session.completed_by_name,
        cancelled_at=session.cancelled_at,
        cancelled_by_name=session.cancelled_by_name,
        cancel_reason=session.cancel_reason,
        reversed_at=session.reversed_at,
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
