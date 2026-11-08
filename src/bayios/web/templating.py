from __future__ import annotations

import hashlib
from importlib.metadata import version
from pathlib import Path

from fastapi.templating import Jinja2Templates

from bayios.web.navigation import NAV_ITEMS

WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _asset_version() -> str:
    digest = hashlib.sha256()
    for path in sorted(STATIC_DIR.rglob("*")):
        if path.is_file():
            digest.update(path.read_bytes())
    return f"{version('bayios')}-{digest.hexdigest()[:12]}"


templates.env.globals.update(nav_items=NAV_ITEMS, asset_version=_asset_version())
