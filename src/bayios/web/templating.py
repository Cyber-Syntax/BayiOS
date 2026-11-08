from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

from fastapi.templating import Jinja2Templates

from bayios.web.navigation import NAV_ITEMS

WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals.update(nav_items=NAV_ITEMS, asset_version=version("bayios"))
