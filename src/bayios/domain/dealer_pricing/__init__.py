from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

MONEY_QUANTUM = Decimal("0.01")
ZERO = Decimal(0)
HUNDRED = Decimal(100)
DEFAULT_DEALER_DISCOUNT_PERCENT = Decimal("10.00")


def quantize_money(value: Decimal) -> Decimal:
    """Round a monetary value to two decimals using commercial rounding."""
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def validate_dealer_percent(value: Decimal) -> Decimal:
    if value < ZERO or value > HUNDRED:
        raise ValueError("Bayi indirimi oranı %0 ile %100 arasında olmalıdır.")
    return value


def validate_floor_price(value: Decimal | None) -> Decimal | None:
    if value is not None and value < ZERO:
        raise ValueError("Bayi taban fiyatı negatif olamaz.")
    return value


def validate_floor_prices(
    cash_floor_price: Decimal | None,
    card_floor_price: Decimal | None,
) -> tuple[Decimal | None, Decimal | None]:
    return (
        validate_floor_price(cash_floor_price),
        validate_floor_price(card_floor_price),
    )


@dataclass(frozen=True)
class DealerPricingValues:
    """Current product-specific cash and card floor prices."""

    cash_floor_price: Decimal | None = None
    card_floor_price: Decimal | None = None

    def __post_init__(self) -> None:
        validate_floor_prices(self.cash_floor_price, self.card_floor_price)


@dataclass(frozen=True)
class DealerDiscountSettingValues:
    """The global default dealer discount shown by the campaign guide."""

    default_percent: Decimal = DEFAULT_DEALER_DISCOUNT_PERCENT

    def __post_init__(self) -> None:
        validate_dealer_percent(self.default_percent)
