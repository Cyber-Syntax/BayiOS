from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse

from bayios.application.products import (
    export_products_csv,
    export_products_xlsx,
    get_product_detail,
    search_products,
)
from bayios.web.deps import UnitOfWorkDep
from bayios.web.templating import templates

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_class=HTMLResponse)
def list_products(
    request: Request,
    uow: UnitOfWorkDep,
    q: Annotated[str | None, Query()] = None,
    page: int = 1,
    limit: int = 100,
) -> HTMLResponse:
    offset = max(0, (page - 1) * limit)
    products, total_count = search_products(uow, query=q, limit=limit, offset=offset)

    context = {
        "active_nav": "products",
        "products": products,
        "total_count": total_count,
        "q": q or "",
        "page": page,
        "limit": limit,
    }

    # If requested by HTMX search input, render only the table fragment
    if request.headers.get("HX-Request") and not request.headers.get("HX-Boosted"):
        return templates.TemplateResponse(request, "products/_table.html", context)

    return templates.TemplateResponse(request, "products/list.html", context)


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

    return templates.TemplateResponse(
        request,
        "products/detail.html",
        {
            "active_nav": "products",
            "product": detail.product,
            "price_history": detail.price_history,
            "stock_movements": detail.stock_movements,
            "sellable_stock": detail.sellable_stock,
            "open_reservation": detail.open_reservation,
            "supply_need": detail.supply_need,
        },
    )
