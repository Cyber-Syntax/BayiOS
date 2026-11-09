from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol

from bayios.adapters.db.models.inventory import StockCountItem, StockCountSession


class StockCountRepository(Protocol):
    """Stock count session persistence port."""

    def add_session(self, session: StockCountSession) -> None: ...

    def add_items(self, items: Sequence[StockCountItem]) -> None: ...

    def get_session(self, session_id: uuid.UUID) -> StockCountSession | None: ...

    def get_items(self, session_id: uuid.UUID) -> Sequence[StockCountItem]: ...

    def list_sessions(self, limit: int = 20) -> Sequence[StockCountSession]: ...

    def delete_item(self, item: StockCountItem) -> None: ...

    def stock_version(self, category_id: uuid.UUID | None) -> int: ...
