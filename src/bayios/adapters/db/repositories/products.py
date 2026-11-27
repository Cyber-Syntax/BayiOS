from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from bayios.adapters.db.models.inventory import StockMovement
from bayios.adapters.db.models.products import (
    Product,
    ProductCategory,
    ProductExternalIdHistory,
    ProductImportBatch,
    ProductPriceHistory,
)
from bayios.domain.products import normalize_product_name


class SqlAlchemyProductRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def search(
        self,
        query: str | None = None,
        category_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
        only_archived: bool = False,
    ) -> tuple[Sequence[Product], int]:
        stmt = sa.select(Product)
        count_stmt = sa.select(sa.func.count(Product.id))

        if only_archived:
            stmt = stmt.where(Product.is_archived.is_(True))
            count_stmt = count_stmt.where(Product.is_archived.is_(True))
        elif not include_archived:
            stmt = stmt.where(Product.is_archived.is_(False))
            count_stmt = count_stmt.where(Product.is_archived.is_(False))

        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
            count_stmt = count_stmt.where(Product.category_id == category_id)

        if query and query.strip():
            normalized = normalize_product_name(query)
            clean_query = query.strip()
            # Support prefix / substring search on both normalized and display name (preserving leading zeroes)
            filter_clause = sa.or_(
                Product.name_normalized.contains(normalized),
                Product.name.ilike(f"%{clean_query}%"),
                Product.external_id.ilike(f"%{clean_query}%"),
            )
            stmt = stmt.where(filter_clause)
            count_stmt = count_stmt.where(filter_clause)

        total_count = self._session.scalar(count_stmt) or 0
        products = self._session.scalars(
            stmt.order_by(Product.name).limit(limit).offset(offset)
        ).all()
        return products, total_count

    def get_by_id(self, product_id: uuid.UUID) -> Product | None:
        return self._session.get(Product, product_id)

    def get_by_ids(self, product_ids: Sequence[uuid.UUID]) -> Sequence[Product]:
        if not product_ids:
            return []
        return self._session.scalars(
            sa.select(Product).where(Product.id.in_(product_ids))
        ).all()

    def set_archived(self, product_ids: Sequence[uuid.UUID], archived: bool = True) -> int:
        if not product_ids:
            return 0
        result = self._session.execute(
            sa.update(Product)
            .where(Product.id.in_(product_ids))
            .values(is_archived=archived, updated_at=sa.func.now())
        )
        return result.rowcount or 0

    def delete_products(self, product_ids: Sequence[uuid.UUID]) -> int:
        if not product_ids:
            return 0
        # Price history and stock movements are removed by ON DELETE CASCADE.
        result = self._session.execute(
            sa.delete(Product).where(Product.id.in_(product_ids))
        )
        return result.rowcount or 0

    def set_category(
        self, product_ids: Sequence[uuid.UUID], category_id: uuid.UUID | None
    ) -> int:
        if not product_ids:
            return 0
        result = self._session.execute(
            sa.update(Product)
            .where(Product.id.in_(product_ids))
            .values(category_id=category_id, updated_at=sa.func.now())
        )
        return result.rowcount or 0

    def get_by_external_id(self, external_id: str) -> Product | None:
        return self._session.scalar(
            sa.select(Product).where(Product.external_id == external_id)
        )

    def get_by_external_ids(
        self, external_ids: Sequence[str]
    ) -> dict[str, Product]:
        if not external_ids:
            return {}
        products = self._session.scalars(
            sa.select(Product).where(Product.external_id.in_(external_ids))
        ).all()
        return {p.external_id: p for p in products if p.external_id}

    def get_by_external_id_including_history(
        self, external_id: str
    ) -> Product | None:
        current = self.get_by_external_id(external_id)
        if current is not None:
            return current
        return self._session.scalar(
            sa.select(Product)
            .join(
                ProductExternalIdHistory,
                ProductExternalIdHistory.product_id == Product.id,
            )
            .where(ProductExternalIdHistory.external_id == external_id)
        )

    def get_by_normalized_name(self, normalized_name: str) -> Product | None:
        return self._session.scalar(
            sa.select(Product)
            .where(Product.name_normalized == normalized_name)
            .order_by(Product.created_at)
        )

    def get_by_normalized_names(self, names: Sequence[str]) -> dict[str, Product]:
        grouped = self.find_by_normalized_names(names)
        return {
            name: products[0]
            for name, products in grouped.items()
            if products
        }

    def find_by_normalized_names(
        self, names: Sequence[str]
    ) -> dict[str, list[Product]]:
        if not names:
            return {}
        products = self._session.scalars(
            sa.select(Product)
            .where(Product.name_normalized.in_(names))
            .order_by(Product.created_at)
        ).all()
        grouped: dict[str, list[Product]] = {}
        for product in products:
            grouped.setdefault(product.name_normalized, []).append(product)
        return grouped

    def add_external_id_history(
        self, entry: ProductExternalIdHistory
    ) -> None:
        self._session.add(entry)
        self._session.flush()

    def get_external_id_history(self) -> Sequence[ProductExternalIdHistory]:
        return self._session.scalars(
            sa.select(ProductExternalIdHistory)
        ).all()

    def delete_external_id_history(self, external_id: str) -> None:
        self._session.execute(
            sa.delete(ProductExternalIdHistory).where(
                ProductExternalIdHistory.external_id == external_id
            )
        )
        self._session.flush()

    def add(self, product: Product) -> None:
        # Flush immediately so dependent rows (price history / stock movements)
        # always have the parent product row to satisfy their foreign keys.
        self._session.add(product)
        self._session.flush()

    def get_all(self) -> Sequence[Product]:
        return self._session.scalars(sa.select(Product).order_by(Product.name)).all()

    def list_by_category(
        self,
        category_id: uuid.UUID | None,
        include_archived: bool = False,
    ) -> Sequence[Product]:
        stmt = sa.select(Product)
        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
        if not include_archived:
            stmt = stmt.where(Product.is_archived.is_(False))
        return self._session.scalars(stmt.order_by(Product.name)).all()

    def search_by_category(
        self,
        category_id: uuid.UUID | None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
        in_stock_only: bool = False,
    ) -> tuple[Sequence[Product], int]:
        stmt = sa.select(Product)
        count_stmt = sa.select(sa.func.count(Product.id))
        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
            count_stmt = count_stmt.where(Product.category_id == category_id)
        if not include_archived:
            stmt = stmt.where(Product.is_archived.is_(False))
            count_stmt = count_stmt.where(Product.is_archived.is_(False))
        if in_stock_only:
            stmt = stmt.where(Product.physical_stock > 0)
            count_stmt = count_stmt.where(Product.physical_stock > 0)
        if query and query.strip():
            normalized = normalize_product_name(query)
            clean_query = query.strip()
            filter_clause = sa.or_(
                Product.name_normalized.contains(normalized),
                Product.name.ilike(f"%{clean_query}%"),
                Product.external_id.ilike(f"%{clean_query}%"),
            )
            stmt = stmt.where(filter_clause)
            count_stmt = count_stmt.where(filter_clause)

        total_count = self._session.scalar(count_stmt) or 0
        products = self._session.scalars(
            stmt.order_by(Product.name).limit(limit).offset(offset)
        ).all()
        return products, total_count

    def get_categories(self) -> Sequence[ProductCategory]:
        return self._session.scalars(
            sa.select(ProductCategory).order_by(ProductCategory.name)
        ).all()

    def get_category(self, category_id: uuid.UUID) -> ProductCategory | None:
        return self._session.get(ProductCategory, category_id)

    def get_category_by_name(self, name: str) -> ProductCategory | None:
        return self._session.scalar(
            sa.select(ProductCategory).where(ProductCategory.name == name)
        )

    def get_category_by_normalized(
        self, name_normalized: str
    ) -> ProductCategory | None:
        return self._session.scalar(
            sa.select(ProductCategory).where(
                ProductCategory.name_normalized == name_normalized
            )
        )

    def add_category(self, category: ProductCategory) -> None:
        self._session.add(category)
        self._session.flush()

    def category_usage_counts(self) -> dict[uuid.UUID, int]:
        rows = self._session.execute(
            sa.select(Product.category_id, sa.func.count())
            .where(Product.category_id.is_not(None))
            .group_by(Product.category_id)
        ).all()
        return {category_id: count for category_id, count in rows}

    def reassign_category(
        self, source_id: uuid.UUID, target_id: uuid.UUID
    ) -> None:
        self._session.execute(
            sa.update(Product)
            .where(Product.category_id == source_id)
            .values(category_id=target_id)
        )
        self._session.flush()

    def delete_category(self, category_id: uuid.UUID) -> None:
        category = self._session.get(ProductCategory, category_id)
        if category is not None:
            self._session.delete(category)
            self._session.flush()

    def get_price_history(self, product_id: uuid.UUID) -> Sequence[ProductPriceHistory]:
        return self._session.scalars(
            sa.select(ProductPriceHistory)
            .where(ProductPriceHistory.product_id == product_id)
            .order_by(ProductPriceHistory.changed_at.desc())
        ).all()

    def get_stock_movements(self, product_id: uuid.UUID) -> Sequence[StockMovement]:
        return self._session.scalars(
            sa.select(StockMovement)
            .where(StockMovement.product_id == product_id)
            .order_by(StockMovement.created_at.desc())
        ).all()

    def add_price_history(self, history: ProductPriceHistory) -> None:
        self._session.add(history)

    def get_stock_movements_for_reference(
        self, reference_type: str, reference_id: uuid.UUID
    ) -> Sequence[StockMovement]:
        return self._session.scalars(
            sa.select(StockMovement)
            .where(
                StockMovement.reference_type == reference_type,
                StockMovement.reference_id == reference_id,
            )
            .order_by(StockMovement.created_at)
        ).all()

    def add_stock_movement(self, movement: StockMovement) -> None:
        self._session.add(movement)

    def create_import_batch(self, batch: ProductImportBatch) -> None:
        self._session.add(batch)

    def get_import_batch_by_checksum(self, checksum: str) -> ProductImportBatch | None:
        return self._session.scalar(
            sa.select(ProductImportBatch)
            .where(ProductImportBatch.source_checksum == checksum)
            .order_by(ProductImportBatch.started_at.desc())
        )
