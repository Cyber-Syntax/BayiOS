from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, File, Form, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from bayios.application.errors import NotFoundError, ValidationError
from bayios.application.settings import (
    create_banks_bulk,
    create_categories_bulk,
    delete_bank,
    delete_category,
    list_bank_overviews,
    list_category_overviews,
    merge_banks,
    merge_categories,
    preview_banks,
    preview_categories,
    rename_bank,
    rename_category,
    set_bank_active,
    update_bank_card_networks,
    update_category_group,
)
from bayios.application.settings.io import (
    export_banks_xlsx,
    export_categories_xlsx,
    import_banks_xlsx,
    import_categories_xlsx,
)
from bayios.web.deps import UnitOfWorkDep
from bayios.web.templating import templates

router = APIRouter(prefix="/settings", tags=["settings"])

XLSX_MEDIA = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@router.get("")
def settings_index() -> RedirectResponse:
    return RedirectResponse(url="/settings/banks", status_code=303)


@router.get("/banks", response_class=HTMLResponse)
def banks_page(
    request: Request,
    uow: UnitOfWorkDep,
    q: str | None = None,
) -> HTMLResponse:
    rows = list_bank_overviews(uow, q)
    return templates.TemplateResponse(
        request,
        "settings/banks.html",
        {
            "active_nav": "settings",
            "rows": rows,
            "all_rows": rows if not q else list_bank_overviews(uow),
            "q": q or "",
            "msg": request.query_params.get("msg"),
            "count": request.query_params.get("count"),
        },
    )


@router.post("/banks")
def create_bank_route(
    uow: UnitOfWorkDep,
    name: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    try:
        result = create_banks_bulk(uow, name or "")
    except (ValidationError, ValueError) as exc:
        return _redirect_error("/settings/banks", exc)
    return RedirectResponse(
        url=f"/settings/banks?{urlencode({'msg': 'added', 'count': result.created})}",
        status_code=303,
    )


@router.post("/banks/bulk-preview", response_class=HTMLResponse)
def bulk_banks_preview_route(
    request: Request,
    uow: UnitOfWorkDep,
    names: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    try:
        preview = preview_banks(uow, names or "")
    except (ValidationError, ValueError) as exc:
        return _redirect_error_response("/settings/banks", exc)
    return _render_bulk_preview(
        request,
        preview=preview,
        raw_text=names,
        action="/settings/banks/bulk",
        back_url="/settings/banks",
        title="Banka Toplu Ekleme Önizlemesi",
    )


@router.post("/banks/bulk")
def bulk_banks_route(
    uow: UnitOfWorkDep,
    names: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    try:
        result = create_banks_bulk(uow, names or "")
    except (ValidationError, ValueError) as exc:
        return _redirect_error("/settings/banks", exc)
    return RedirectResponse(
        url=f"/settings/banks?{urlencode({'msg': 'bulk', 'count': result.created})}",
        status_code=303,
    )


@router.post("/banks/{bank_id}/rename")
def rename_bank_route(
    bank_id: uuid.UUID,
    uow: UnitOfWorkDep,
    name: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    try:
        bank = rename_bank(uow, bank_id, name or "")
    except (NotFoundError, ValidationError, ValueError) as exc:
        return _redirect_error("/settings/banks", exc)
    return RedirectResponse(
        url=f"/settings/banks?{urlencode({'msg': 'renamed', 'count': bank.name})}",
        status_code=303,
    )


@router.post("/banks/{bank_id}/card-networks")
def bank_card_networks_route(
    bank_id: uuid.UUID,
    uow: UnitOfWorkDep,
    card_networks: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    try:
        bank = update_bank_card_networks(uow, bank_id, card_networks or "")
    except (NotFoundError, ValidationError) as exc:
        return _redirect_error("/settings/banks", exc)
    return RedirectResponse(
        url=f"/settings/banks?{urlencode({'msg': 'bank_networks', 'count': bank.name})}",
        status_code=303,
    )


@router.post("/banks/{bank_id}/active")
def bank_active_route(
    bank_id: uuid.UUID,
    uow: UnitOfWorkDep,
    active: Annotated[str, Form()],
) -> RedirectResponse:
    try:
        bank = set_bank_active(uow, bank_id, active == "1")
    except (NotFoundError, ValidationError) as exc:
        return _redirect_error("/settings/banks", exc)
    return RedirectResponse(
        url=f"/settings/banks?{urlencode({'msg': 'active', 'count': bank.name})}",
        status_code=303,
    )


@router.post("/banks/{bank_id}/merge")
def merge_bank_route(
    bank_id: uuid.UUID,
    uow: UnitOfWorkDep,
    target_id: Annotated[str, Form()],
) -> RedirectResponse:
    try:
        merge_banks(uow, bank_id, uuid.UUID(target_id))
    except (NotFoundError, ValidationError, ValueError) as exc:
        return _redirect_error("/settings/banks", exc)
    return RedirectResponse(
        url=f"/settings/banks?{urlencode({'msg': 'merged'})}",
        status_code=303,
    )


@router.post("/banks/{bank_id}/delete")
def delete_bank_route(
    bank_id: uuid.UUID,
    uow: UnitOfWorkDep,
    confirm: Annotated[str | None, Form()] = None,
    force: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    try:
        delete_bank(
            uow,
            bank_id,
            confirm=confirm == "1",
            force=force == "1",
        )
    except (NotFoundError, ValidationError) as exc:
        return _redirect_error("/settings/banks", exc)
    return RedirectResponse(
        url=f"/settings/banks?{urlencode({'msg': 'deleted'})}",
        status_code=303,
    )


@router.get("/banks/export.xlsx")
def export_banks_route(uow: UnitOfWorkDep) -> Response:
    return Response(
        content=export_banks_xlsx(uow),
        media_type=XLSX_MEDIA,
        headers={
            "Content-Disposition": "attachment; filename=bayios-bankalar.xlsx"
        },
    )


@router.post("/banks/import")
async def import_banks_route(
    request: Request,
    uow: UnitOfWorkDep,
    file: Annotated[UploadFile, File()],
) -> Response:
    content = await file.read()
    try:
        result = import_banks_xlsx(uow, content)
    except (ValidationError, ValueError) as exc:
        return _redirect_error("/settings/banks", exc)
    return RedirectResponse(
        url=f"/settings/banks?{urlencode({'msg': 'imported', 'created': result.created, 'updated': result.updated})}",
        status_code=303,
    )


@router.get("/categories", response_class=HTMLResponse)
def categories_page(
    request: Request,
    uow: UnitOfWorkDep,
    q: str | None = None,
) -> HTMLResponse:
    rows = list_category_overviews(uow, q)
    return templates.TemplateResponse(
        request,
        "settings/categories.html",
        {
            "active_nav": "settings",
            "rows": rows,
            "all_rows": rows if not q else list_category_overviews(uow),
            "q": q or "",
            "msg": request.query_params.get("msg"),
            "count": request.query_params.get("count"),
        },
    )


@router.post("/categories")
def create_category_route(
    uow: UnitOfWorkDep,
    name: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    try:
        result = create_categories_bulk(uow, name or "")
    except (ValidationError, ValueError) as exc:
        return _redirect_error("/settings/categories", exc)
    return RedirectResponse(
        url=f"/settings/categories?{urlencode({'msg': 'added', 'count': result.created})}",
        status_code=303,
    )


@router.post("/categories/bulk-preview", response_class=HTMLResponse)
def bulk_categories_preview_route(
    request: Request,
    uow: UnitOfWorkDep,
    names: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    try:
        preview = preview_categories(uow, names or "")
    except (ValidationError, ValueError) as exc:
        return _redirect_error_response("/settings/categories", exc)
    return _render_bulk_preview(
        request,
        preview=preview,
        raw_text=names,
        action="/settings/categories/bulk",
        back_url="/settings/categories",
        title="Kategori Toplu Ekleme Önizlemesi",
    )


@router.post("/categories/bulk")
def bulk_categories_route(
    uow: UnitOfWorkDep,
    names: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    try:
        result = create_categories_bulk(uow, names or "")
    except (ValidationError, ValueError) as exc:
        return _redirect_error("/settings/categories", exc)
    return RedirectResponse(
        url=f"/settings/categories?{urlencode({'msg': 'bulk', 'count': result.created})}",
        status_code=303,
    )


@router.post("/categories/{category_id}/rename")
def rename_category_route(
    category_id: uuid.UUID,
    uow: UnitOfWorkDep,
    name: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    try:
        category = rename_category(uow, category_id, name or "")
    except (NotFoundError, ValidationError, ValueError) as exc:
        return _redirect_error("/settings/categories", exc)
    return RedirectResponse(
        url=f"/settings/categories?{urlencode({'msg': 'renamed', 'count': category.name})}",
        status_code=303,
    )


@router.post("/categories/{category_id}/group")
def category_group_route(
    category_id: uuid.UUID,
    uow: UnitOfWorkDep,
    commission_group: Annotated[str, Form()],
) -> RedirectResponse:
    try:
        update_category_group(uow, category_id, commission_group)
    except (NotFoundError, ValidationError) as exc:
        return _redirect_error("/settings/categories", exc)
    return RedirectResponse(
        url=f"/settings/categories?{urlencode({'msg': 'group'})}",
        status_code=303,
    )


@router.post("/categories/{category_id}/merge")
def merge_category_route(
    category_id: uuid.UUID,
    uow: UnitOfWorkDep,
    target_id: Annotated[str, Form()],
) -> RedirectResponse:
    try:
        merge_categories(uow, category_id, uuid.UUID(target_id))
    except (NotFoundError, ValidationError, ValueError) as exc:
        return _redirect_error("/settings/categories", exc)
    return RedirectResponse(
        url=f"/settings/categories?{urlencode({'msg': 'merged'})}",
        status_code=303,
    )


@router.post("/categories/{category_id}/delete")
def delete_category_route(
    category_id: uuid.UUID,
    uow: UnitOfWorkDep,
    confirm: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    try:
        delete_category(uow, category_id, confirm=confirm == "1")
    except (NotFoundError, ValidationError) as exc:
        return _redirect_error("/settings/categories", exc)
    return RedirectResponse(
        url=f"/settings/categories?{urlencode({'msg': 'deleted'})}",
        status_code=303,
    )


@router.get("/categories/export.xlsx")
def export_categories_route(uow: UnitOfWorkDep) -> Response:
    return Response(
        content=export_categories_xlsx(uow),
        media_type=XLSX_MEDIA,
        headers={
            "Content-Disposition": "attachment; filename=bayios-kategoriler.xlsx"
        },
    )


@router.post("/categories/import")
async def import_categories_route(
    request: Request,
    uow: UnitOfWorkDep,
    file: Annotated[UploadFile, File()],
) -> Response:
    content = await file.read()
    try:
        result = import_categories_xlsx(uow, content)
    except (ValidationError, ValueError) as exc:
        return _redirect_error("/settings/categories", exc)
    return RedirectResponse(
        url=f"/settings/categories?{urlencode({'msg': 'imported', 'created': result.created, 'updated': result.updated})}",
        status_code=303,
    )


def _render_bulk_preview(
    request: Request,
    *,
    preview: object,
    raw_text: str,
    action: str,
    back_url: str,
    title: str,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "settings/bulk_preview.html",
        {
            "active_nav": "settings",
            "preview": preview,
            "raw_text": raw_text,
            "action": action,
            "back_url": back_url,
            "title": title,
        },
        status_code=200,
    )


def _redirect_error(path: str, exc: Exception) -> RedirectResponse:
    return RedirectResponse(
        url=f"{path}?{urlencode({'msg': f'error:{exc}'})}",
        status_code=303,
    )


def _redirect_error_response(path: str, exc: Exception) -> RedirectResponse:
    return _redirect_error(path, exc)
