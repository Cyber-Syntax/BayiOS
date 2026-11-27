from __future__ import annotations

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_TURKISH_LOWER = str.maketrans({"I": "ı", "İ": "i"})
_TURKISH_UPPER = str.maketrans({"i": "İ", "ı": "I"})
# Brand/report abbreviations that must keep their all-caps form.
_UPPERCASE_TOKENS = frozenset({"BBVA", "HSBC", "TEB", "ING", "QNB", "TV", "LED", "HP"})


def normalize_name(raw_name: str) -> str:
    """Return the case/space-insensitive key used for exact name matching."""
    normalized = unicodedata.normalize("NFKC", raw_name).strip()
    normalized = _WHITESPACE.sub(" ", normalized)
    return normalized.translate(_TURKISH_LOWER).lower()


def _title_token(token: str) -> str:
    if any(char.isdigit() for char in token):
        return token
    letters = [char for char in token if char.isalpha()]
    if not letters:
        return token
    if token.upper() in _UPPERCASE_TOKENS:
        return token
    first = token[0].translate(_TURKISH_UPPER).upper()
    rest = token[1:].translate(_TURKISH_LOWER).lower()
    return first + rest


def canonical_display_name(raw_name: str, *, always_title: bool = False) -> str:
    """Return the canonical Turkish display form of a bank or category name.

    Comments, notes and product names are out of scope. Bank names are always
    normalised (short brand names); categories only when written entirely in
    upper or lower case, so mixed-case names are never mangled.
    """
    normalized = unicodedata.normalize("NFKC", raw_name).strip()
    normalized = _WHITESPACE.sub(" ", normalized)
    letters = [char for char in normalized if char.isalpha()]
    if not letters:
        return normalized
    uniform_case = all(char.isupper() for char in letters) or all(
        char.islower() for char in letters
    )
    if not always_title and not uniform_case:
        return normalized
    return " ".join(_title_token(token) for token in normalized.split(" "))
