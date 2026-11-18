from __future__ import annotations

from dataclasses import dataclass

from bayios.domain.naming import normalize_name


@dataclass(frozen=True)
class ActorContext:
    """Audit metadata identifying the client device and optional worker name."""

    device_name: str | None = None
    worker_name: str | None = None


def normalize_product_name(raw_name: str) -> str:
    """Return the canonical name used for exact product matching."""
    return normalize_name(raw_name)


def normalize_category_name(raw_name: str) -> str:
    """Return the canonical name used for category matching (case/space insensitive)."""
    return normalize_name(raw_name)
