from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from bayios.web.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "home.html", {"active_nav": "home"})
