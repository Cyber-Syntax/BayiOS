from __future__ import annotations

import base64
import json
import uuid
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from bayios.application.campaigns.io import campaign_import_template
from bayios.application.imports.campaigns import (
    commit_campaign_import,
    preview_campaign_import,
)
from bayios.web.deps import ActorDep, UnitOfWorkDep
from bayios.web.templating import templates

router = APIRouter(prefix="/imports/campaigns", tags=["imports"])

UPLOAD_HELP = (
    "Excel (.xlsx) dosyası yükleyin. Tercih edilen format: <strong>Kampanyalar</strong> ve <strong>Kampanya Ürünleri</strong> sayfaları.",
    "Kampanya detayından açıldıysa yalnızca o kampanya güncellenir; ürün listesi tek başına da yüklenebilir.",
    "Tek sayfa şirket dosyası da kabul edilir; aynı kampanya satırları kampanya adı ve tarihlerle gruplanır.",
    "Kampanya adı, başlangıç ve bitiş tarihi zorunludur. Bitiş tarihi başlangıçtan önce olamaz.",
    "Ürün ilişkisi: Şart ürünü, Fayda ürünü, Hediye ürünü veya İlgili ürün.",
    "Bilinmeyen ürünler otomatik oluşturulmaz; önce ürünleri içe aktarın.",
    "Önizleme onaylanmadan veritabanına hiçbir kayıt yazılmaz.",
)


@router.get("", response_class=HTMLResponse)
def upload_page(
    request: Request,
    campaign_id: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    target = _optional_uuid(campaign_id)
    return _upload(request, target)


@router.get("/template")
def download_template() -> Response:
    return Response(
        content=campaign_import_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=bayios-sablon-kampanyalar.xlsx"
        },
    )


@router.post("/preview", response_class=HTMLResponse)
async def preview_import(
    request: Request,
    uow: UnitOfWorkDep,
    file: Annotated[UploadFile, File()],
    campaign_id: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    target = _optional_uuid(campaign_id)
    if not file.filename:
        return _upload(request, target, error="Lütfen bir dosya seçin.")
    if not file.filename.lower().endswith(".xlsx"):
        return _upload(
            request, target, error="Yalnızca .xlsx uzantılı dosyalar desteklenir."
        )
    content = await file.read()
    if not content:
        return _upload(request, target, error="Yüklenen dosya boş.")
    try:
        preview = preview_campaign_import(
            uow, content, target_campaign_id=target
        )
    except Exception as exc:  # noqa: BLE001
        return _upload(request, target, error=str(exc))
    return templates.TemplateResponse(
        request,
        "imports/generic_preview.html",
        {
            "active_nav": "campaigns",
            "title": preview.title,
            "file_name": file.filename,
            "file_type": "xlsx",
            "preview": preview,
            "source_b64": base64.b64encode(content).decode("ascii"),
            "import_token": uuid.uuid4().hex,
            "commit_action": "/imports/campaigns/commit",
            "back_url": (
                f"/campaigns/{target}" if target is not None else "/campaigns"
            ),
            "campaign_id": str(target) if target is not None else "",
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
    campaign_id: Annotated[str | None, Form()] = None,
) -> Response:
    target = _optional_uuid(campaign_id)
    try:
        source = base64.b64decode(source_b64.encode("ascii"))
    except Exception:  # noqa: BLE001
        return _upload(request, target, error="Geçersiz dosya verisi.")
    form = await request.form()
    try:
        decisions = json.loads(str(form.get("decisions_json") or "{}"))
    except json.JSONDecodeError:
        return _upload(request, target, error="Geçersiz karar verisi.")
    try:
        result = commit_campaign_import(
            uow,
            file_name=file_name,
            file_type=file_type,
            source=source,
            decisions=decisions if isinstance(decisions, dict) else {},
            actor=actor,
            commit_token=str(import_token) if import_token else None,
            target_campaign_id=target,
        )
    except Exception as exc:  # noqa: BLE001
        return _upload(request, target, error=str(exc))
    query = urlencode(
        {
            "msg": "import_success",
            "created": result.created_count,
            "updated": result.updated_count,
            "skipped": result.skipped_count,
            "errors": result.error_count,
        }
    )
    back = f"/campaigns/{target}" if target is not None else "/campaigns"
    return RedirectResponse(url=f"{back}?{query}", status_code=303)


def _upload(
    request: Request,
    target: uuid.UUID | None,
    *,
    error: str | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "imports/generic_upload.html",
        {
            "active_nav": "campaigns",
            "title": "Kampanya Excel İçe Aktar",
            "description": (
                "Bu kampanyanın ürün ilişkilerini Excel dosyasından yükleyin."
                if target is not None
                else "Kampanya ve ürün ilişkilerini Excel dosyasından yükleyin."
            ),
            "form_action": "/imports/campaigns/preview",
            "template_url": (
                f"/campaigns/{target}/export/xlsx"
                if target is not None
                else "/imports/campaigns/template"
            ),
            "back_url": (
                f"/campaigns/{target}" if target is not None else "/campaigns"
            ),
            "back_label": "Kampanyalar",
            "accept": ".xlsx",
            "help_lines": UPLOAD_HELP,
            "error": error,
            "campaign_id": str(target) if target is not None else "",
        },
        status_code=400 if error else 200,
    )


def _optional_uuid(value: str | None) -> uuid.UUID | None:
    if not value or not value.strip():
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None
