from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from bayios.application.campaigns import list_campaigns
from bayios.application.commissions import list_banks
from bayios.application.errors import NotFoundError, ValidationError
from bayios.application.offers import (
    OfferInput,
    OfferItemInput,
    build_offer_profit_summary,
    convert_offer_to_reservation,
    create_offer,
    get_offer_detail,
    list_offers,
    reserve_offer,
    sell_offer,
    set_offer_status,
    update_offer,
)
from bayios.application.offers.io import export_offers_xlsx
from bayios.application.products import search_products
from bayios.domain.commissions import (
    CARD_TYPE_LABELS,
    CHANNEL_LABELS,
    CardType,
    PaymentChannel,
)
from bayios.domain.offers import (
    OFFER_STATUS_LABELS,
    PAYMENT_TYPE_LABELS,
    PaymentType,
)
from bayios.web.deps import ActorDep, UnitOfWorkDep
from bayios.web.templating import templates

router = APIRouter(prefix="/offers", tags=["offers"])

STATUS_FILTERS = (("", "Tümü"),) + tuple(
    (status.value, label) for status, label in OFFER_STATUS_LABELS.items()
)


@router.get("", response_class=HTMLResponse)
def offers_page(
    request: Request,
    uow: UnitOfWorkDep,
    status: Annotated[str, Query()] = "",
    q: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query()] = 1,
    limit: Annotated[int, Query()] = 25,
) -> HTMLResponse:
    page = max(1, page)
    limit = max(1, limit)
    selected = status if status in {value for value, _ in STATUS_FILTERS} else ""
    rows, total = list_offers(
        uow,
        status=selected or None,
        query=q,
        limit=limit,
        offset=(page - 1) * limit,
    )
    pages = max(1, math.ceil(total / limit))
    context = {
        "active_nav": "offers",
        "rows": rows,
        "status": selected,
        "q": q or "",
        "status_filters": STATUS_FILTERS,
        "status_labels": OFFER_STATUS_LABELS,
        "payment_labels": PAYMENT_TYPE_LABELS,
        "page": page,
        "limit": limit,
        "total_pages": pages,
        "total_count": total,
    }
    if request.headers.get("HX-Request") and not request.headers.get("HX-Boosted"):
        return templates.TemplateResponse(
            request, "offers/_results.html", context
        )
    return templates.TemplateResponse(request, "offers/list.html", context)


@router.get("/export/xlsx")
def export_offers_route(
    uow: UnitOfWorkDep,
    status: Annotated[str, Query()] = "",
    q: Annotated[str | None, Query()] = None,
) -> Response:
    selected = status if status in {value for value, _ in STATUS_FILTERS} else ""
    content = export_offers_xlsx(uow, status=selected or None, query=q)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=bayios-teklifler.xlsx"},
    )


@router.get("/new", response_class=HTMLResponse)
def new_offer_page(request: Request, uow: UnitOfWorkDep) -> HTMLResponse:
    return _render_form(request, uow, offer_id=None)


@router.get("/picker", response_class=HTMLResponse)
def offer_picker(
    request: Request,
    uow: UnitOfWorkDep,
    q: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    products, _ = search_products(uow, query=q, limit=5, offset=0)
    return templates.TemplateResponse(
        request, "offers/_picker.html", {"products": products}
    )


@router.post("")
async def create_offer_route(
    request: Request, uow: UnitOfWorkDep, actor: ActorDep
) -> Response:
    form = await request.form()
    try:
        data = _offer_input_from_form(form)
        offer_id = create_offer(uow, data, actor)
    except (ValidationError, ValueError, NotFoundError) as exc:
        return _render_form(
            request,
            uow,
            offer_id=None,
            error=str(exc),
            status_code=400,
            form=form,
        )
    return RedirectResponse(
        url=f"/offers/{offer_id}?{urlencode({'msg': 'created'})}",
        status_code=303,
    )


@router.get("/{offer_id}", response_class=HTMLResponse)
def offer_detail_page(
    request: Request, offer_id: uuid.UUID, uow: UnitOfWorkDep
) -> HTMLResponse:
    detail = get_offer_detail(uow, offer_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Teklif bulunamadı.")
    return templates.TemplateResponse(
        request,
        "offers/detail.html",
        {
            "active_nav": "offers",
            "detail": detail,
            "profit_summary": build_offer_profit_summary(detail),
            "status_labels": OFFER_STATUS_LABELS,
            "payment_labels": PAYMENT_TYPE_LABELS,
            "channel_labels": CHANNEL_LABELS,
            "card_labels": CARD_TYPE_LABELS,
            "msg": request.query_params.get("msg"),
        },
    )


@router.get("/{offer_id}/edit", response_class=HTMLResponse)
def edit_offer_page(
    request: Request, offer_id: uuid.UUID, uow: UnitOfWorkDep
) -> HTMLResponse:
    detail = get_offer_detail(uow, offer_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Teklif bulunamadı.")
    return _render_form(request, uow, offer_id=offer_id, detail=detail)


@router.post("/{offer_id}/edit")
async def update_offer_route(
    request: Request,
    offer_id: uuid.UUID,
    uow: UnitOfWorkDep,
    actor: ActorDep,
) -> Response:
    form = await request.form()
    try:
        data = _offer_input_from_form(form)
        update_offer(uow, offer_id, data, actor)
    except (ValidationError, ValueError, NotFoundError) as exc:
        detail = get_offer_detail(uow, offer_id)
        return _render_form(
            request,
            uow,
            offer_id=offer_id,
            detail=detail,
            error=str(exc),
            status_code=400,
            form=form,
        )
    return RedirectResponse(
        url=f"/offers/{offer_id}?{urlencode({'msg': 'updated'})}",
        status_code=303,
    )


@router.post("/{offer_id}/status")
def set_status_route(
    offer_id: uuid.UUID,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    target_status: Annotated[str, Form()],
) -> RedirectResponse:
    try:
        set_offer_status(uow, offer_id, target_status, actor=actor)
    except (ValidationError, NotFoundError) as exc:
        return RedirectResponse(
            url=f"/offers/{offer_id}?{urlencode({'msg': f'error:{exc}'})}",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/offers/{offer_id}?{urlencode({'msg': 'status'})}",
        status_code=303,
    )


@router.post("/{offer_id}/convert")
def convert_offer_route(
    offer_id: uuid.UUID, uow: UnitOfWorkDep, actor: ActorDep
) -> RedirectResponse:
    try:
        reservation_id = convert_offer_to_reservation(uow, offer_id, actor)
    except (ValidationError, NotFoundError) as exc:
        return RedirectResponse(
            url=f"/offers/{offer_id}?{urlencode({'msg': f'error:{exc}'})}",
            status_code=303,
        )
    return RedirectResponse(url=f"/reservations/{reservation_id}", status_code=303)


@router.post("/{offer_id}/reserve")
def reserve_offer_route(
    offer_id: uuid.UUID, uow: UnitOfWorkDep, actor: ActorDep
) -> RedirectResponse:
    try:
        reserve_offer(uow, offer_id, actor)
    except (ValidationError, NotFoundError) as exc:
        return RedirectResponse(
            url=f"/offers/{offer_id}?{urlencode({'msg': f'error:{exc}'})}",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/offers/{offer_id}?{urlencode({'msg': 'reserved'})}",
        status_code=303,
    )


@router.post("/{offer_id}/sell")
def sell_offer_route(
    offer_id: uuid.UUID,
    uow: UnitOfWorkDep,
    actor: ActorDep,
    low_stock_reason: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    try:
        sell_offer(
            uow,
            offer_id,
            low_stock_reason=low_stock_reason,
            actor=actor,
        )
    except (ValidationError, NotFoundError) as exc:
        return RedirectResponse(
            url=f"/offers/{offer_id}?{urlencode({'msg': f'error:{exc}'})}",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/offers/{offer_id}?{urlencode({'msg': 'sold'})}",
        status_code=303,
    )


@router.get("/{offer_id}/print", response_class=HTMLResponse)
def print_offer(
    request: Request, offer_id: uuid.UUID, uow: UnitOfWorkDep
) -> HTMLResponse:
    detail = get_offer_detail(uow, offer_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Teklif bulunamadı.")
    return templates.TemplateResponse(
        request,
        "offers/print_detail.html",
        {
            "active_nav": "offers",
            "detail": detail,
            "payment_labels": PAYMENT_TYPE_LABELS,
            "generated_at": datetime.now(UTC),
        },
    )


def _render_form(
    request: Request,
    uow: UnitOfWorkDep,
    *,
    offer_id: uuid.UUID | None,
    detail: object | None = None,
    error: str | None = None,
    status_code: int = 200,
    form: object | None = None,
) -> HTMLResponse:
    campaigns, _ = list_campaigns(uow, state="active", limit=200)
    banks = list_banks(uow)
    products, _ = search_products(uow, query=None, limit=5, offset=0)
    initial_items: list[dict[str, object]] = []
    values: dict[str, object] = {
        "customer_name": "",
        "customer_phone": "",
        "note": "",
        "payment_type": "cash",
        "channel": "",
        "bank_id": "",
        "installment_count": "",
        "card_type": "",
        "dealer_discount_percent": "10",
    }
    if form is not None:
        values, initial_items = _form_state_from_form(uow, form)
    elif detail is not None:
        offer = detail.offer
        values.update(
            {
                "customer_name": offer.customer_name or "",
                "customer_phone": offer.customer_phone or "",
                "note": offer.note or "",
                "payment_type": offer.payment_type,
                "channel": offer.channel or "",
                "bank_id": str(offer.bank_id) if offer.bank_id else "",
                "installment_count": (
                    str(offer.installment_count)
                    if offer.installment_count
                    else ""
                ),
                "card_type": offer.card_type or "",
                "dealer_discount_percent": str(offer.dealer_discount_percent),
            }
        )
        initial_items = [
            {
                "product_id": str(item.product_id) if item.product_id else "",
                "product_name": item.product_name_snapshot,
                "quantity": item.quantity,
                "campaign_id": str(
                    (item.campaign_snapshot or {}).get("campaign_id") or "auto"
                ),
                "gift_present": "",
                "unit_price_cash": (
                    str(item.unit_price_cash)
                    if item.unit_price_cash is not None
                    else ""
                ),
                "unit_price_card": (
                    str(item.unit_price_card)
                    if item.unit_price_card is not None
                    else ""
                ),
            }
            for item in detail.items
        ]
    return templates.TemplateResponse(
        request,
        "offers/form.html",
        {
            "active_nav": "offers",
            "offer_id": offer_id,
            "values": values,
            "initial_items": initial_items,
            "campaigns": campaigns,
            "banks": banks,
            "products": products,
            "channel_options": tuple(
                (item.value, CHANNEL_LABELS[item]) for item in PaymentChannel
            ),
            "card_options": tuple(
                (item.value, CARD_TYPE_LABELS[item]) for item in CardType
            ),
            "error": error,
        },
        status_code=status_code,
    )


def _form_state_from_form(
    uow: UnitOfWorkDep, form: object
) -> tuple[dict[str, object], list[dict[str, object]]]:
    get = form.get  # type: ignore[attr-defined]
    getlist = form.getlist  # type: ignore[attr-defined]
    values: dict[str, object] = {
        "customer_name": str(get("customer_name") or ""),
        "customer_phone": str(get("customer_phone") or ""),
        "note": str(get("note") or ""),
        "payment_type": str(get("payment_type") or "cash"),
        "channel": str(get("channel") or ""),
        "bank_id": str(get("bank_id") or ""),
        "installment_count": str(get("installment_count") or ""),
        "card_type": str(get("card_type") or ""),
        "dealer_discount_percent": str(
            get("dealer_discount_percent") or "10"
        ),
    }
    product_ids = [str(value) for value in getlist("product_id")]
    quantities = [str(value) for value in getlist("quantity")]
    campaign_ids = [str(value) for value in getlist("campaign_id")]
    gift_values = [str(value) for value in getlist("gift_present")]
    cash_values = [str(value) for value in getlist("unit_price_cash")]
    card_values = [str(value) for value in getlist("unit_price_card")]
    parsed_ids = [_optional_uuid(raw) for raw in product_ids]
    target_ids = [item for item in parsed_ids if item is not None]
    products: dict[uuid.UUID, object] = {}
    if target_ids:
        with uow:
            products = {
                product.id: product
                for product in uow.products.get_by_ids(target_ids)
            }
    items: list[dict[str, object]] = []
    for index, raw_id in enumerate(product_ids):
        product_id = parsed_ids[index]
        if product_id is None:
            continue
        product = products.get(product_id)
        items.append(
            {
                "product_id": str(product_id),
                "product_name": (
                    product.name if product is not None else raw_id
                ),
                "quantity": (
                    quantities[index] if index < len(quantities) else "1"
                ),
                "campaign_id": (
                    campaign_ids[index]
                    if index < len(campaign_ids)
                    else ""
                ),
                "gift_present": (
                    gift_values[index]
                    if index < len(gift_values)
                    else ""
                ),
                "unit_price_cash": (
                    cash_values[index] if index < len(cash_values) else ""
                ),
                "unit_price_card": (
                    card_values[index] if index < len(card_values) else ""
                ),
            }
        )
    return values, items


def _offer_input_from_form(form: object) -> OfferInput:
    get = form.get  # type: ignore[attr-defined]
    getlist = form.getlist  # type: ignore[attr-defined]
    product_ids = [str(value) for value in getlist("product_id")]
    quantities = [str(value) for value in getlist("quantity")]
    campaign_ids = [str(value) for value in getlist("campaign_id")]
    gift_values = [str(value) for value in getlist("gift_present")]
    cash_values = [str(value) for value in getlist("unit_price_cash")]
    card_values = [str(value) for value in getlist("unit_price_card")]
    items: list[OfferItemInput] = []
    for index, raw_id in enumerate(product_ids):
        if not raw_id.strip():
            continue
        product_id = _optional_uuid(raw_id)
        if product_id is None:
            raise ValidationError("Geçersiz ürün seçimi.")
        raw_campaign = (
            campaign_ids[index] if index < len(campaign_ids) else ""
        )
        auto_campaign = raw_campaign == "auto"
        items.append(
            OfferItemInput(
                product_id=product_id,
                quantity=_int_value(
                    quantities[index] if index < len(quantities) else "1"
                ),
                campaign_id=(
                    _optional_uuid(raw_campaign)
                    if raw_campaign not in {"", "auto"}
                    else None
                ),
                auto_campaign=auto_campaign,
                gift_present=(
                    gift_values[index] == "1"
                    if index < len(gift_values)
                    and gift_values[index] in {"0", "1"}
                    else None
                ),
                unit_price_cash=_decimal_value(
                    cash_values[index] if index < len(cash_values) else ""
                ),
                unit_price_card=_decimal_value(
                    card_values[index] if index < len(card_values) else ""
                ),
            )
        )
    payment_type = PaymentType(str(get("payment_type") or "cash"))
    channel_value = str(get("channel") or "")
    card_value = str(get("card_type") or "")
    discount = _decimal_value(
        str(get("dealer_discount_percent") or "10")
    )
    return OfferInput(
        customer_name=str(get("customer_name") or "") or None,
        customer_phone=str(get("customer_phone") or "") or None,
        payment_type=payment_type,
        channel=PaymentChannel(channel_value) if channel_value else None,
        bank_id=_optional_uuid(str(get("bank_id") or "")),
        installment_count=(
            _int_value(str(get("installment_count") or "0"))
            if str(get("installment_count") or "").strip()
            else None
        ),
        card_type=CardType(card_value) if card_value else None,
        dealer_discount_percent=(
            discount if discount is not None else Decimal(10)
        ),
        note=str(get("note") or "") or None,
        items=tuple(items),
    )


def _optional_uuid(value: str | None) -> uuid.UUID | None:
    if not value or not value.strip():
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _int_value(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValidationError("Miktar tam sayı olmalıdır.") from exc


def _decimal_value(value: str) -> Decimal | None:
    if not value or not value.strip():
        return None
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation as exc:
        raise ValidationError("Fiyat değeri geçersiz.") from exc
