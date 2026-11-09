from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from bayios.adapters.db.models.inventory import (
    StockCountItem,
    StockCountSession,
    StockMovement,
)
from bayios.adapters.db.models.products import Product


class SqlAlchemyStockCountRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_session(self, session: StockCountSession) -> None:
        self._session.add(session)
        self._session.flush()

    def add_items(self, items: Sequence[StockCountItem]) -> None:
        self._session.add_all(items)
        self._session.flush()

    def get_session(self, session_id: uuid.UUID) -> StockCountSession | None:
        return self._session.get(StockCountSession, session_id)

    def get_items(self, session_id: uuid.UUID) -> Sequence[StockCountItem]:
        return self._session.scalars(
            sa.select(StockCountItem)
            .where(StockCountItem.session_id == session_id)
            .order_by(StockCountItem.product_name)
        ).all()

    def list_sessions(self, limit: int = 20) -> Sequence[StockCountSession]:
        return self._session.scalars(
            sa.select(StockCountSession)
            .order_by(StockCountSession.started_at.desc())
            .limit(limit)
        ).all()

    def delete_item(self, item: StockCountItem) -> None:
        self._session.delete(item)

    def stock_version(self, category_id: uuid.UUID | None) -> int:
        stmt = (
            sa.select(sa.func.count(StockMovement.id))
            .select_from(StockMovement)
            .join(Product, StockMovement.product_id == Product.id)
        )
        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
        return int(self._session.scalar(stmt) or 0)
