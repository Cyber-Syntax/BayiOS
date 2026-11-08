from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class ActorContext:
    """Audit metadata identifying the client device and optional worker name."""

    device_name: str | None = None
    worker_name: str | None = None


def normalize_product_name(raw_name: str) -> str:
    """Return the canonical name used for exact product matching."""
    normalized = unicodedata.normalize("NFKC", raw_name).strip()
    normalized = _WHITESPACE.sub(" ", normalized)
    return normalized.translate(str.maketrans({"I": "ı", "İ": "i"})).lower()
