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
from bayios.application.imports.offers_json import (
    commit_offer_json,
    preview_offer_json,
)
from bayios.application.offers.io import offer_import_template
from bayios.web.deps import ActorDep, UnitOfWorkDep
from bayios.web.templating import templates

router = APIRouter(prefix="/imports/offers", tags=["imports"])

HELP = (
    "Excel (.xlsx) veya scraper/backup JSON (schema_version 1.0) dosyası yükleyin. Excel'de tek sayfa düz dosya veya Teklifler + Teklif Satırları sayfaları kabul edilir.",
    "JSON içe aktarmada teklif ürünleri, kampanya adı, manuel nakit/kart toplamı ve durum bilgisi korunur.",
    "Yeni tekliflerde satırları gruplamak için Teklif Anahtarı kullanılır; mevcut taslaklar Teklif No ile güncellenir.",
    "Yalnızca taslak teklifler güncellenir. Komisyon ve kâr sunucuda yeniden hesaplanır.",
    "Kart tekliflerinde kanal, taksit ve kart tipi zorunludur; banka isteğe bağlıdır (boşsa genel oran kullanılır).",
    "Bilinmeyen ürün otomatik oluşturulmaz. Bilinmeyen bankayı istersen aşağıdaki onayla oluşturabilirsin; varsayılan kapalıdır.",
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
    auto_create_banks: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    if not file.filename:
        return _upload(request, error="Lütfen bir dosya seçin.")
    suffix = (
        file.filename.lower().rsplit(".", 1)[-1]
        if "." in file.filename
        else ""
    )
    if suffix not in {"xlsx", "json"}:
        return _upload(
            request, error="Yalnızca .xlsx veya .json uzantılı dosyalar desteklenir."
        )
    content = await file.read()
    if not content:
        return _upload(request, error="Yüklenen dosya boş.")
    create_banks = (auto_create_banks or "") == "1"
    try:
        preview = (
            preview_offer_json(uow, content, auto_create_banks=create_banks)
            if suffix == "json"
            else preview_offer_import(
                uow, content, auto_create_banks=create_banks
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _upload(request, error=str(exc))
    return templates.TemplateResponse(
        request,
        "imports/generic_preview.html",
        {
            "active_nav": "offers",
            "title": preview.title,
            "file_name": file.filename,
            "file_type": suffix,
            "preview": preview,
            "source_b64": base64.b64encode(content).decode("ascii"),
            "import_token": uuid.uuid4().hex,
            "commit_action": "/imports/offers/commit",
            "back_url": "/imports/offers",
            "auto_create_banks": create_banks,
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
    auto_create_banks: Annotated[str | None, Form()] = None,
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
        if file_type == "json" or source.lstrip().startswith(b"{"):
            result = commit_offer_json(
                uow,
                file_name=file_name,
                file_type="json",
                source=source,
                decisions=decisions if isinstance(decisions, dict) else {},
                actor=actor,
                commit_token=str(import_token) if import_token else None,
                auto_create_banks=(auto_create_banks or "") == "1",
            )
        else:
            result = commit_offer_import(
                uow,
                file_name=file_name,
                file_type=file_type,
                source=source,
                decisions=decisions if isinstance(decisions, dict) else {},
                actor=actor,
                commit_token=str(import_token) if import_token else None,
                auto_create_banks=(auto_create_banks or "") == "1",
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
            "title": "Teklif İçe Aktar (Excel/JSON)",
            "description": "Teklifleri ve ürün satırlarını Excel veya JSON dosyasından yükleyin.",
            "form_action": "/imports/offers/preview",
            "template_url": "/imports/offers/template",
            "template_label": "Şablon İndir",
            "json_template_url": "/offers/export/json",
            "json_template_label": "Örnek JSON İndir",
            "back_url": "/offers",
            "back_label": "Teklifler",
            "accept": ".xlsx,.json",
            "help_lines": HELP,
            "error": error,
            "show_bank_autocreate": True,
        },
        status_code=400 if error else 200,
    )
