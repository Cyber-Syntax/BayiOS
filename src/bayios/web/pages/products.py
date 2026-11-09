from __future__ import annotations

import math
import uuid
from decimal import Decimal
from typing import Annotated
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from bayios.application.imports import _normalize_decimal
from bayios.application.inventory import list_categories
from bayios.application.products import (
    adjust_product_stock,
    archive_products,
    assign_products_category,
    create_manual_product,
    delete_products,
    export_products_csv,
    export_products_xlsx,
    get_product_detail,
    search_products,
    update_product,
)
from bayios.web.deps import ActorDep, UnitOfWorkDep
from bayios.web.templating import templates

router = APIRouter(prefix="/products", tags=["products"])


def _parse_decimal_form(val: str | None) -> Decimal | None:
    if not val or not val.strip():
        return None
    normalized = _normalize_decimal(val)
    if normalized is None:
        raise HTTPException(status_code=400, detail="Geçersiz fiyat formatı")
    return Decimal(normalized)


def _parse_uuid_form(val: str | None) -> uuid.UUID | None:
    if not val or not val.strip():
        return None
    try:
        return uuid.UUID(val)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Geçersiz kategori") from exc


def _parse_uuid_query(val: str | None) -> uuid.UUID | None:
    if not val or not val.strip():
        return None
    try:
        return uuid.UUID(val)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Geçersiz kategori") from exc


def _safe_redirect(url: str | None, fallback: str, msg: str) -> str:
    if not url or not url.startswith("/") or url.startswith("//"):
        url = fallback
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    query["msg"] = [msg]
    return urlunsplit(parsed._replace(query=urlencode(query, doseq=True)))


@router.get("", response_class=HTMLResponse)
def list_products(
    request: Request,
    uow: UnitOfWorkDep,
    q: Annotated[str | None, Query()] = None,
    status: Annotated[str, Query()] = "active",
    category_id: Annotated[str | None, Query()] = None,
    page: int = 1,
    limit: int = 25,
) -> HTMLResponse:
    page = max(1, page)
    limit = max(1, limit)
    offset = (page - 1) * limit
    only_archived = status == "archived"
    include_archived = status == "all" or status == "archived"
    selected_category = _parse_uuid_query(category_id)

    products, total_count = search_products(
        uow,
        query=q,
        category_id=selected_category,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
        only_archived=only_archived,
    )

    total_pages = max(1, math.ceil(total_count / limit))
    if page > total_pages:
        page = total_pages
        offset = (page - 1) * limit
        products, total_count = search_products(
            uow,
            query=q,
            category_id=selected_category,
            limit=limit,
            offset=offset,
            include_archived=include_archived,
            only_archived=only_archived,
        )

    categories = list_categories(uow)
    context = {
        "active_nav": "products",
        "products": products,
        "categories": categories,
        "category_names": {category.id: category.name for category in categories},
        "total_count": total_count,
        "q": q or "",
        "status": status,
        "selected_category": selected_category,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
    }

    # If requested by HTMX search input, render only the table fragment
    if request.headers.get("HX-Request") and not request.headers.get("HX-Boosted"):
        return templates.TemplateResponse(request, "products/_table.html", context)

    return templates.TemplateResponse(request, "products/list.html", context)


@router.post("", response_class=HTMLResponse)
def create_product_route(
    request: Request,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    name: Annotated[str, Form()],
    regular_price: Annotated[str | None, Form()] = None,
    website_discounted_price: Annotated[str | None, Form()] = None,
    cost_price: Annotated[str | None, Form()] = None,
    physical_stock: Annotated[int, Form()] = 0,
    category_id: Annotated[str | None, Form()] = None,
) -> Response:
    try:
        reg = _parse_decimal_form(regular_price)
        disc = _parse_decimal_form(website_discounted_price)
        cost = _parse_decimal_form(cost_price)
        create_manual_product(
            uow=uow,
            name=name,
            regular_price=reg,
            website_discounted_price=disc,
            cost_price=cost,
            physical_stock=physical_stock,
            category_id=_parse_uuid_form(category_id),
            actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RedirectResponse(url="/products?msg=product_created", status_code=303)


@router.post("/bulk-archive")
def bulk_archive_route(
    uow: UnitOfWorkDep,
    product_ids: Annotated[list[str], Form()],
    action: Annotated[str, Form()] = "archive",
) -> Response:
    uuids = [uuid.UUID(pid) for pid in product_ids if pid]
    should_archive = action != "unarchive"
    archive_products(uow, uuids, archive=should_archive)
    msg = "archived" if should_archive else "unarchived"
    return RedirectResponse(url=f"/products?msg={msg}&count={len(uuids)}", status_code=303)


@router.post("/bulk-delete")
def bulk_delete_route(
    uow: UnitOfWorkDep,
    product_ids: Annotated[list[str], Form()],
    confirmed: Annotated[str, Form()] = "",
) -> Response:
    if confirmed != "yes_delete_permanently":
        raise HTTPException(
            status_code=400, detail="Silme işlemi iki aşamalı doğrulama gerektirir."
        )
    uuids = [uuid.UUID(pid) for pid in product_ids if pid]
    delete_products(uow, uuids)
    return RedirectResponse(url=f"/products?msg=deleted&count={len(uuids)}", status_code=303)


@router.post("/bulk-category")
def bulk_category_route(
    uow: UnitOfWorkDep,
    product_ids: Annotated[list[str], Form()],
    category_id: Annotated[str | None, Form()] = None,
) -> Response:
    uuids = [uuid.UUID(pid) for pid in product_ids if pid]
    try:
        count = assign_products_category(
            uow, uuids, category_id=_parse_uuid_form(category_id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        url=f"/products?msg=category_assigned&count={count}", status_code=303
    )


@router.post("/{product_id}/stock")
def update_product_stock_route(
    product_id: uuid.UUID,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    physical_stock: Annotated[int, Form()],
    note: Annotated[str | None, Form()] = None,
    redirect_to: Annotated[str | None, Form()] = None,
) -> Response:
    if physical_stock < 0:
        raise HTTPException(status_code=400, detail="Fiziksel stok negatif olamaz.")
    try:
        adjust_product_stock(
            uow=uow,
            product_id=product_id,
            new_physical_stock=physical_stock,
            note=note,
            actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    target = _safe_redirect(
        redirect_to, f"/products/{product_id}", "stock_updated"
    )
    return RedirectResponse(url=target, status_code=303)


@router.post("/{product_id}/edit")
def update_product_route(
    product_id: uuid.UUID,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    name: Annotated[str, Form()],
    regular_price: Annotated[str | None, Form()] = None,
    website_discounted_price: Annotated[str | None, Form()] = None,
    cost_price: Annotated[str | None, Form()] = None,
    category_id: Annotated[str | None, Form()] = None,
) -> Response:
    try:
        update_product(
            uow=uow,
            product_id=product_id,
            name=name,
            regular_price=_parse_decimal_form(regular_price),
            website_discounted_price=_parse_decimal_form(website_discounted_price),
            cost_price=_parse_decimal_form(cost_price),
            category_id=_parse_uuid_form(category_id),
            actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RedirectResponse(
        url=f"/products/{product_id}?msg=product_updated", status_code=303
    )


@router.post("/{product_id}/archive")
def archive_single_product_route(
    product_id: uuid.UUID,
    uow: UnitOfWorkDep,
    action: Annotated[str, Form()] = "archive",
) -> Response:
    should_archive = action != "unarchive"
    archive_products(uow, [product_id], archive=should_archive)
    msg = "archived" if should_archive else "unarchived"
    return RedirectResponse(url=f"/products/{product_id}?msg={msg}", status_code=303)


@router.post("/{product_id}/delete")
def delete_single_product_route(
    product_id: uuid.UUID,
    uow: UnitOfWorkDep,
    confirmed: Annotated[str, Form()] = "",
) -> Response:
    if confirmed != "yes_delete_permanently":
        raise HTTPException(
            status_code=400, detail="Silme işlemi iki aşamalı doğrulama gerektirir."
        )
    delete_products(uow, [product_id])
    return RedirectResponse(url="/products?msg=deleted&count=1", status_code=303)


@router.get("/export/csv")
def export_csv(uow: UnitOfWorkDep) -> Response:
    csv_bytes = export_products_csv(uow)
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=bayios-urunler.csv"},
    )


@router.get("/export/xlsx")
def export_xlsx(uow: UnitOfWorkDep) -> Response:
    xlsx_bytes = export_products_xlsx(uow)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=bayios-urunler.xlsx"},
    )


@router.get("/{product_id}", response_class=HTMLResponse)
def product_detail(
    request: Request,
    product_id: uuid.UUID,
    uow: UnitOfWorkDep,
) -> HTMLResponse:
    detail = get_product_detail(uow, product_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")

    categories = list_categories(uow)
    category_names = {category.id: category.name for category in categories}
    return templates.TemplateResponse(
        request,
        "products/detail.html",
        {
            "active_nav": "products",
            "product": detail.product,
            "price_history": detail.price_history,
            "stock_movements": detail.stock_movements,
            "open_reservation": detail.open_reservation,
            "categories": categories,
            "category_name": category_names.get(detail.product.category_id),
        },
    )
