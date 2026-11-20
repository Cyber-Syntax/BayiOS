from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bayios.domain.naming import normalize_name


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


def normalize_category_name(raw_name: str) -> str:
    """Return the canonical name used for category matching (case/space insensitive)."""
    return normalize_name(raw_name)
