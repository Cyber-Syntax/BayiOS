from __future__ import annotations

from decimal import Decimal

import pytest

from bayios.domain.dealer_pricing import (
    DEFAULT_DEALER_DISCOUNT_PERCENT,
    DealerDiscountSettingValues,
    DealerPricingValues,
    quantize_money,
    validate_dealer_percent,
    validate_floor_price,
    validate_floor_prices,
)


def test_default_dealer_discount_is_ten_percent() -> None:
    assert DEFAULT_DEALER_DISCOUNT_PERCENT == Decimal("10.00")
    assert DealerDiscountSettingValues().default_percent == Decimal("10.00")
    assert (
        DealerDiscountSettingValues(default_percent=Decimal(15)).default_percent
        == Decimal(15)
    )


def test_dealer_percent_range() -> None:
    assert validate_dealer_percent(Decimal(0)) == Decimal(0)
    assert validate_dealer_percent(Decimal(100)) == Decimal(100)
    with pytest.raises(ValueError):
        validate_dealer_percent(Decimal(-1))
    with pytest.raises(ValueError):
        validate_dealer_percent(Decimal(101))
    with pytest.raises(ValueError):
        DealerDiscountSettingValues(default_percent=Decimal(101))


def test_floor_price_validation() -> None:
    assert validate_floor_price(None) is None
    assert validate_floor_price(Decimal(0)) == Decimal(0)
    assert validate_floor_prices(Decimal(1), None) == (Decimal(1), None)
    with pytest.raises(ValueError):
        validate_floor_price(Decimal("-0.01"))
    with pytest.raises(ValueError):
        DealerPricingValues(cash_floor_price=Decimal(-1))


def test_money_rounding_uses_half_up() -> None:
    assert quantize_money(Decimal("23399.105")) == Decimal("23399.11")
    assert quantize_money(Decimal("23399.104")) == Decimal("23399.10")
    assert quantize_money(Decimal(23399)) == Decimal("23399.00")
