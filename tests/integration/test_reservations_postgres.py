from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from bayios.adapters.db.models.inventory import StockMovement
from bayios.adapters.db.models.products import Product
from bayios.adapters.db.models.reservations import Reservation, ReservationItem
from bayios.adapters.db.repositories.reservations import (
    SqlAlchemyReservationRepository,
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


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _product(name: str, stock: int = 5) -> Product:
    return Product(
        name=name,
        name_normalized=name.lower(),
        regular_price=Decimal("100.00"),
        physical_stock=stock,
    )


def _reservation(items: list[tuple[uuid.UUID, str, int]]) -> tuple[Reservation, list[ReservationItem]]:
    now = datetime.now(UTC)
    reservation = Reservation(
        customer_name="Test Müşteri",
        reservation_date=now,
        reminder_due_at=now + timedelta(days=395),
        reminder_status="pending",
    )
    lines = [
        ReservationItem(
            reservation_id=reservation.id,
            product_id=product_id,
            product_name_snapshot=name,
            quantity=quantity,
            status="reserved",
        )
        for product_id, name, quantity in items
    ]
    return reservation, lines


def _persist(
    session: Session, reservation: Reservation, lines: list[ReservationItem]
) -> SqlAlchemyReservationRepository:
    repository = SqlAlchemyReservationRepository(session)
    for line in lines:
        if line.reservation_id is None:
            line.reservation_id = reservation.id
    session.add(reservation)
    session.flush()
    repository.add_items(lines)
    session.commit()
    return repository


def test_migrations_apply_and_open_quantity_aggregates(session: Session) -> None:
    first = _product("07325 A")
    second = _product("09325 A")
    session.add_all([first, second])
    session.flush()

    reservation, lines = _reservation(
        [(first.id, first.name, 2), (second.id, second.name, 3)]
    )
    lines[0].delivered_quantity = 1
    repository = _persist(session, reservation, lines)

    totals = repository.open_quantity_by_product([first.id, second.id])

    assert totals == {first.id: 1, second.id: 3}
    assert repository.open_product_ids([first.id, second.id]) == {first.id, second.id}
    session.delete(first)
    session.commit()


def test_hard_deleted_product_keeps_closed_line_snapshot(session: Session) -> None:
    product = _product("09470 HP")
    session.add(product)
    session.flush()

    reservation, lines = _reservation([(product.id, product.name, 1)])
    lines[0].delivered_quantity = 1
    lines[0].status = "delivered"
    repository = _persist(session, reservation, lines)
    assert repository.open_product_ids([product.id]) == set()

    session.delete(product)
    session.commit()

    stored = session.get(ReservationItem, lines[0].id)
    assert stored is not None
    assert stored.product_id is None
    assert stored.product_name_snapshot == "09470 HP"


def test_duplicate_delivery_idempotency_key_is_rejected(session: Session) -> None:
    product = _product("09605")
    session.add(product)
    session.flush()

    reservation, lines = _reservation([(product.id, product.name, 2)])
    _persist(session, reservation, lines)

    key = f"reservation_delivery:{lines[0].id}:{uuid.uuid4()}"
    session.add(
        StockMovement(
            product_id=product.id,
            movement_type="delivery_out",
            quantity_delta=-1,
            quantity_before=5,
            quantity_after=4,
            reference_type="reservation_item",
            reference_id=lines[0].id,
            idempotency_key=key,
        )
    )
    session.commit()

    session.add(
        StockMovement(
            product_id=product.id,
            movement_type="delivery_out",
            quantity_delta=-1,
            quantity_before=4,
            quantity_after=3,
            reference_type="reservation_item",
            reference_id=lines[0].id,
            idempotency_key=key,
        )
    )
    with pytest.raises(sa.exc.IntegrityError):
        session.commit()
    session.rollback()
