from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from bayios.adapters.db.models.commissions import (
    Bank,
    CommissionLimit,
    CommissionPeriod,
    CommissionRate,
)
from bayios.adapters.db.models.offers import Offer
from bayios.adapters.db.models.products import ProductCategory
from bayios.domain.commissions import period_bounds

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


def test_bankless_rate_and_category_limit_constraints(
    session_factory: sessionmaker[Session],
) -> None:
    start, end = period_bounds(2026, 12)
    with session_factory() as session:
        bank = Bank(name="Test Bank", name_normalized="test bank")
        category = ProductCategory(
            name="Test TV Kategori",
            name_normalized="test tv kategori",
            commission_group="other",
        )
        period = CommissionPeriod(
            period_key="2026-12",
            valid_from=start,
            valid_until=end,
            status="active",
        )
        session.add_all([bank, category, period])
        session.flush()

        session.add(
            CommissionRate(
                period_id=period.id,
                channel="pos",
                bank_id=None,
                product_group="other",
                installment_count=2,
                commission_percent=Decimal(5),
                scope_key="pos|-|other|-|2",
            )
        )
        session.add(
            CommissionLimit(
                period_id=period.id,
                channel=None,
                bank_id=None,
                product_group=None,
                category_id=category.id,
                card_type=None,
                max_installments=4,
                scope_key=f"-|-|-|{category.id}|-",
            )
        )
        session.add(
            Offer(
                payment_type="card",
                channel="pos",
                bank_id=None,
                installment_count=2,
                card_type="consumer",
                commission_percent_snapshot=Decimal(5),
                commission_source="general",
            )
        )
        session.commit()

    with session_factory() as session:
        session.add(Bank(name="TEST BANK", name_normalized="test bank"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with session_factory() as session:
        category_id = session.scalar(sa.select(ProductCategory.id))
        period_id = session.scalar(sa.select(CommissionPeriod.id))
        session.add(
            CommissionLimit(
                period_id=period_id,
                channel="pos",
                bank_id=session.scalar(sa.select(Bank.id)),
                product_group=None,
                category_id=category_id,
                card_type=None,
                max_installments=8,
                scope_key=f"pos|bank|{category_id}|-",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
