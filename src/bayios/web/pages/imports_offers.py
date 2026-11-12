from __future__ import annotations

import base64
import json
import uuid
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, File, Form, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from bayios.application.imports.offers import (
    commit_offer_import,
    preview_offer_import,
)
from bayios.application.offers.io import offer_import_template
from bayios.web.deps import ActorDep, UnitOfWorkDep
from bayios.web.templating import templates

router = APIRouter(prefix="/imports/offers", tags=["imports"])

HELP = (
    "Excel (.xlsx) dosyası yükleyin. Tek sayfa düz dosya veya Teklifler + Teklif Satırları sayfaları kabul edilir.",
    "Yeni tekliflerde satırları gruplamak için Teklif Anahtarı kullanılır; mevcut taslaklar Teklif No ile güncellenir.",
    "Yalnızca taslak teklifler güncellenir. Komisyon ve kâr sunucuda yeniden hesaplanır.",
    "Kart tekliflerinde kanal, taksit ve kart tipi zorunludur; POS/Ödero'da banka zorunludur.",
    "Bilinmeyen ürün veya banka otomatik oluşturulmaz.",
)


@router.get("", response_class=HTMLResponse)
def upload_page(request: Request) -> HTMLResponse:
    return _upload(request)


@router.get("/template")
def download_template() -> Response:
    return Response(
        content=offer_import_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=bayios-sablon-teklifler.xlsx"
        },
    )


@router.post("/preview", response_class=HTMLResponse)
async def preview_import(
    request: Request,
    uow: UnitOfWorkDep,
    file: Annotated[UploadFile, File()],
) -> HTMLResponse:
    if not file.filename:
        return _upload(request, error="Lütfen bir dosya seçin.")
    if not file.filename.lower().endswith(".xlsx"):
        return _upload(request, error="Yalnızca .xlsx uzantılı dosyalar desteklenir.")
    content = await file.read()
    if not content:
        return _upload(request, error="Yüklenen dosya boş.")
    try:
        preview = preview_offer_import(uow, content)
    except Exception as exc:  # noqa: BLE001
        return _upload(request, error=str(exc))
    return templates.TemplateResponse(
        request,
        "imports/generic_preview.html",
        {
            "active_nav": "offers",
            "title": preview.title,
            "file_name": file.filename,
            "file_type": "xlsx",
            "preview": preview,
            "source_b64": base64.b64encode(content).decode("ascii"),
            "import_token": uuid.uuid4().hex,
            "commit_action": "/imports/offers/commit",
            "back_url": "/imports/offers",
        },
    )


@router.post("/commit")
async def commit_import(
    request: Request,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    file_name: Annotated[str, Form()],
    file_type: Annotated[str, Form()],
    source_b64: Annotated[str, Form()],
    import_token: Annotated[str | None, Form()] = None,
) -> Response:
    try:
        source = base64.b64decode(source_b64.encode("ascii"))
    except Exception:  # noqa: BLE001
        return _upload(request, error="Geçersiz dosya verisi.")
    form = await request.form()
    try:
        decisions = json.loads(str(form.get("decisions_json") or "{}"))
    except json.JSONDecodeError:
        return _upload(request, error="Geçersiz karar verisi.")
    try:
        result = commit_offer_import(
            uow,
            file_name=file_name,
            file_type=file_type,
            source=source,
            decisions=decisions if isinstance(decisions, dict) else {},
            actor=actor,
            commit_token=str(import_token) if import_token else None,
        )
    except Exception as exc:  # noqa: BLE001
        return _upload(request, error=str(exc))
    query = urlencode(
        {
            "msg": "import_success",
            "created": result.created_count,
            "updated": result.updated_count,
            "skipped": result.skipped_count,
            "errors": result.error_count,
        }
    )
    return RedirectResponse(url=f"/offers?{query}", status_code=303)


def _upload(request: Request, *, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "imports/generic_upload.html",
        {
            "active_nav": "offers",
            "title": "Teklif Excel İçe Aktar",
            "description": "Teklifleri ve ürün satırlarını Excel dosyasından yükleyin.",
            "form_action": "/imports/offers/preview",
            "template_url": "/imports/offers/template",
            "back_url": "/offers",
            "back_label": "Teklifler",
            "accept": ".xlsx",
            "help_lines": HELP,
            "error": error,
        },
        status_code=400 if error else 200,
    )
