from __future__ import annotations

import uuid
from collections.abc import Sequence
from types import TracebackType
from typing import Self

from bayios.adapters.db.models.inventory import StockMovement
from bayios.adapters.db.models.products import Product, ProductImportBatch, ProductPriceHistory
from bayios.domain.products import normalize_product_name


class FakeProductRepository:
    def __init__(self) -> None:
        self.products: dict[uuid.UUID, Product] = {}
        self.price_history: list[ProductPriceHistory] = []
        self.stock_movements: list[StockMovement] = []
        self.import_batches: list[ProductImportBatch] = []

    def search(
        self, query: str | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[Product], int]:
        results = list(self.products.values())
        if query and query.strip():
            normalized = normalize_product_name(query)
            clean = query.strip().lower()
            results = [
                p
                for p in results
                if normalized in p.name_normalized or clean in p.name.lower()
            ]
        results.sort(key=lambda p: p.name)
        total = len(results)
        return results[offset : offset + limit], total

    def get_by_id(self, product_id: uuid.UUID) -> Product | None:
        return self.products.get(product_id)

    def get_by_normalized_name(self, normalized_name: str) -> Product | None:
        for p in self.products.values():
            if p.name_normalized == normalized_name:
                return p
        return None

    def get_by_normalized_names(self, names: Sequence[str]) -> dict[str, Product]:
        target = set(names)
        return {
            p.name_normalized: p
            for p in self.products.values()
            if p.name_normalized in target
        }

    def add(self, product: Product) -> None:
        self.products[product.id] = product

    def get_all(self) -> Sequence[Product]:
        results = list(self.products.values())
        results.sort(key=lambda p: p.name)
        return results

    def get_price_history(self, product_id: uuid.UUID) -> Sequence[ProductPriceHistory]:
        return [h for h in self.price_history if h.product_id == product_id]

    def get_stock_movements(self, product_id: uuid.UUID) -> Sequence[StockMovement]:
        return [m for m in self.stock_movements if m.product_id == product_id]

    def add_price_history(self, history: ProductPriceHistory) -> None:
        self.price_history.append(history)

    def add_stock_movement(self, movement: StockMovement) -> None:
        self.stock_movements.append(movement)

    def create_import_batch(self, batch: ProductImportBatch) -> None:
        self.import_batches.append(batch)

    def get_import_batch_by_checksum(self, checksum: str) -> ProductImportBatch | None:
        for b in reversed(self.import_batches):
            if b.source_checksum == checksum:
                return b
        return None


class FakeUnitOfWork:
    def __init__(self, repo: FakeProductRepository | None = None) -> None:
        self.products = repo or FakeProductRepository()
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rollback()

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True
