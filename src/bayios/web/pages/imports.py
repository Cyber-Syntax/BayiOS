from __future__ import annotations

import base64
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from bayios.application.imports import commit_product_import, preview_product_import
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
    if ext not in ("csv", "xlsx"):
        return templates.TemplateResponse(
            request,
            "imports/upload.html",
            {
                "active_nav": "products",
                "error": "Yalnızca .csv ve .xlsx uzantılı dosyalar desteklenir.",
            },
        )

    content = await file.read()
    if not content:
        return templates.TemplateResponse(
            request,
            "imports/upload.html",
            {"active_nav": "products", "error": "Yüklenen dosya boş."},
        )

    # Find existing products to pre-populate update vs create decision
    with uow:
        all_products = uow.products.get_all()
        existing_names = {p.name_normalized for p in all_products}

    preview = preview_product_import(content, existing_names=existing_names)

    create_count = sum(1 for r in preview.rows if r.decision == "create")
    update_count = sum(1 for r in preview.rows if r.decision == "update")
    error_count = sum(1 for r in preview.rows if r.decision == "error")

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
            "file_type": ext,
            "total_rows": len(preview.rows),
            "create_count": create_count,
            "update_count": update_count,
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
    file_name: Annotated[str, Form()],
    file_type: Annotated[str, Form()],
    source_b64: Annotated[str, Form()],
) -> Response:
    try:
        source_bytes = base64.b64decode(source_b64.encode("ascii"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Geçersiz dosya verisi") from exc

    # Parse decisions from single JSON field — avoids multipart field-count limits
    form_data = await request.form()
    decisions_json_str = form_data.get("decisions_json") or "{}"
    import_token = form_data.get("import_token")
    try:
        decisions: dict[str, str] = json.loads(decisions_json_str)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Geçersiz karar verisi") from exc

    result = commit_product_import(
        uow=uow,
        file_name=file_name,
        file_type=file_type,
        source=source_bytes,
        decisions=decisions,
        actor=actor,
        commit_token=str(import_token) if import_token else None,
    )

    # Redirect back to products with feedback
    return RedirectResponse(
        url=f"/products?msg=import_success&created={result.created_count}&updated={result.updated_count}&skipped={result.skipped_count}",
        status_code=303,
    )
