from __future__ import annotations

import math
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from bayios.adapters.db.models.products import ProductCategory
from bayios.application.errors import ConflictError, NotFoundError, ValidationError
from bayios.application.inventory import (
    complete_stock_count_session,
    create_product_category,
    get_stock_count_session,
    get_stock_overview,
    list_categories,
    list_recent_stock_count_sessions,
    open_stock_count_session,
    refresh_stock_count_session,
    save_counted_quantities,
)
from bayios.application.inventory.io import export_stock_xlsx
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.web.deps import ActorDep, UnitOfWorkDep
from bayios.web.templating import templates

router = APIRouter(prefix="/stock", tags=["stock"])


def _optional_uuid(value: str | None) -> uuid.UUID | None:
    if not value or not value.strip():
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Geçersiz kategori") from exc


def _category_index(categories: Sequence[ProductCategory]) -> dict[uuid.UUID, str]:
    return {category.id: category.name for category in categories}


@router.get("", response_class=HTMLResponse)
def stock_index(
    request: Request,
    uow: UnitOfWorkDep,
    category_id: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query()] = 1,
    limit: Annotated[int, Query()] = 50,
) -> HTMLResponse:
    selected_category = _optional_uuid(category_id)
    page = max(1, page)
    limit = max(1, limit)
    offset = (page - 1) * limit

    categories = list_categories(uow)
    rows, total_count = get_stock_overview(
        uow, category_id=selected_category, query=q, limit=limit, offset=offset
    )
    total_pages = max(1, math.ceil(total_count / limit))
    if page > total_pages:
        page = total_pages
        offset = (page - 1) * limit
        rows, total_count = get_stock_overview(
            uow, category_id=selected_category, query=q, limit=limit, offset=offset
        )

    sessions = list_recent_stock_count_sessions(uow)
    open_sessions = [s for s in sessions if s.status in ("open", "review")]
    completed_sessions = [s for s in sessions if s.status == "completed"]
    category_names = _category_index(categories)

    context = {
        "active_nav": "stock",
        "categories": categories,
        "selected_category": selected_category,
        "category_names": category_names,
        "rows": rows,
        "sessions": sessions,
        "open_sessions": open_sessions,
        "completed_sessions": completed_sessions,
        "q": q or "",
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "total_count": total_count,
    }

    if request.headers.get("HX-Request") and not request.headers.get("HX-Boosted"):
        return templates.TemplateResponse(request, "stock/_results.html", context)

    return templates.TemplateResponse(request, "stock/index.html", context)


@router.post("/categories")
def create_category_route(
    uow: UnitOfWorkDep,
    name: Annotated[str, Form()],
) -> Response:
    try:
        create_product_category(uow, name)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url="/stock?msg=category_created", status_code=303)


@router.post("/sessions")
def open_session_route(
    uow: UnitOfWorkDep,
    actor: ActorDep,
    category_id: Annotated[str | None, Form()] = None,
    note: Annotated[str | None, Form()] = None,
) -> Response:
    try:
        view = open_stock_count_session(
            uow,
            category_id=_optional_uuid(category_id),
            actor=actor,
            note=note,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/stock/sessions/{view.id}", status_code=303)


@router.get("/sessions/{session_id}", response_class=HTMLResponse)
def session_page(
    request: Request,
    session_id: uuid.UUID,
    uow: UnitOfWorkDep,
    page: Annotated[int, Query()] = 1,
    limit: Annotated[int, Query()] = 50,
) -> HTMLResponse:
    return _render_session(request, uow, session_id, page=page, limit=limit)


@router.post("/sessions/{session_id}/count")
async def save_count_route(
    request: Request,
    session_id: uuid.UUID,
    uow: UnitOfWorkDep,
) -> Response:
    form = await request.form()
    counted: dict[uuid.UUID, int | None] = {}
    for key, value in form.items():
        if not key.startswith("counted_"):
            continue
        try:
            product_id = uuid.UUID(key.removeprefix("counted_"))
        except ValueError:
            continue
        text = str(value).strip()
        try:
            counted[product_id] = int(text) if text else None
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="Sayılan miktar tam sayı olmalıdır."
            ) from exc
    try:
        save_counted_quantities(uow, session_id, counted)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        url=f"/stock/sessions/{session_id}?msg=counts_saved", status_code=303
    )


@router.post("/sessions/{session_id}/refresh")
def refresh_session_route(
    session_id: uuid.UUID,
    uow: UnitOfWorkDep,
) -> Response:
    try:
        refresh_stock_count_session(uow, session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        url=f"/stock/sessions/{session_id}?msg=refreshed", status_code=303
    )


@router.post("/sessions/{session_id}/complete")
def complete_session_route(
    request: Request,
    session_id: uuid.UUID,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    acknowledge_differences: Annotated[str | None, Form()] = None,
) -> Response:
    try:
        complete_stock_count_session(
            uow,
            session_id,
            actor=actor,
            acknowledge_differences=acknowledge_differences == "on",
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        return _render_session(request, uow, session_id, error=str(exc), status_code=409)
    except ValidationError as exc:
        return _render_session(request, uow, session_id, error=str(exc), status_code=400)
    return RedirectResponse(
        url=f"/stock/sessions/{session_id}?msg=completed", status_code=303
    )


@router.get("/export/xlsx")
def export_stock_route(
    uow: UnitOfWorkDep,
    category_id: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> Response:
    content = export_stock_xlsx(
        uow, category_id=_optional_uuid(category_id), query=q
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=bayios-stok.xlsx"},
    )


@router.get("/print", response_class=HTMLResponse)
def print_count_list(
    request: Request,
    uow: UnitOfWorkDep,
    category_id: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    selected_category = _optional_uuid(category_id)
    categories = list_categories(uow)
    category_names = _category_index(categories)
    rows, _ = get_stock_overview(uow, category_id=selected_category)

    return templates.TemplateResponse(
        request,
        "stock/print.html",
        {
            "active_nav": "stock",
            "rows": rows,
            "category_name": category_names.get(selected_category)
            if selected_category
            else "Tüm Ürünler",
            "generated_at": datetime.now(UTC),
        },
    )


def _render_session(
    request: Request,
    uow: UnitOfWork,
    session_id: uuid.UUID,
    error: str | None = None,
    status_code: int = 200,
    page: int = 1,
    limit: int = 50,
) -> HTMLResponse:
    view = get_stock_count_session(uow, session_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Sayım oturumu bulunamadı.")

    page = max(1, page)
    limit = max(1, limit)
    total_items = len(view.items)
    total_pages = max(1, math.ceil(total_items / limit))
    page = min(page, total_pages)
    offset = (page - 1) * limit
    page_items = view.items[offset : offset + limit]

    return templates.TemplateResponse(
        request,
        "stock/session.html",
        {
            "active_nav": "stock",
            "session": view,
            "page_items": page_items,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "total_items": total_items,
            "error": error,
        },
        status_code=status_code,
    )
