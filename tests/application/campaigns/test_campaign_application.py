from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from bayios.adapters.db.models.campaigns import DealerDiscountSetting, DealerPricing
from bayios.adapters.db.models.products import Product
from bayios.application.campaigns import (
    CampaignInput,
    CampaignProductInput,
    archive_campaign,
    create_campaign,
    get_campaign_detail,
    list_active_campaigns_for_product,
    list_campaigns,
    update_campaign,
)
from bayios.application.errors import ValidationError
from bayios.domain.campaigns import (
    BasePriceType,
    CampaignType,
    DiscountType,
    ProductRelationType,
)
from tests.fakes import FakeUnitOfWork

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
END = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)


def _product() -> Product:
    return Product(
        id=uuid.uuid4(),
        name="Buzdolabı",
        name_normalized="buzdolabı",
        regular_price=Decimal(25999),
        website_discounted_price=Decimal(23999),
        physical_stock=1,
    )


def _input(
    product_id: uuid.UUID, **overrides: object
) -> CampaignInput:
    values: dict[str, object] = {
        "name": "Hediye Kampanyası",
        "campaign_type": CampaignType.GIFT,
        "starts_at": NOW,
        "ends_at": END,
        "base_price_type": BasePriceType.REGULAR,
        "discount_type": DiscountType.GIFT,
        "gift_description": "Buzdolabı hediye",
        "gift_optional": True,
        "gift_yes_base_price_type": BasePriceType.REGULAR,
        "gift_no_base_price_type": BasePriceType.WEBSITE_DISCOUNTED,
        "products": (
            CampaignProductInput(product_id, ProductRelationType.BENEFIT),
        ),
    }
    values.update(overrides)
    return CampaignInput(**values)  # type: ignore[arg-type]


@pytest.fixture
def setup() -> tuple[FakeUnitOfWork, Product]:
    uow = FakeUnitOfWork()
    product = _product()
    uow.products.add(product)
    uow.dealer_pricing.add(
        DealerPricing(
            id=uuid.uuid4(),
            product_id=product.id,
            cash_floor_price=Decimal(22000),
            card_floor_price=Decimal(22500),
        )
    )
    return uow, product


def test_create_campaign_builds_v1_and_gift_scenarios(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup

    campaign_id = create_campaign(uow, _input(product.id))
    detail = get_campaign_detail(uow, campaign_id, now=NOW)

    assert detail is not None
    assert detail.current_version.version_no == 1
    assert len(detail.versions) == 1
    assert detail.selected_product_name == product.name
    assert detail.scenarios[0].final_price == Decimal("23399.10")
    assert detail.scenarios[1].final_price == Decimal("21599.10")
    assert detail.scenarios[0].cash_floor_price == Decimal("22000.00")
    assert detail.scenarios[0].card_floor_price == Decimal("22500.00")

    items, total = list_campaigns(uow, state="active", now=NOW)
    assert total == 1
    assert items[0].name == "Hediye Kampanyası"
    assert items[0].state == "active"
    assert items[0].product_count == 1


def test_update_without_changes_keeps_single_version(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup
    campaign_id = create_campaign(uow, _input(product.id))

    update_campaign(uow, campaign_id, _input(product.id))
    detail = get_campaign_detail(uow, campaign_id, now=NOW)

    assert detail is not None
    assert len(detail.versions) == 1


def test_update_creates_new_version_and_preserves_old(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup
    campaign_id = create_campaign(uow, _input(product.id))

    update_campaign(uow, campaign_id, _input(product.id, name="Yeni Ad"))
    detail = get_campaign_detail(uow, campaign_id, now=NOW)

    assert detail is not None
    assert detail.current_version.name == "Yeni Ad"
    assert detail.current_version.version_no == 2
    assert len(detail.versions) == 2
    assert detail.versions[1].name == "Hediye Kampanyası"


def test_archive_moves_campaign_to_history(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup
    campaign_id = create_campaign(uow, _input(product.id))

    archive_campaign(uow, campaign_id, archived=True)

    active, active_total = list_campaigns(uow, state="active", now=NOW)
    history, history_total = list_campaigns(uow, state="history", now=NOW)

    assert active_total == 0
    assert active == ()
    assert history_total == 1
    assert history[0].state == "archived"


def test_active_campaigns_for_product_use_floor_prices_separately(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup
    create_campaign(uow, _input(product.id))

    views = list_active_campaigns_for_product(uow, product.id, now=NOW)

    assert len(views) == 1
    assert views[0].scenarios[0].final_price == Decimal("23399.10")
    assert views[0].scenarios[0].cash_floor_price == Decimal("22000.00")
    assert views[0].relation_label == "Fayda ürünü"


def test_missing_product_is_rejected(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, _ = setup

    with pytest.raises(ValidationError, match="bulunamadı"):
        create_campaign(uow, _input(uuid.uuid4()))


def test_campaign_validation_errors_are_turkish(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup

    with pytest.raises(ValidationError, match="Hediye indirimi değer almaz"):
        create_campaign(
            uow, _input(product.id, discount_value=Decimal(5))
        )
    with pytest.raises(
        ValidationError,
        match="Hediye kampanyalarında hediye açıklaması zorunludur",
    ):
        create_campaign(
            uow,
            _input(
                product.id,
                gift_description=None,
                gift_optional=False,
            ),
        )


def test_default_dealer_percent_is_used_and_can_be_overridden(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup
    uow.dealer_pricing.setting = DealerDiscountSetting(
        id=uuid.uuid4(), default_percent=Decimal("15.00")
    )
    campaign_id = create_campaign(uow, _input(product.id))

    detail = get_campaign_detail(uow, campaign_id, now=NOW)
    overridden = get_campaign_detail(
        uow, campaign_id, dealer_percent=Decimal(10), now=NOW
    )

    assert detail is not None
    assert detail.dealer_percent == Decimal("15.00")
    assert detail.scenarios[0].final_price == Decimal("22099.15")
    assert overridden is not None
    assert overridden.scenarios[0].final_price == Decimal("23399.10")


def test_expired_campaign_is_not_active_but_in_history(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup
    create_campaign(
        uow,
        _input(
            product.id,
            starts_at=NOW - timedelta(days=60),
            ends_at=NOW - timedelta(days=30),
        ),
    )

    active, active_total = list_campaigns(uow, state="active", now=NOW)
    history, history_total = list_campaigns(uow, state="history", now=NOW)

    assert active_total == 0
    assert active == ()
    assert history_total == 1
    assert history[0].state == "expired"


def test_scheduled_campaign_is_upcoming_in_active_list(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup
    create_campaign(
        uow,
        _input(
            product.id,
            starts_at=NOW + timedelta(days=10),
            ends_at=NOW + timedelta(days=20),
        ),
    )

    active, total = list_campaigns(uow, state="active", now=NOW)

    assert total == 1
    assert active[0].state == "scheduled"
    assert active[0].state_label == "Yaklaşan"


def test_list_filters_by_query_type_and_date(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup
    create_campaign(
        uow,
        _input(product.id, ends_at=NOW + timedelta(days=5)),
    )
    create_campaign(
        uow,
        _input(
            product.id,
            name="Kış İndirimi",
            campaign_type=CampaignType.PRODUCT_DISCOUNT,
            discount_type=DiscountType.PERCENT,
            discount_value=Decimal(10),
            gift_description=None,
            gift_optional=False,
            gift_yes_base_price_type=None,
            gift_no_base_price_type=None,
            starts_at=NOW + timedelta(days=10),
            ends_at=NOW + timedelta(days=20),
        ),
    )

    by_query, query_total = list_campaigns(uow, query="Kış", now=NOW)
    by_type, type_total = list_campaigns(
        uow, campaign_type=CampaignType.PRODUCT_DISCOUNT, now=NOW
    )
    by_from, from_total = list_campaigns(
        uow, date_from=NOW + timedelta(days=7), now=NOW
    )
    by_to, to_total = list_campaigns(
        uow, date_to=NOW + timedelta(days=7), now=NOW
    )

    assert query_total == 1
    assert by_query[0].name == "Kış İndirimi"
    assert type_total == 1
    assert by_type[0].name == "Kış İndirimi"
    assert from_total == 1
    assert by_from[0].name == "Kış İndirimi"
    assert to_total == 1
    assert by_to[0].name == "Hediye Kampanyası"


def test_product_without_website_price_uses_regular(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, _ = setup
    product = Product(
        id=uuid.uuid4(),
        name="Fırın",
        name_normalized="fırın",
        regular_price=Decimal(25999),
        website_discounted_price=None,
        physical_stock=1,
    )
    uow.products.add(product)
    campaign_id = create_campaign(uow, _input(product.id))

    detail = get_campaign_detail(uow, campaign_id, now=NOW)

    assert detail is not None
    assert detail.scenarios[1].final_price == Decimal("23399.10")
    assert detail.scenarios[1].warning is not None
    assert "Oliz fiyatı" in detail.scenarios[1].warning


def test_invalid_dealer_percent_override_is_rejected(
    setup: tuple[FakeUnitOfWork, Product],
) -> None:
    uow, product = setup
    campaign_id = create_campaign(uow, _input(product.id))

    with pytest.raises(ValidationError, match="%0"):
        get_campaign_detail(
            uow, campaign_id, dealer_percent=Decimal(101), now=NOW
        )
