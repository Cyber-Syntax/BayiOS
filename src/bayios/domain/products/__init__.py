import re
import unicodedata


_WHITESPACE = re.compile(r"\s+")


def normalize_product_name(raw_name: str) -> str:
    """Return the canonical name used for exact product matching."""
    normalized = unicodedata.normalize("NFKC", raw_name).strip()
    normalized = _WHITESPACE.sub(" ", normalized)
    return normalized.translate(str.maketrans({"I": "ı", "İ": "i"})).lower()
