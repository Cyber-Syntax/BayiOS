from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from bayios.adapters.db.models.inventory import StockMovement
from bayios.adapters.db.models.products import Product, ProductImportBatch, ProductPriceHistory
from bayios.domain.products import normalize_product_name


class SqlAlchemyProductRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def search(
        self, query: str | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[Product], int]:
        stmt = sa.select(Product)
        count_stmt = sa.select(sa.func.count(Product.id))

        if query and query.strip():
            normalized = normalize_product_name(query)
            clean_query = query.strip()
            # Support prefix / substring search on both normalized and display name (preserving leading zeroes)
            filter_clause = sa.or_(
                Product.name_normalized.contains(normalized),
                Product.name.ilike(f"%{clean_query}%"),
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

    def get_by_normalized_name(self, normalized_name: str) -> Product | None:
        return self._session.scalar(
            sa.select(Product).where(Product.name_normalized == normalized_name)
        )

    def get_by_normalized_names(self, names: Sequence[str]) -> dict[str, Product]:
        if not names:
            return {}
        products = self._session.scalars(
            sa.select(Product).where(Product.name_normalized.in_(names))
        ).all()
        return {p.name_normalized: p for p in products}

    def add(self, product: Product) -> None:
        self._session.add(product)

    def get_all(self) -> Sequence[Product]:
        return self._session.scalars(sa.select(Product).order_by(Product.name)).all()

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
