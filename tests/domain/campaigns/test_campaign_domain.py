from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from bayios.domain.campaigns import (
    BasePriceType,
    CampaignContract,
    CampaignPriceInput,
    CampaignProductLink,
    CampaignState,
    CampaignType,
    DiscountType,
    ProductRelationType,
    campaign_scenarios,
    classify_campaign,
    is_same_contract,
    next_version_no,
)

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=60)


def _gift_contract(**overrides: object) -> CampaignContract:
    values: dict[str, object] = {
        "name": "Hediye Kampanyası",
        "campaign_type": CampaignType.GIFT,
        "starts_at": NOW,
        "ends_at": LATER,
        "base_price_type": BasePriceType.REGULAR,
        "discount_type": DiscountType.GIFT,
        "gift_description": "Buzdolabı hediye",
        "gift_optional": True,
        "gift_yes_base_price_type": BasePriceType.REGULAR,
        "gift_no_base_price_type": BasePriceType.WEBSITE_DISCOUNTED,
        "products": (
            CampaignProductLink(
                product_id="p1",
                product_name="Buzdolabı",
                relation_type=ProductRelationType.BENEFIT,
            ),
        ),
    }
    values.update(overrides)
    return CampaignContract(**values)  # type: ignore[arg-type]


def _prices(**overrides: object) -> CampaignPriceInput:
    values: dict[str, object] = {
        "regular_price": Decimal(25999),
        "website_discounted_price": Decimal(23999),
        "cash_floor_price": Decimal(22000),
        "card_floor_price": Decimal(22500),
    }
    values.update(overrides)
    return CampaignPriceInput(**values)  # type: ignore[arg-type]


def test_gift_scenarios_use_regular_and_website_bases() -> None:
    scenarios = campaign_scenarios(_gift_contract(), _prices(), Decimal(10))

    assert [scenario.final_price for scenario in scenarios] == [
        Decimal("23399.10"),
        Decimal("21599.10"),
    ]
    assert scenarios[0].gift_present is True
    assert scenarios[0].base_price_type is BasePriceType.REGULAR
    assert scenarios[1].gift_present is False
    assert scenarios[1].base_price_type is BasePriceType.WEBSITE_DISCOUNTED
    assert scenarios[0].cash_floor_price == Decimal("22000.00")
    assert scenarios[0].card_floor_price == Decimal("22500.00")


def test_missing_website_price_falls_back_to_regular() -> None:
    scenarios = campaign_scenarios(
        _gift_contract(),
        _prices(website_discounted_price=None),
        Decimal(10),
    )

    assert scenarios[1].final_price == Decimal("23399.10")
    assert scenarios[1].warning is not None
    assert "Website price" in scenarios[1].warning


def test_fixed_amount_and_special_price_scenarios() -> None:
    fixed = campaign_scenarios(
        _gift_contract(
            campaign_type=CampaignType.PRODUCT_DISCOUNT,
            discount_type=DiscountType.FIXED_AMOUNT,
            discount_value=Decimal(500),
            gift_description=None,
            gift_optional=False,
        ),
        _prices(),
    )
    special = campaign_scenarios(
        _gift_contract(
            campaign_type=CampaignType.PRODUCT_DISCOUNT,
            discount_type=DiscountType.SPECIAL_PRICE,
            discount_value=Decimal(24999),
            gift_description=None,
            gift_optional=False,
        ),
        _prices(),
    )

    assert fixed[0].final_price == Decimal("25499.00")
    assert special[0].final_price == Decimal("24999.00")
    assert special[0].discount_amount == Decimal("1000.00")


def test_coupon_and_info_only_are_informational() -> None:
    scenarios = campaign_scenarios(
        _gift_contract(
            campaign_type=CampaignType.COUPON,
            discount_type=DiscountType.INFO_ONLY,
            gift_description=None,
            gift_optional=False,
        ),
        _prices(),
    )

    assert scenarios[0].is_informational is True
    assert scenarios[0].final_price is None


def test_invalid_contracts_are_rejected() -> None:
    with pytest.raises(ValueError):
        _gift_contract(name="  ")
    with pytest.raises(ValueError):
        _gift_contract(ends_at=NOW - timedelta(days=1))
    with pytest.raises(ValueError):
        _gift_contract(
            campaign_type=CampaignType.PRODUCT_DISCOUNT,
            discount_type=DiscountType.PERCENT,
            discount_value=Decimal(101),
            gift_description=None,
            gift_optional=False,
        )
    with pytest.raises(ValueError):
        _gift_contract(
            campaign_type=CampaignType.PRODUCT_DISCOUNT,
            discount_type=DiscountType.FIXED_AMOUNT,
            discount_value=Decimal(-1),
            gift_description=None,
            gift_optional=False,
        )
    with pytest.raises(ValueError):
        _gift_contract(gift_description=None)
    with pytest.raises(ValueError):
        _gift_contract(
            products=(
                CampaignProductLink("p1", "Ürün", ProductRelationType.BENEFIT),
                CampaignProductLink("p1", "Ürün", ProductRelationType.BENEFIT),
            )
        )


def test_classify_campaign_states() -> None:
    assert (
        classify_campaign(
            starts_at=NOW,
            ends_at=LATER,
            archived=False,
            as_of=NOW,
        )
        is CampaignState.ACTIVE
    )
    assert (
        classify_campaign(
            starts_at=NOW + timedelta(days=1),
            ends_at=LATER,
            archived=False,
            as_of=NOW,
        )
        is CampaignState.SCHEDULED
    )
    assert (
        classify_campaign(
            starts_at=NOW - timedelta(days=10),
            ends_at=NOW - timedelta(days=1),
            archived=False,
            as_of=NOW,
        )
        is CampaignState.EXPIRED
    )
    assert (
        classify_campaign(
            starts_at=NOW,
            ends_at=LATER,
            archived=True,
            as_of=NOW,
        )
        is CampaignState.ARCHIVED
    )


def test_version_numbers_and_contract_comparison() -> None:
    contract = _gift_contract()
    same = _gift_contract()
    changed = _gift_contract(name="Başka")

    assert next_version_no(None) == 1
    assert next_version_no(3) == 4
    assert is_same_contract(contract, same) is True
    assert is_same_contract(contract, changed) is False


def test_price_input_and_dealer_percent_validation() -> None:
    with pytest.raises(ValueError):
        _prices(regular_price=Decimal(-1))
    with pytest.raises(ValueError):
        campaign_scenarios(_gift_contract(), _prices(), Decimal(101))
