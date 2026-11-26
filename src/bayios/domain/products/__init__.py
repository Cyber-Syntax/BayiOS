from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from bayios.domain.naming import normalize_name

CENT = Decimal("0.01")


@dataclass(frozen=True)
class ActorContext:
    """Audit metadata identifying the client device and optional worker name."""

    device_name: str | None = None
    worker_name: str | None = None


def normalize_product_name(raw_name: str) -> str:
    """Return the canonical name used for exact product matching."""
    return normalize_name(raw_name)


def normalize_website_price(value: Decimal | None) -> Decimal | None:
    """Treat zero as "no Oliz price"; keep other prices unchanged."""
    if value is None or value == 0:
        return None
    return value


def calculate_oliz_discount(
    regular_price: Decimal | None, website_discounted_price: Decimal | None
) -> Decimal | None:
    """Return the positive Oliz discount (regular minus Oliz), else ``None``.

    The value is derived at read time and never persisted. A missing, zero or
    non-positive difference means there is no real Oliz discount to display.
    """
    oliz_price = normalize_website_price(website_discounted_price)
    if regular_price is None or oliz_price is None:
        return None
    discount = (regular_price - oliz_price).quantize(CENT, rounding=ROUND_HALF_UP)
    if discount <= 0:
        return None
    return discount


def normalize_category_name(raw_name: str) -> str:
    """Return the canonical name used for category matching (case/space insensitive)."""
    return normalize_name(raw_name)
