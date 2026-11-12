from __future__ import annotations

import base64
import json
import uuid
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, File, Form, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from bayios.application.commissions.io import (
    commission_limits_template,
    commission_rates_template,
)
from bayios.application.imports.commissions import (
    commit_commission_limits,
    commit_commission_rates,
    preview_commission_limits,
    preview_commission_rates,
)
from bayios.web.deps import ActorDep, UnitOfWorkDep
from bayios.web.templating import templates

router = APIRouter(prefix="/imports/commissions", tags=["imports"])

RATE_HELP = (
    "Excel (.xlsx) dosyası yükleyin. Dönem YYYY-MM biçiminde olmalıdır.",
    "Dönem yoksa taslak dönem otomatik oluşturulur; arşivli dönem reddedilir.",
    "POS/Ödero için banka ve ürün grubu zorunludur; Chippin'de banka boş olmalıdır.",
    "Ödero bandı yalnızca Ödero kanalında kullanılır.",
    "Mevcut oranlar güncellenir; dosyada olmayan satırlar silinmez.",
)
LIMIT_HELP = (
    "Excel (.xlsx) dosyası yükleyin. Dönem YYYY-MM biçiminde olmalıdır.",
    "Dönem yoksa taslak dönem otomatik oluşturulur; arşivli dönem reddedilir.",
    "Limit en az bir kapsam alanı içermelidir: kanal, banka, ürün grubu veya kart tipi.",
    "Chippin limitinde banka boş olmalıdır.",
    "Mevcut limitler güncellenir; dosyada olmayan satırlar silinmez.",
)


@router.get("/rates", response_class=HTMLResponse)
def rates_upload_page(request: Request) -> HTMLResponse:
    return _upload(request, kind="rates")


@router.get("/limits", response_class=HTMLResponse)
def limits_upload_page(request: Request) -> HTMLResponse:
    return _upload(request, kind="limits")


@router.get("/rates/template")
def rates_template() -> Response:
    return _template_response(
        commission_rates_template(), "bayios-sablon-komisyon-oranlari.xlsx"
    )


@router.get("/limits/template")
def limits_template() -> Response:
    return _template_response(
        commission_limits_template(), "bayios-sablon-taksit-limitleri.xlsx"
    )


@router.post("/rates/preview", response_class=HTMLResponse)
async def rates_preview(
    request: Request,
    uow: UnitOfWorkDep,
    file: Annotated[UploadFile, File()],
) -> HTMLResponse:
    return await _preview(request, uow, file, kind="rates")


@router.post("/limits/preview", response_class=HTMLResponse)
async def limits_preview(
    request: Request,
    uow: UnitOfWorkDep,
    file: Annotated[UploadFile, File()],
) -> HTMLResponse:
    return await _preview(request, uow, file, kind="limits")


@router.post("/rates/commit")
async def rates_commit(
    request: Request,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    file_name: Annotated[str, Form()],
    file_type: Annotated[str, Form()],
    source_b64: Annotated[str, Form()],
    import_token: Annotated[str | None, Form()] = None,
) -> Response:
    return await _commit(
        request, uow, actor, file_name, file_type, source_b64, import_token, kind="rates"
    )


@router.post("/limits/commit")
async def limits_commit(
    request: Request,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    file_name: Annotated[str, Form()],
    file_type: Annotated[str, Form()],
    source_b64: Annotated[str, Form()],
    import_token: Annotated[str | None, Form()] = None,
) -> Response:
    return await _commit(
        request, uow, actor, file_name, file_type, source_b64, import_token, kind="limits"
    )


async def _preview(
    request: Request, uow: UnitOfWorkDep, file: UploadFile, *, kind: str
) -> HTMLResponse:
    if not file.filename:
        return _upload(request, kind=kind, error="Lütfen bir dosya seçin.")
    if not file.filename.lower().endswith(".xlsx"):
        return _upload(
            request, kind=kind, error="Yalnızca .xlsx uzantılı dosyalar desteklenir."
        )
    content = await file.read()
    if not content:
        return _upload(request, kind=kind, error="Yüklenen dosya boş.")
    try:
        preview = (
            preview_commission_rates(uow, content)
            if kind == "rates"
            else preview_commission_limits(uow, content)
        )
    except Exception as exc:  # noqa: BLE001
        return _upload(request, kind=kind, error=str(exc))
    return templates.TemplateResponse(
        request,
        "imports/generic_preview.html",
        {
            "active_nav": "commissions",
            "title": preview.title,
            "file_name": file.filename,
            "file_type": "xlsx",
            "preview": preview,
            "source_b64": base64.b64encode(content).decode("ascii"),
            "import_token": uuid.uuid4().hex,
            "commit_action": f"/imports/commissions/{kind}/commit",
            "back_url": f"/imports/commissions/{kind}",
        },
    )


async def _commit(
    request: Request,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    file_name: str,
    file_type: str,
    source_b64: str,
    import_token: str | None,
    *,
    kind: str,
) -> Response:
    try:
        source = base64.b64decode(source_b64.encode("ascii"))
    except Exception:  # noqa: BLE001
        return _upload(request, kind=kind, error="Geçersiz dosya verisi.")
    form = await request.form()
    try:
        decisions = json.loads(str(form.get("decisions_json") or "{}"))
    except json.JSONDecodeError:
        return _upload(request, kind=kind, error="Geçersiz karar verisi.")
    try:
        commit = (
            commit_commission_rates if kind == "rates" else commit_commission_limits
        )
        result = commit(
            uow,
            file_name=file_name,
            file_type=file_type,
            source=source,
            decisions=decisions if isinstance(decisions, dict) else {},
            actor=actor,
            commit_token=str(import_token) if import_token else None,
        )
    except Exception as exc:  # noqa: BLE001
        return _upload(request, kind=kind, error=str(exc))
    query = urlencode(
        {
            "msg": "import_success",
            "created": result.created_count,
            "updated": result.updated_count,
            "skipped": result.skipped_count,
            "errors": result.error_count,
        }
    )
    return RedirectResponse(url=f"/commissions?{query}", status_code=303)


def _upload(
    request: Request, *, kind: str, error: str | None = None
) -> HTMLResponse:
    is_rates = kind == "rates"
    return templates.TemplateResponse(
        request,
        "imports/generic_upload.html",
        {
            "active_nav": "commissions",
            "title": (
                "Komisyon Oranları Excel İçe Aktar"
                if is_rates
                else "Taksit Limitleri Excel İçe Aktar"
            ),
            "description": (
                "Aylık komisyon oranlarını Excel dosyasından yükleyin."
                if is_rates
                else "Aylık taksit limitlerini Excel dosyasından yükleyin."
            ),
            "form_action": f"/imports/commissions/{kind}/preview",
            "template_url": f"/imports/commissions/{kind}/template",
            "back_url": "/commissions",
            "back_label": "Komisyonlar",
            "accept": ".xlsx",
            "help_lines": RATE_HELP if is_rates else LIMIT_HELP,
            "error": error,
        },
        status_code=400 if error else 200,
    )


def _template_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
