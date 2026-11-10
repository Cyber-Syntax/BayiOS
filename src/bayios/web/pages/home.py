from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from bayios.application.reservations import list_home_reminders
from bayios.web.deps import UnitOfWorkDep
from bayios.web.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, uow: UnitOfWorkDep) -> HTMLResponse:
    reminders = list_home_reminders(uow, horizon_days=30, limit=8)
    return templates.TemplateResponse(
        request,
        "home.html",
        {"active_nav": "home", "reminders": reminders},
    )
