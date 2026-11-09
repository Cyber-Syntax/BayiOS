from __future__ import annotations

from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from bayios.adapters.db.repositories.products import SqlAlchemyProductRepository
from bayios.adapters.db.repositories.stock_counts import (
    SqlAlchemyStockCountRepository,
)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._products: SqlAlchemyProductRepository | None = None
        self._stock_counts: SqlAlchemyStockCountRepository | None = None
        self._committed = False

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork is not active; use it as a context manager")
        return self._session

    @property
    def products(self) -> SqlAlchemyProductRepository:
        if self._products is None:
            raise RuntimeError("UnitOfWork is not active; use it as a context manager")
        return self._products

    @property
    def stock_counts(self) -> SqlAlchemyStockCountRepository:
        if self._stock_counts is None:
            raise RuntimeError("UnitOfWork is not active; use it as a context manager")
        return self._stock_counts

    def __enter__(self) -> Self:
        if self._session is not None:
            raise RuntimeError("UnitOfWork is already active")
        self._session = self._session_factory()
        self._products = SqlAlchemyProductRepository(self._session)
        self._stock_counts = SqlAlchemyStockCountRepository(self._session)
        self._committed = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self.session
        try:
            if exc_type is not None:
                session.rollback()
            elif not self._committed and (session.dirty or session.new or session.deleted):
                # Rollback uncommitted write changes if any exist
                session.rollback()
        finally:
            session.close()
            self._session = None
            self._products = None
            self._stock_counts = None

    def commit(self) -> None:
        self.session.commit()
        self._committed = True

    def rollback(self) -> None:
        self.session.rollback()
        self._committed = False
