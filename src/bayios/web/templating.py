from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi.templating import Jinja2Templates

from bayios.web.navigation import NAV_ITEMS

WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"

templates = Jinja2Templates(directory=TEMPLATES_DIR)

TURKISH_MONTHS = (
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
)

try:  # Turkey has used a fixed UTC+3 offset since 2016.
    _ISTANBUL = ZoneInfo("Europe/Istanbul")
except ZoneInfoNotFoundError:  # pragma: no cover - Windows without tzdata
    _ISTANBUL = timezone(timedelta(hours=3), "Europe/Istanbul")


def _istanbul(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(_ISTANBUL)


def tr_date(value: date | datetime | None) -> str:
    """Turkish short date: 10.11.2026 (UTC values shown in Europe/Istanbul)."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = _istanbul(value)
    return f"{value.day:02d}.{value.month:02d}.{value.year}"


def tr_date_long(value: date | datetime | None) -> str:
    """Turkish long date with month name: 10 Kasım 2026."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = _istanbul(value)
    return f"{value.day} {TURKISH_MONTHS[value.month - 1]} {value.year}"


def tr_datetime(value: datetime | None) -> str:
    """Turkish date and time: 10.11.2026 14:35."""
    if value is None:
        return ""
    if not isinstance(value, datetime):
        return tr_date(value)
    return f"{tr_date(value)} {_istanbul(value).strftime('%H:%M')}"


def iso_date(value: date | datetime | None) -> str:
    """ISO date for HTML date inputs: 2026-11-10."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = _istanbul(value)
    return value.strftime("%Y-%m-%d")


def tr_money(value: Decimal | float | None) -> str:
    """Turkish money display: 23.399,10 (no currency suffix)."""
    if value is None:
        return "—"
    return (
        f"{Decimal(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )


def tr_percent(value: Decimal | float | None) -> str:
    """Turkish percentage display: 10,00 %."""
    if value is None:
        return "—"
    return f"{Decimal(value):.2f}".replace(".", ",") + " %"


def _asset_version() -> str:
    digest = hashlib.sha256()
    for path in sorted(STATIC_DIR.rglob("*")):
        if path.is_file():
            digest.update(path.read_bytes())
    return f"{version('bayios')}-{digest.hexdigest()[:12]}"


templates.env.filters.update(
    tr_date=tr_date,
    tr_date_long=tr_date_long,
    tr_datetime=tr_datetime,
    iso_date=iso_date,
    tr_money=tr_money,
    tr_percent=tr_percent,
)
templates.env.globals.update(nav_items=NAV_ITEMS, asset_version=_asset_version())
