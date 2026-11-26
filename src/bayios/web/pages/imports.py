from __future__ import annotations

import base64
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from bayios.application.errors import ImportFormatError
from bayios.application.imports import (
    ProductIndex,
    commit_product_import,
    preview_product_import,
    product_import_template,
)
from bayios.web.deps import ActorDep, UnitOfWorkDep
from bayios.web.templating import templates

router = APIRouter(prefix="/imports/products", tags=["imports"])


@router.get("", response_class=HTMLResponse)
def upload_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "imports/upload.html",
        {"active_nav": "products"},
    )


@router.get("/template")
def download_template() -> Response:
    return Response(
        content=product_import_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=bayios-sablon-urunler.xlsx"
        },
    )


@router.post("/preview", response_class=HTMLResponse)
async def preview_import(
    request: Request,
    uow: UnitOfWorkDep,
    file: Annotated[UploadFile, File()],
) -> HTMLResponse:
    if not file.filename:
        return templates.TemplateResponse(
            request,
            "imports/upload.html",
            {"active_nav": "products", "error": "Lütfen bir dosya seçin."},
        )

    file_name = file.filename
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if ext not in ("csv", "xlsx", "json"):
        return templates.TemplateResponse(
            request,
            "imports/upload.html",
            {
                "active_nav": "products",
                "error": "Yalnızca .csv, .xlsx ve .json uzantılı dosyalar desteklenir.",
            },
        )

    content = await file.read()
    if not content:
        return templates.TemplateResponse(
            request,
            "imports/upload.html",
            {"active_nav": "products", "error": "Yüklenen dosya boş."},
        )

    # Find existing products to pre-populate create/update/unchanged decisions.
    with uow:
        index = ProductIndex.load(uow)

    try:
        preview = preview_product_import(content, index=index)
    except ImportFormatError as exc:
        return templates.TemplateResponse(
            request,
            "imports/upload.html",
            {"active_nav": "products", "error": str(exc)},
        )

    create_count = sum(1 for r in preview.rows if r.decision == "create")
    update_count = sum(1 for r in preview.rows if r.decision == "update")
    unchanged_count = sum(1 for r in preview.rows if r.decision == "skip")
    error_count = sum(
        1 for r in preview.rows if r.decision == "error" or r.details_error
    )

    source_b64 = base64.b64encode(content).decode("ascii")

    # Build initial decisions dict for Alpine.js (row_number → decision)
    initial_decisions = {
        str(row.row_number): row.decision
        for row in preview.rows
        if not row.errors
    }

    import_token = uuid.uuid4().hex

    return templates.TemplateResponse(
        request,
        "imports/preview.html",
        {
            "active_nav": "products",
            "file_name": file_name,
            "file_type": preview.source_type,
            "source_type": preview.source_type,
            "schema_version": preview.schema_version,
            "catalog_scraped_at": preview.catalog_scraped_at,
            "total_rows": len(preview.rows),
            "create_count": create_count,
            "update_count": update_count,
            "unchanged_count": unchanged_count,
            "error_count": error_count,
            "rows": preview.rows,
            "source_b64": source_b64,
            "initial_decisions": initial_decisions,
            "import_token": import_token,
        },
    )


@router.post("/commit", response_class=HTMLResponse)
async def commit_import(
    request: Request,
    uow: UnitOfWorkDep,
    actor: ActorDep,
) -> Response:
    # Large catalog.json files arrive as Base64 in one multipart field. Starlette's
    # default part limit is 1 MB; allow enough room for a 32 MB file plus Base64.
    async with request.form(max_part_size=32 * 1024 * 1024) as form_data:
        file_name = str(form_data.get("file_name") or "")
        file_type = str(form_data.get("file_type") or "")
        source_b64 = str(form_data.get("source_b64") or "")
        decisions_json_str = str(form_data.get("decisions_json") or "{}")
        import_token = form_data.get("import_token")

    if not source_b64:
        raise HTTPException(status_code=400, detail="Dosya verisi bulunamadı")

    try:
        source_bytes = base64.b64decode(
            source_b64.encode("ascii"), validate=True
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Geçersiz dosya verisi") from exc

    try:
        decisions: dict[str, str] = json.loads(decisions_json_str)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Geçersiz karar verisi") from exc

    try:
        result = commit_product_import(
            uow=uow,
            file_name=file_name,
            file_type=file_type,
            source=source_bytes,
            decisions=decisions,
            actor=actor,
            commit_token=str(import_token) if import_token else None,
        )
    except ImportFormatError as exc:
        return templates.TemplateResponse(
            request,
            "imports/upload.html",
            {"active_nav": "products", "error": str(exc)},
        )

    # Redirect back to products with feedback
    return RedirectResponse(
        url=f"/products?msg=import_success&created={result.created_count}&updated={result.updated_count}&skipped={result.skipped_count}",
        status_code=303,
    )
