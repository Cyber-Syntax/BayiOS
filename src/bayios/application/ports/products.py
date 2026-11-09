from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol

from bayios.adapters.db.models.inventory import StockMovement
from bayios.adapters.db.models.products import (
    Product,
    ProductCategory,
    ProductImportBatch,
    ProductPriceHistory,
)


class ProductRepository(Protocol):
    """Product catalog and import persistence port."""

    def search(
        self,
        query: str | None = None,
        category_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
        only_archived: bool = False,
    ) -> tuple[Sequence[Product], int]: ...

    def get_by_id(self, product_id: uuid.UUID) -> Product | None: ...

    def get_by_ids(self, product_ids: Sequence[uuid.UUID]) -> Sequence[Product]: ...

    def set_archived(self, product_ids: Sequence[uuid.UUID], archived: bool = True) -> int: ...

    def set_category(
        self, product_ids: Sequence[uuid.UUID], category_id: uuid.UUID | None
    ) -> int: ...

    def delete_products(self, product_ids: Sequence[uuid.UUID]) -> int: ...

    def get_by_normalized_name(self, normalized_name: str) -> Product | None: ...

    def get_by_normalized_names(self, names: Sequence[str]) -> dict[str, Product]: ...

    def add(self, product: Product) -> None: ...

    def get_all(self) -> Sequence[Product]: ...

    def list_by_category(
        self,
        category_id: uuid.UUID | None,
        include_archived: bool = False,
    ) -> Sequence[Product]: ...

    def search_by_category(
        self,
        category_id: uuid.UUID | None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
    ) -> tuple[Sequence[Product], int]: ...

    def get_categories(self) -> Sequence[ProductCategory]: ...

    def get_category(self, category_id: uuid.UUID) -> ProductCategory | None: ...

    def get_category_by_name(self, name: str) -> ProductCategory | None: ...

    def add_category(self, category: ProductCategory) -> None: ...

    def get_price_history(self, product_id: uuid.UUID) -> Sequence[ProductPriceHistory]: ...

    def get_stock_movements(self, product_id: uuid.UUID) -> Sequence[StockMovement]: ...

    def add_price_history(self, history: ProductPriceHistory) -> None: ...

    def add_stock_movement(self, movement: StockMovement) -> None: ...

    def create_import_batch(self, batch: ProductImportBatch) -> None: ...

    def get_import_batch_by_checksum(self, checksum: str) -> ProductImportBatch | None: ...
