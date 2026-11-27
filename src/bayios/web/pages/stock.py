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
    add_stock_count_line,
    cancel_stock_count_session,
    complete_stock_count_session,
    get_stock_count_session,
    get_stock_overview,
    list_categories,
    list_recent_stock_count_sessions,
    open_stock_count_session,
    refresh_stock_count_session,
    save_and_complete_stock_count,
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


def _parse_counted(form_items) -> dict[uuid.UUID, int | None]:
    counted: dict[uuid.UUID, int | None] = {}
    for key, value in form_items:
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
    return counted


def _is_htmx(request: Request) -> bool:
    return bool(request.headers.get("HX-Request")) and not request.headers.get(
        "HX-Boosted"
    )


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
    cancelled_sessions = [s for s in sessions if s.status == "cancelled"]
    history_sessions = sorted(
        [*completed_sessions, *cancelled_sessions],
        key=lambda session: session.started_at,
        reverse=True,
    )
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
        "cancelled_sessions": cancelled_sessions,
        "history_sessions": history_sessions,
        "q": q or "",
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "total_count": total_count,
    }

    if _is_htmx(request):
        return templates.TemplateResponse(request, "stock/_results.html", context)

    return templates.TemplateResponse(request, "stock/index.html", context)


@router.post("/sessions")
def open_session_route(
    uow: UnitOfWorkDep,
    actor: ActorDep,
    category_id: Annotated[str | None, Form()] = None,
    note: Annotated[str | None, Form()] = None,
    mode: Annotated[str, Form()] = "category",
) -> Response:
    try:
        view = open_stock_count_session(
            uow,
            category_id=_optional_uuid(category_id),
            actor=actor,
            note=note,
            mode=mode,
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


@router.get("/sessions/{session_id}/lookup", response_class=HTMLResponse)
def lookup_products_route(
    request: Request,
    session_id: uuid.UUID,
    uow: UnitOfWorkDep,
    q: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    view = get_stock_count_session(uow, session_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Sayım oturumu bulunamadı.")
    if view.mode != "quick":
        raise HTTPException(status_code=400, detail="Arama yalnızca hızlı sayımda kullanılır.")

    categories = list_categories(uow)
    category_names = _category_index(categories)
    rows, _ = get_stock_overview(
        uow,
        category_id=view.category_id,
        query=q,
        limit=8,
    )
    existing = {item.product_id for item in view.items}
    return templates.TemplateResponse(
        request,
        "stock/_lookup.html",
        {
            "session": view,
            "rows": rows,
            "existing_ids": existing,
            "category_names": category_names,
            "q": q or "",
        },
    )


@router.post("/sessions/{session_id}/items")
def add_line_route(
    request: Request,
    session_id: uuid.UUID,
    uow: UnitOfWorkDep,
    product_id: Annotated[str, Form()],
) -> Response:
    try:
        view = add_stock_count_line(uow, session_id, uuid.UUID(product_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Geçersiz ürün") from exc

    if _is_htmx(request):
        return templates.TemplateResponse(
            request,
            "stock/_quick_lines.html",
            {
                "session": view,
                "page_items": view.items,
                "total_items": len(view.items),
            },
        )
    return RedirectResponse(url=f"/stock/sessions/{session_id}", status_code=303)


@router.post("/sessions/{session_id}/count")
async def save_count_route(
    request: Request,
    session_id: uuid.UUID,
    uow: UnitOfWorkDep,
) -> Response:
    form = await request.form()
    counted = _parse_counted(form.multi_items())
    try:
        save_counted_quantities(uow, session_id, counted)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        url=f"/stock/sessions/{session_id}?msg=draft_saved", status_code=303
    )


@router.post("/sessions/{session_id}/save")
async def save_session_route(
    request: Request,
    session_id: uuid.UUID,
    uow: UnitOfWorkDep,
    actor: ActorDep,
) -> Response:
    form = await request.form()
    counted = _parse_counted(form.multi_items())
    try:
        save_and_complete_stock_count(uow, session_id, counted, actor=actor)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        return _render_session(request, uow, session_id, error=str(exc), status_code=409)
    except ValidationError as exc:
        return _render_session(request, uow, session_id, error=str(exc), status_code=400)
    return RedirectResponse(
        url=f"/stock/sessions/{session_id}?msg=saved", status_code=303
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
) -> Response:
    try:
        complete_stock_count_session(uow, session_id, actor=actor)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        return _render_session(request, uow, session_id, error=str(exc), status_code=409)
    except ValidationError as exc:
        return _render_session(request, uow, session_id, error=str(exc), status_code=400)
    return RedirectResponse(
        url=f"/stock/sessions/{session_id}?msg=saved", status_code=303
    )


@router.post("/sessions/{session_id}/cancel")
def cancel_session_route(
    request: Request,
    session_id: uuid.UUID,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    reason: Annotated[str | None, Form()] = None,
) -> Response:
    try:
        cancel_stock_count_session(uow, session_id, actor=actor, reason=reason)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        return _render_session(request, uow, session_id, error=str(exc), status_code=409)
    except ValidationError as exc:
        return _render_session(request, uow, session_id, error=str(exc), status_code=400)
    return RedirectResponse(
        url=f"/stock/sessions/{session_id}?msg=cancelled", status_code=303
    )


@router.get("/export/xlsx")
def export_stock_route(
    uow: UnitOfWorkDep,
    category_id: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    in_stock: Annotated[bool, Query()] = False,
) -> Response:
    content = export_stock_xlsx(
        uow,
        category_id=_optional_uuid(category_id),
        query=q,
        only_in_stock=in_stock,
    )
    filename = "bayios-stok-stokta.xlsx" if in_stock else "bayios-stok.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/print", response_class=HTMLResponse)
def print_count_list(
    request: Request,
    uow: UnitOfWorkDep,
    category_id: Annotated[str | None, Query()] = None,
    reserved_only: Annotated[bool, Query()] = False,
    in_stock: Annotated[bool, Query()] = False,
) -> HTMLResponse:
    selected_category = _optional_uuid(category_id)
    categories = list_categories(uow)
    category_names = _category_index(categories)
    rows, _ = get_stock_overview(
        uow,
        category_id=selected_category,
        limit=10_000,
        only_in_stock=in_stock,
    )
    if reserved_only:
        rows = tuple(row for row in rows if row.summary.open_reservation > 0)

    grouped: dict[str, list] = {}
    for row in rows:
        name = category_names.get(row.product.category_id, "Kategorisiz")
        grouped.setdefault(name, []).append(row)
    groups = [
        {"name": name, "rows": grouped[name]}
        for name in sorted(grouped)
    ]

    category_name = (
        category_names.get(selected_category)
        if selected_category
        else "Tüm Kategoriler"
    )
    return templates.TemplateResponse(
        request,
        "stock/print.html",
        {
            "active_nav": "stock",
            "groups": groups,
            "selected_category": selected_category,
            "category_name": category_name,
            "reserved_only": reserved_only,
            "in_stock": in_stock,
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
    if view.mode == "quick":
        page = 1
        total_pages = 1
        page_items = view.items
    else:
        total_pages = max(1, math.ceil(total_items / limit))
        page = min(page, total_pages)
        offset = (page - 1) * limit
        page_items = view.items[offset : offset + limit]

    context = {
        "active_nav": "stock",
        "session": view,
        "page_items": page_items,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "total_items": total_items,
        "error": error,
    }
    if _is_htmx(request):
        return templates.TemplateResponse(
            request, "stock/_quick_lines.html", context, status_code=status_code
        )
    return templates.TemplateResponse(
        request, "stock/session.html", context, status_code=status_code
    )
