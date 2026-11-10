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
from bayios.adapters.db.models.campaigns import (
    Campaign,
    CampaignVersion,
    CampaignVersionProduct,
    DealerPricing,
    DealerPricingHistory,
)
from bayios.adapters.db.models.products import Product
from bayios.adapters.db.repositories.campaigns import SqlAlchemyCampaignRepository
from bayios.adapters.db.repositories.dealer_pricing import (
    SqlAlchemyDealerPricingRepository,
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


def test_campaign_and_dealer_pricing_roundtrip(
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime.now(UTC)
    with session_factory() as session:
        product = Product(
            name="A4 Test Buzdolabı",
            name_normalized="a4 test buzdolabı",
            regular_price=Decimal("25999.00"),
            website_discounted_price=Decimal("23999.00"),
            physical_stock=1,
        )
        session.add(product)
        session.flush()

        campaign_repo = SqlAlchemyCampaignRepository(session)
        campaign = Campaign(id=uuid.uuid4(), is_archived=False)
        campaign_repo.add(campaign)
        version = CampaignVersion(
            id=uuid.uuid4(),
            campaign_id=campaign.id,
            version_no=1,
            name="Hediye Kampanyası",
            campaign_type="gift",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=30),
            base_price_type="regular",
            discount_type="gift",
            gift_description="Buzdolabı hediye",
            gift_optional=True,
            created_at=now,
        )
        campaign_repo.add_version(version)
        campaign_repo.add_version_products(
            [
                CampaignVersionProduct(
                    id=uuid.uuid4(),
                    campaign_version_id=version.id,
                    product_id=product.id,
                    product_name_snapshot=product.name,
                    relation_type="benefit",
                )
            ]
        )
        campaign_repo.set_current_version(campaign.id, version.id)
        session.commit()

        rows, total = campaign_repo.list(state="active", as_of=now)
        active = campaign_repo.active_for_product(product.id, as_of=now)

        assert total == 1
        assert rows[0][0].id == campaign.id
        assert len(active) == 1
        assert active[0].link.product_id == product.id

        dealer_repo = SqlAlchemyDealerPricingRepository(session)
        pricing = DealerPricing(
            id=uuid.uuid4(),
            product_id=product.id,
            cash_floor_price=Decimal("22000.00"),
            card_floor_price=Decimal("22500.00"),
        )
        dealer_repo.add(pricing)
        dealer_repo.add_history(
            DealerPricingHistory(
                id=uuid.uuid4(),
                product_id=product.id,
                old_cash_floor=None,
                new_cash_floor=Decimal("22000.00"),
                old_card_floor=None,
                new_card_floor=Decimal("22500.00"),
                changed_at=now,
            )
        )
        session.commit()

        assert dealer_repo.get(product.id) is not None
        history = dealer_repo.get_history(product.id)
        assert len(history) == 1
        assert history[0].new_cash_floor == Decimal("22000.00")
