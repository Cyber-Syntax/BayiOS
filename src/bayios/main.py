from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from bayios.bootstrap import ApplicationSettings, build_container
from bayios.logging_config import configure_logging
from bayios.web.api.health import router as health_router
from bayios.web.pages.campaigns import router as campaigns_router
from bayios.web.pages.commissions import router as commissions_router
from bayios.web.pages.home import router as home_router
from bayios.web.pages.imports import router as imports_router
from bayios.web.pages.imports_campaigns import router as imports_campaigns_router
from bayios.web.pages.imports_commissions import router as imports_commissions_router
from bayios.web.pages.imports_offers import router as imports_offers_router
from bayios.web.pages.imports_reservations import router as imports_reservations_router
from bayios.web.pages.offers import router as offers_router
from bayios.web.pages.products import router as products_router
from bayios.web.pages.reservations import router as reservations_router
from bayios.web.pages.stock import router as stock_router
from bayios.web.templating import STATIC_DIR

logger = logging.getLogger(__name__)


def create_app(settings: ApplicationSettings | None = None) -> FastAPI:
    settings = settings or ApplicationSettings()
    configure_logging(settings.log_level, settings.log_format)
    container = build_container(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # No eager DB connect: the app must come up even if Postgres is down,
        # so /health can report it instead of the process crashing.
        logger.info("BayiOS starting")
        try:
            yield
        finally:
            container.dispose()
            logger.info("BayiOS stopped")

    app = FastAPI(title="BayiOS", lifespan=lifespan)
    app.state.container = container
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(health_router)
    app.include_router(home_router)
    app.include_router(products_router)
    app.include_router(imports_router)
    app.include_router(imports_campaigns_router)
    app.include_router(imports_commissions_router)
    app.include_router(imports_offers_router)
    app.include_router(imports_reservations_router)
    app.include_router(campaigns_router)
    app.include_router(commissions_router)
    app.include_router(offers_router)
    app.include_router(stock_router)
    app.include_router(reservations_router)
    return app
