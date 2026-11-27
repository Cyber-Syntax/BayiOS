from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from bayios.application.campaigns import list_campaigns
from bayios.application.offers import list_offers
from bayios.application.reservations import list_home_reminders, list_reservations
from bayios.domain.offers import OFFER_STATUS_LABELS
from bayios.web.deps import UnitOfWorkDep
from bayios.web.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, uow: UnitOfWorkDep) -> HTMLResponse:
    now = datetime.now(UTC)
    reminders = list_home_reminders(uow, now=now, horizon_days=30, limit=8)
    recent_offers, _ = list_offers(uow, limit=5)
    recent_reservations, _ = list_reservations(uow, now=now, limit=5)
    draft_offers = list_offers(uow, status="draft", limit=1)[1]
    presented_offers = list_offers(uow, status="presented", limit=1)[1]
    open_reservations = list_reservations(uow, status="open", now=now, limit=1)[1]
    overdue_reminders = list_reservations(uow, status="overdue", now=now, limit=1)[1]
    active_campaigns = list_campaigns(uow, state="active", now=now, limit=1)[1]

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "active_nav": "home",
            "today": now,
            "reminders": reminders,
            "recent_offers": recent_offers,
            "recent_reservations": recent_reservations,
            "open_offers": draft_offers + presented_offers,
            "open_reservations": open_reservations,
            "overdue_reminders": overdue_reminders,
            "active_campaigns": active_campaigns,
            "offer_status_labels": OFFER_STATUS_LABELS,
        },
    )
