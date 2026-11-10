from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from bayios.application.errors import NotFoundError, ValidationError
from bayios.application.products import get_product, search_products
from bayios.application.reservations import (
    STATUS_LABELS,
    NewReservationItem,
    add_reservation_item,
    cancel_item,
    change_item_status,
    create_reservation,
    default_snooze_due,
    deliver_item,
    get_reservation_detail,
    list_reservations,
    remove_reservation_item,
    snooze_reminder,
    update_reservation,
    update_reservation_item_quantity,
)
from bayios.domain.reservations import ACTIVE_STATUSES
from bayios.web.deps import ActorDep, UnitOfWorkDep
from bayios.web.templating import templates

router = APIRouter(prefix="/reservations", tags=["reservations"])

STATUS_FILTERS = (
    ("open", "Açık"),
    ("delivered", "Teslim edildi"),
    ("cancelled", "İptal"),
    ("overdue", "Hatırlatması geciken"),
    ("", "Tümü"),
)
PRINT_COPY_TITLES = {
    "depot": "DEPO KOPYASI",
    "dealer": "BAYİ KOPYASI",
}
STATUS_OPTIONS = tuple(
    (status.value, STATUS_LABELS[status]) for status in ACTIVE_STATUSES
)


def _optional_uuid(value: str | None) -> uuid.UUID | None:
    if not value or not value.strip():
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _parse_date(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValidationError("Tarih GG.AA.YYYY biçiminde olmalıdır.") from exc


def _parse_int(value: str | None, default: int | None = None) -> int | None:
    if value is None or not value.strip():
        return default
    try:
        return int(value.strip())
    except ValueError as exc:
        raise ValidationError("Miktar tam sayı olmalıdır.") from exc


def _redirect(reservation_id: uuid.UUID, msg: str) -> RedirectResponse:
    query = urlencode({"msg": msg})
    return RedirectResponse(
        url=f"/reservations/{reservation_id}?{query}", status_code=303
    )


@router.get("", response_class=HTMLResponse)
def list_reservations_route(
    request: Request,
    uow: UnitOfWorkDep,
    q: Annotated[str | None, Query()] = None,
    status: Annotated[str, Query()] = "open",
    page: Annotated[int, Query()] = 1,
    limit: Annotated[int, Query()] = 25,
) -> HTMLResponse:
    page = max(1, page)
    limit = max(1, limit)
    offset = (page - 1) * limit
    selected_status = status if status in {value for value, _ in STATUS_FILTERS} else "open"

    rows, total_count = list_reservations(
        uow,
        status=selected_status or None,
        query=q,
        limit=limit,
        offset=offset,
    )
    total_pages = max(1, math.ceil(total_count / limit))
    if page > total_pages:
        page = total_pages
        offset = (page - 1) * limit
        rows, total_count = list_reservations(
            uow,
            status=selected_status or None,
            query=q,
            limit=limit,
            offset=offset,
        )

    context = {
        "active_nav": "reservations",
        "rows": rows,
        "q": q or "",
        "status": selected_status,
        "status_filters": STATUS_FILTERS,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "total_count": total_count,
    }
    if request.headers.get("HX-Request") and not request.headers.get("HX-Boosted"):
        return templates.TemplateResponse(request, "reservations/_results.html", context)
    return templates.TemplateResponse(request, "reservations/list.html", context)


@router.get("/print", response_class=HTMLResponse)
def print_list_route(
    request: Request,
    uow: UnitOfWorkDep,
    q: Annotated[str | None, Query()] = None,
    status: Annotated[str, Query()] = "open",
) -> HTMLResponse:
    rows, _ = list_reservations(
        uow,
        status=status or None,
        query=q,
        limit=10_000,
        offset=0,
    )
    return templates.TemplateResponse(
        request,
        "reservations/print_list.html",
        {
            "active_nav": "reservations",
            "rows": rows,
            "q": q or "",
            "status": status,
            "generated_at": datetime.now(UTC),
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_reservation_page(
    request: Request,
    uow: UnitOfWorkDep,
    q: Annotated[str | None, Query()] = None,
    product_id: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    return _render_new(request, uow, q=q, preselected=_optional_uuid(product_id))


@router.get("/new/picker", response_class=HTMLResponse)
def new_reservation_picker(
    request: Request,
    uow: UnitOfWorkDep,
    q: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    products, _ = search_products(uow, query=q, limit=25, offset=0)
    return templates.TemplateResponse(
        request,
        "reservations/_picker.html",
        {"products": products, "today": datetime.now(UTC)},
    )


@router.post("")
async def create_reservation_route(
    request: Request,
    uow: UnitOfWorkDep,
    actor: ActorDep,
) -> Response:
    form = await request.form()
    customer_name = str(form.get("customer_name") or "")
    note = str(form.get("note") or "") or None
    product_ids = [str(value) for value in form.getlist("product_id")]
    quantities = [str(value) for value in form.getlist("quantity")]

    items: list[NewReservationItem] = []
    try:
        for index, product_id in enumerate(product_ids):
            parsed_id = _optional_uuid(product_id)
            if parsed_id is None:
                continue
            quantity = _parse_int(
                quantities[index] if index < len(quantities) else None, default=1
            )
            items.append(NewReservationItem(parsed_id, int(quantity or 1)))
        reservation_date = _parse_date(str(form.get("reservation_date") or ""))
        view = create_reservation(
            uow,
            customer_name=customer_name,
            items=items,
            reservation_date=reservation_date,
            note=note,
            actor=actor,
        )
    except (ValidationError, ValueError) as exc:
        return _render_new(
            request,
            uow,
            q=None,
            preselected=None,
            error=str(exc),
            status_code=400,
            customer_name=customer_name,
            note=note or "",
        )

    return RedirectResponse(url=f"/reservations/{view.id}?msg=created", status_code=303)


@router.get("/{reservation_id}", response_class=HTMLResponse)
def reservation_detail_page(
    request: Request,
    reservation_id: uuid.UUID,
    uow: UnitOfWorkDep,
) -> HTMLResponse:
    return _render_detail(request, uow, reservation_id)


@router.post("/{reservation_id}/edit")
def update_reservation_route(
    reservation_id: uuid.UUID,
    uow: UnitOfWorkDep,
    customer_name: Annotated[str, Form()],
    note: Annotated[str | None, Form()] = None,
    reservation_date: Annotated[str | None, Form()] = None,
) -> Response:
    try:
        update_reservation(
            uow,
            reservation_id,
            customer_name=customer_name,
            note=note,
            reservation_date=_parse_date(reservation_date),
        )
    except (ValidationError, NotFoundError) as exc:
        return _redirect(reservation_id, f"error:{exc}")
    return _redirect(reservation_id, "updated")


@router.post("/{reservation_id}/items")
def add_item_route(
    reservation_id: uuid.UUID,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    product_id: Annotated[str, Form()],
    quantity: Annotated[str | None, Form()] = None,
) -> Response:
    try:
        add_reservation_item(
            uow,
            reservation_id,
            product_id=_optional_uuid(product_id) or uuid.UUID(int=0),
            quantity=int(_parse_int(quantity, default=1) or 1),
            actor=actor,
        )
    except (ValidationError, NotFoundError) as exc:
        return _redirect(reservation_id, f"error:{exc}")
    return _redirect(reservation_id, "item_added")


@router.post("/{reservation_id}/items/{item_id}/quantity")
def update_item_quantity_route(
    reservation_id: uuid.UUID,
    item_id: uuid.UUID,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    quantity: Annotated[str, Form()],
    note: Annotated[str | None, Form()] = None,
) -> Response:
    try:
        update_reservation_item_quantity(
            uow,
            item_id,
            new_quantity=int(_parse_int(quantity, default=1) or 1),
            note=note,
            actor=actor,
        )
    except (ValidationError, NotFoundError) as exc:
        return _redirect(reservation_id, f"error:{exc}")
    return _redirect(reservation_id, "quantity_updated")


@router.post("/{reservation_id}/items/{item_id}/remove")
def remove_item_route(
    reservation_id: uuid.UUID,
    item_id: uuid.UUID,
    uow: UnitOfWorkDep,
    actor: ActorDep,
) -> Response:
    try:
        remove_reservation_item(uow, item_id, actor=actor)
    except (ValidationError, NotFoundError) as exc:
        return _redirect(reservation_id, f"error:{exc}")
    return _redirect(reservation_id, "item_removed")


@router.post("/{reservation_id}/items/{item_id}/status")
def change_status_route(
    reservation_id: uuid.UUID,
    item_id: uuid.UUID,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    target_status: Annotated[str, Form()],
    note: Annotated[str | None, Form()] = None,
    service_date: Annotated[str | None, Form()] = None,
    other_dealer_note: Annotated[str | None, Form()] = None,
) -> Response:
    try:
        change_item_status(
            uow,
            item_id,
            target_status=target_status,
            note=note,
            service_date=_parse_date(service_date),
            other_dealer_note=other_dealer_note,
            actor=actor,
        )
    except (ValidationError, NotFoundError) as exc:
        return _redirect(reservation_id, f"error:{exc}")
    return _redirect(reservation_id, "status_changed")


@router.post("/{reservation_id}/items/{item_id}/deliver")
def deliver_item_route(
    reservation_id: uuid.UUID,
    item_id: uuid.UUID,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    quantity: Annotated[str, Form()],
    idempotency_key: Annotated[str, Form()],
    low_stock_reason: Annotated[str | None, Form()] = None,
    note: Annotated[str | None, Form()] = None,
) -> Response:
    try:
        deliver_item(
            uow,
            item_id,
            quantity=int(_parse_int(quantity, default=1) or 1),
            idempotency_key=idempotency_key,
            low_stock_reason=low_stock_reason or None,
            note=note,
            actor=actor,
        )
    except (ValidationError, NotFoundError) as exc:
        return _redirect(reservation_id, f"error:{exc}")
    return _redirect(reservation_id, "delivered")


@router.post("/{reservation_id}/items/{item_id}/cancel")
def cancel_item_route(
    reservation_id: uuid.UUID,
    item_id: uuid.UUID,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    quantity: Annotated[str, Form()],
    note: Annotated[str | None, Form()] = None,
) -> Response:
    try:
        cancel_item(
            uow,
            item_id,
            quantity=int(_parse_int(quantity, default=1) or 1),
            note=note,
            actor=actor,
        )
    except (ValidationError, NotFoundError) as exc:
        return _redirect(reservation_id, f"error:{exc}")
    return _redirect(reservation_id, "cancelled")


@router.post("/{reservation_id}/reminder/snooze")
def snooze_reminder_route(
    reservation_id: uuid.UUID,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    new_due_at: Annotated[str | None, Form()] = None,
    note: Annotated[str | None, Form()] = None,
) -> Response:
    try:
        snooze_reminder(
            uow,
            reservation_id,
            new_due_at=_parse_date(new_due_at),
            note=note,
            actor=actor,
        )
    except (ValidationError, NotFoundError) as exc:
        return _redirect(reservation_id, f"error:{exc}")
    return _redirect(reservation_id, "snoozed")


@router.get("/{reservation_id}/items/picker", response_class=HTMLResponse)
def item_picker(
    request: Request,
    reservation_id: uuid.UUID,
    uow: UnitOfWorkDep,
    q: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    products, _ = search_products(uow, query=q, limit=10, offset=0)
    return templates.TemplateResponse(
        request,
        "reservations/_item_picker.html",
        {"products": products, "reservation_id": reservation_id},
    )


@router.get("/{reservation_id}/print", response_class=HTMLResponse)
def print_detail_route(
    request: Request,
    reservation_id: uuid.UUID,
    uow: UnitOfWorkDep,
    copy: Annotated[str, Query()] = "both",
) -> HTMLResponse:
    detail = get_reservation_detail(uow, reservation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı.")
    copies = (
        list(PRINT_COPY_TITLES.items())
        if copy not in PRINT_COPY_TITLES
        else [(copy, PRINT_COPY_TITLES[copy])]
    )
    return templates.TemplateResponse(
        request,
        "reservations/print_detail.html",
        {
            "active_nav": "reservations",
            "reservation": detail,
            "copies": copies,
            "copy": copy,
            "generated_at": datetime.now(UTC),
        },
    )


def _render_new(
    request: Request,
    uow: UnitOfWorkDep,
    *,
    q: str | None,
    preselected: uuid.UUID | None,
    error: str | None = None,
    status_code: int = 200,
    customer_name: str = "",
    note: str = "",
) -> HTMLResponse:
    products, _ = search_products(uow, query=q, limit=25, offset=0)
    initial_lines: list[dict[str, str]] = []
    if preselected is not None:
        selected = get_product(uow, preselected)
        if selected is not None:
            initial_lines.append({"id": str(selected.id), "name": selected.name})

    return templates.TemplateResponse(
        request,
        "reservations/new.html",
        {
            "active_nav": "reservations",
            "products": products,
            "q": q or "",
            "initial_lines": initial_lines,
            "customer_name": customer_name,
            "note": note,
            "today": datetime.now(UTC).date().isoformat(),
            "error": error,
        },
        status_code=status_code,
    )


def _render_detail(
    request: Request,
    uow: UnitOfWorkDep,
    reservation_id: uuid.UUID,
    *,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    detail = get_reservation_detail(uow, reservation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı.")

    return templates.TemplateResponse(
        request,
        "reservations/detail.html",
        {
            "active_nav": "reservations",
            "reservation": detail,
            "status_options": STATUS_OPTIONS,
            "status_labels": {
                status.value: label for status, label in STATUS_LABELS.items()
            },
            "page_token": uuid.uuid4().hex,
            "today": datetime.now(UTC).date().isoformat(),
            "default_snooze": default_snooze_due(datetime.now(UTC))
            .date()
            .isoformat(),
            "error": error,
        },
        status_code=status_code,
    )
