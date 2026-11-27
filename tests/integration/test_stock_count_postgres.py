from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from bayios.adapters.db.models.products import Product
from bayios.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from bayios.application.errors import ConflictError
from bayios.application.inventory import (
    cancel_stock_count_session,
    get_stock_count_session,
    open_stock_count_session,
    save_and_complete_stock_count,
)

TEST_DATABASE_URL = os.environ.get("BAYIOS_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason=(
        "BAYIOS_TEST_DATABASE_URL is not set; integration tests need a real "
        "PostgreSQL (SQLite fallback is not supported)"
    ),
)


@pytest.fixture(scope="module")
def session_factory() -> Iterator[sessionmaker[Session]]:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL, future=True)
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))

    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(Config("alembic.ini"), "head")

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def _add_product(session_factory: sessionmaker[Session], stock: int = 5) -> uuid.UUID:
    session = session_factory()
    try:
        product = Product(
            name="Test Ürün",
            name_normalized="test ürün",
            regular_price=Decimal("100.00"),
            physical_stock=stock,
        )
        session.add(product)
        session.commit()
        return product.id
    finally:
        session.close()


def _stock(session_factory: sessionmaker[Session], product_id: uuid.UUID) -> int:
    session = session_factory()
    try:
        product = session.get(Product, product_id)
        assert product is not None
        return product.physical_stock
    finally:
        session.close()


def test_count_save_is_atomic_and_idempotent(
    session_factory: sessionmaker[Session],
) -> None:
    product_id = _add_product(session_factory)
    uow = SqlAlchemyUnitOfWork(session_factory)

    view = open_stock_count_session(uow, category_id=None)
    result = save_and_complete_stock_count(uow, view.id, {product_id: 3})

    assert result.adjusted_count == 1
    assert _stock(session_factory, product_id) == 3

    retry = save_and_complete_stock_count(uow, view.id, {product_id: 1})

    assert retry == result
    assert _stock(session_factory, product_id) == 3
    completed = get_stock_count_session(SqlAlchemyUnitOfWork(session_factory), view.id)
    assert completed is not None
    assert completed.status == "completed"


def test_cancelling_completed_count_reverses_stock(
    session_factory: sessionmaker[Session],
) -> None:
    product_id = _add_product(session_factory)
    uow = SqlAlchemyUnitOfWork(session_factory)
    view = open_stock_count_session(uow, category_id=None)
    save_and_complete_stock_count(uow, view.id, {product_id: 3})

    cancel_stock_count_session(
        SqlAlchemyUnitOfWork(session_factory), view.id, reason="Yanlış sayım"
    )

    assert _stock(session_factory, product_id) == 5
    cancelled = get_stock_count_session(SqlAlchemyUnitOfWork(session_factory), view.id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancelled.reversed_at is not None


def test_cancelling_completed_count_refuses_changed_stock(
    session_factory: sessionmaker[Session],
) -> None:
    product_id = _add_product(session_factory)
    uow = SqlAlchemyUnitOfWork(session_factory)
    view = open_stock_count_session(uow, category_id=None)
    save_and_complete_stock_count(uow, view.id, {product_id: 3})

    session = session_factory()
    try:
        product = session.get(Product, product_id)
        assert product is not None
        product.physical_stock = 4
        session.commit()
    finally:
        session.close()

    with pytest.raises(ConflictError, match="stok değişti"):
        cancel_stock_count_session(SqlAlchemyUnitOfWork(session_factory), view.id)

    assert _stock(session_factory, product_id) == 4
