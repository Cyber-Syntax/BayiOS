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
from bayios.application.dealer_pricing import get_default_dealer_discount
from bayios.application.errors import NotFoundError, ValidationError
from bayios.application.offers import (
    LineCampaignPreview,
    OfferInput,
    OfferItemInput,
    OfferLinePreview,
    build_offer_profit_summary,
    convert_offer_to_reservation,
    create_offer,
    delete_offer,
    get_offer_detail,
    list_offers,
    preview_offer_comparison,
    preview_offer_line,
    reserve_offer,
    sell_offer,
    set_offer_status,
    update_offer,
)
from bayios.application.offers.io import export_offers_xlsx
from bayios.application.offers.json_io import export_offers_json
from bayios.application.products import search_products
from bayios.domain.commissions import (
    CARD_TYPE_LABELS,
    CHANNEL_LABELS,
    CardType,
    PaymentChannel,
    quantize_money,
)
from bayios.domain.offers import (
    OFFER_STATUS_LABELS,
    PAYMENT_TYPE_LABELS,
    PaymentType,
)
from bayios.web.deps import ActorDep, UnitOfWorkDep
from bayios.web.templating import templates

router = APIRouter(prefix="/offers", tags=["offers"])

MAX_FORM_FIELDS = 10_000

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


@router.get("/export/json")
def export_offers_json_route(
    uow: UnitOfWorkDep,
    status: Annotated[str, Query()] = "",
    q: Annotated[str | None, Query()] = None,
) -> Response:
    selected = status if status in {value for value, _ in STATUS_FILTERS} else ""
    content = export_offers_json(uow, status=selected or None, query=q)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=bayios-teklifler.json"},
    )


@router.get("/new", response_class=HTMLResponse)
def new_offer_page(
    request: Request,
    uow: UnitOfWorkDep,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
) -> HTMLResponse:
    return _render_form(request, uow, offer_id=None, prefill_product_id=product_id)


@router.get("/picker", response_class=HTMLResponse)
def offer_picker(
    request: Request,
    uow: UnitOfWorkDep,
    q: Annotated[str | None, Query()] = None,
    dealer_discount_percent: Annotated[Decimal, Query()] = Decimal(10),
    dealer_discount_cash_percent: Annotated[Decimal, Query()] = Decimal(10),
) -> HTMLResponse:
    products, _ = search_products(uow, query=q, limit=5, offset=0)
    previews = {}
    for product in products:
        preview = preview_offer_line(
            uow,
            product.id,
            dealer_discount_percent=dealer_discount_percent,
            dealer_discount_cash_percent=dealer_discount_cash_percent,
        )
        if preview is not None:
            previews[product.id] = _line_payload(preview)
    return templates.TemplateResponse(
        request,
        "offers/_picker.html",
        {"products": products, "product_previews": previews},
    )


@router.post("")
async def create_offer_route(
    request: Request, uow: UnitOfWorkDep, actor: ActorDep
) -> Response:
    form = await request.form(max_fields=MAX_FORM_FIELDS)
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


@router.post("/compare", response_class=HTMLResponse)
async def compare_offer_route(
    request: Request, uow: UnitOfWorkDep
) -> HTMLResponse:
    form = await request.form(max_fields=MAX_FORM_FIELDS)
    if not any(str(value).strip() for value in form.getlist("product_id")):
        return templates.TemplateResponse(
            request,
            "offers/_comparison.html",
            {"comparison": None, "error": None, "empty": True},
        )
    try:
        data = _offer_input_from_form(form)
        comparison = preview_offer_comparison(uow, data)
    except (ValidationError, ValueError, NotFoundError) as exc:
        return templates.TemplateResponse(
            request,
            "offers/_comparison.html",
            {
                "comparison": None,
                "error": str(exc),
                "empty": False,
                "channel_labels": CHANNEL_LABELS,
            },
        )
    return templates.TemplateResponse(
        request,
        "offers/_comparison.html",
        {
            "comparison": comparison,
            "error": None,
            "empty": False,
            "channel_labels": CHANNEL_LABELS,
        },
    )


@router.get("/{offer_id}", response_class=HTMLResponse)
def offer_detail_page(
    request: Request, offer_id: uuid.UUID, uow: UnitOfWorkDep
) -> HTMLResponse:
    detail = get_offer_detail(uow, offer_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Teklif bulunamadı.")
    external_ids = _offer_external_ids(uow, detail)
    return templates.TemplateResponse(
        request,
        "offers/detail.html",
        {
            "active_nav": "offers",
            "detail": detail,
            "profit_summary": build_offer_profit_summary(detail),
            "display_totals": _offer_display_totals(detail),
            "external_ids": external_ids,
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
    form = await request.form(max_fields=MAX_FORM_FIELDS)
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


@router.post("/{offer_id}/delete")
def delete_offer_route(
    offer_id: uuid.UUID,
    uow: UnitOfWorkDep,
    confirm: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    if confirm != "1":
        return RedirectResponse(
            url=f"/offers/{offer_id}?{urlencode({'msg': 'error:Silme onayı gerekli.'})}",
            status_code=303,
        )
    try:
        delete_offer(uow, offer_id)
    except (ValidationError, NotFoundError) as exc:
        return RedirectResponse(
            url=f"/offers/{offer_id}?{urlencode({'msg': f'error:{exc}'})}",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/offers?{urlencode({'msg': 'deleted'})}", status_code=303
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
            "external_ids": _offer_external_ids(uow, detail),
            "payment_labels": PAYMENT_TYPE_LABELS,
            "channel_labels": CHANNEL_LABELS,
            "generated_at": datetime.now(UTC),
        },
    )


def _preview_payload(preview: LineCampaignPreview) -> dict[str, object]:
    return {
        "key": preview.key,
        "source": preview.source,
        "campaign_id": preview.campaign_id,
        "campaign_name": preview.campaign_name,
        "price": str(preview.price),
        "discount_amount": str(preview.discount_amount),
        "share_amount": str(preview.share_amount),
        "discount_type": preview.discount_type,
        "discount_value": (
            str(preview.discount_value)
            if preview.discount_value is not None
            else None
        ),
        "gift_description": preview.gift_description,
    }


def _line_payload(preview: OfferLinePreview) -> dict[str, object]:
    return {
        "product_id": preview.product_id,
        "product_name": preview.product_name,
        "regular_price": (
            str(preview.regular_price)
            if preview.regular_price is not None
            else None
        ),
        "oliz_price": (
            str(preview.oliz_price)
            if preview.oliz_price is not None
            else None
        ),
        "cost_price": (
            str(preview.cost_price)
            if preview.cost_price is not None
            else None
        ),
        "previews": {
            key: _preview_payload(value)
            for key, value in preview.previews.items()
        },
    }


def _selected_preview(
    previews: dict[str, dict[str, object]], campaign_id: str
) -> dict[str, object]:
    if campaign_id in previews:
        return previews[campaign_id]
    if campaign_id == "" and "none" in previews:
        return previews["none"]
    return previews.get("auto") or previews.get("none") or {}


def _item_from_payload(
    payload: dict[str, object],
    *,
    campaign_id: str,
    quantity: object,
    gift_present: object,
    unit_price_cash: object,
    unit_price_card: object,
) -> dict[str, object]:
    previews = payload.get("previews") or {}
    selected = _selected_preview(previews, campaign_id)  # type: ignore[arg-type]
    return {
        "product_id": payload.get("product_id") or "",
        "product_name": payload.get("product_name") or "",
        "quantity": quantity,
        "campaign_id": campaign_id,
        "gift_present": gift_present,
        "unit_price_cash": unit_price_cash,
        "unit_price_card": unit_price_card,
        "regular_price": payload.get("regular_price"),
        "oliz_price": payload.get("oliz_price"),
        "cost_price": payload.get("cost_price"),
        "previews": previews,
        "campaign_name": selected.get("campaign_name"),
        "campaign_price": selected.get("price"),
        "discount_type": selected.get("discount_type"),
        "discount_value": selected.get("discount_value"),
        "gift_description": selected.get("gift_description"),
        "company_price": selected.get("price"),
        "company_discount": selected.get("discount_amount"),
        "company_share": selected.get("share_amount"),
    }


def _enrich_items_with_previews(
    uow: UnitOfWorkDep,
    items: list[dict[str, object]],
    dealer_discount: Decimal,
    dealer_discount_cash: Decimal,
) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    for item in items:
        product_id = _optional_uuid(str(item.get("product_id") or ""))
        if product_id is None:
            enriched.append(item)
            continue
        preview = preview_offer_line(
            uow,
            product_id,
            dealer_discount_percent=dealer_discount,
            dealer_discount_cash_percent=dealer_discount_cash,
            gift_present=(
                str(item.get("gift_present")) == "1"
                if item.get("gift_present") in {"0", "1"}
                else None
            ),
        )
        if preview is None:
            enriched.append(item)
            continue
        enriched.append(
            _item_from_payload(
                _line_payload(preview),
                campaign_id=(
                    str(item["campaign_id"])
                    if item.get("campaign_id") is not None
                    else "auto"
                ),
                quantity=item.get("quantity") or 1,
                gift_present=item.get("gift_present") or "",
                unit_price_cash=item.get("unit_price_cash") or "",
                unit_price_card=item.get("unit_price_card") or "",
            )
        )
    return enriched


def _detail_initial_items(
    uow: UnitOfWorkDep,
    detail: object,
    dealer_discount: Decimal,
    dealer_discount_cash: Decimal,
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for item in detail.items:
        snapshot = item.campaign_snapshot or {}
        campaign_id = str(snapshot.get("campaign_id") or "")
        preview_payload: dict[str, object] = {}
        if item.product_id is not None:
            preview = preview_offer_line(
                uow,
                item.product_id,
                dealer_discount_percent=dealer_discount,
                dealer_discount_cash_percent=dealer_discount_cash,
                gift_present=item.campaign_gift_present,
            )
            if preview is not None:
                preview_payload = _line_payload(preview)
        base = _item_from_payload(
            preview_payload,
            campaign_id=campaign_id,
            quantity=item.quantity,
            gift_present=(
                "1" if item.campaign_gift_present else "0"
                if item.campaign_gift_present is not None
                else ""
            ),
            unit_price_cash=(
                str(item.unit_price_cash)
                if item.unit_price_cash is not None
                else ""
            ),
            unit_price_card=(
                str(item.unit_price_card)
                if item.unit_price_card is not None
                else ""
            ),
        )
        if not preview_payload:
            base["product_id"] = str(item.product_id) if item.product_id else ""
            base["product_name"] = item.product_name_snapshot
            base["regular_price"] = (
                str(item.regular_price_snapshot)
                if item.regular_price_snapshot is not None
                else None
            )
            base["oliz_price"] = (
                str(item.website_price_snapshot)
                if item.website_price_snapshot is not None
                else None
            )
            base["cost_price"] = (
                str(item.cost_price_snapshot)
                if item.cost_price_snapshot is not None
                else None
            )
        campaign_name = item.campaign_name_snapshot or snapshot.get("name")
        campaign_price = (
            item.campaign_price
            or item.base_price_used
            or snapshot.get("campaign_price")
            or snapshot.get("final_price")
        )
        discount_type = snapshot.get("discount_type")
        discount_value = snapshot.get("discount_value")
        gift_description = snapshot.get("gift_description")
        company_price = item.base_price_used
        company_discount = item.company_discount_amount
        if company_discount is None and item.regular_price_snapshot is not None:
            if company_price is not None:
                company_discount = max(
                    Decimal(0),
                    item.regular_price_snapshot - company_price,
                )
            elif item.website_price_snapshot is not None:
                company_discount = max(
                    Decimal(0),
                    item.regular_price_snapshot - item.website_price_snapshot,
                )
            else:
                company_discount = Decimal(0)
        company_share = item.company_share_amount
        if company_share is None:
            if campaign_price is not None and item.regular_price_snapshot is not None:
                company_share = max(
                    Decimal(0),
                    item.regular_price_snapshot - Decimal(str(campaign_price)),
                )
            elif (
                item.regular_price_snapshot is not None
                and item.website_price_snapshot is not None
            ):
                company_share = max(
                    Decimal(0),
                    item.regular_price_snapshot - item.website_price_snapshot,
                )
            else:
                company_share = Decimal(0)
        base["campaign_id"] = campaign_id
        base["campaign_name"] = campaign_name
        base["campaign_price"] = (
            str(campaign_price) if campaign_price is not None else None
        )
        base["discount_type"] = discount_type
        base["discount_value"] = discount_value
        base["gift_description"] = gift_description
        base["company_price"] = (
            str(company_price) if company_price is not None else None
        )
        base["company_discount"] = str(company_discount)
        base["company_share"] = str(company_share)
        previews = dict(base.get("previews") or {})
        if campaign_id:
            previews[campaign_id] = {
                "key": campaign_id,
                "source": "campaign",
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "price": (
                    str(campaign_price) if campaign_price is not None else None
                ),
                "discount_amount": str(company_discount),
                "share_amount": str(company_share),
                "discount_type": discount_type,
                "discount_value": discount_value,
                "gift_description": gift_description,
            }
        else:
            previews["none"] = {
                "key": "none",
                "source": (
                    "oliz"
                    if item.website_price_snapshot is not None
                    else "none"
                ),
                "campaign_id": None,
                "campaign_name": (
                    "Oliz" if item.website_price_snapshot is not None else None
                ),
                "price": (
                    str(item.website_price_snapshot)
                    if item.website_price_snapshot is not None
                    else (
                        str(item.regular_price_snapshot)
                        if item.regular_price_snapshot is not None
                        else None
                    )
                ),
                "discount_amount": str(company_discount),
                "share_amount": str(company_share),
                "discount_type": None,
                "discount_value": None,
                "gift_description": None,
            }
        base["previews"] = previews
        items.append(base)
    return items


def _offer_external_ids(
    uow: UnitOfWorkDep, detail: object
) -> dict[uuid.UUID, str]:
    product_ids = [
        item.product_id
        for item in detail.items
        if getattr(item, "product_id", None) is not None
    ]
    if not product_ids:
        return {}
    with uow:
        products = uow.products.get_by_ids(product_ids)
    return {
        product.id: product.external_id
        for product in products
        if product.external_id
    }


def _offer_display_totals(detail: object) -> dict[str, Decimal]:
    offer = detail.offer
    if getattr(offer, "pricing_version", "legacy") == "v2":
        return {
            "regular_total": offer.regular_total,
            "oliz_total": offer.oliz_total,
            "company_discount_total": offer.company_discount_total,
            "cost_total": offer.cost_total,
        }
    regular_total = Decimal(0)
    oliz_total = Decimal(0)
    company_discount_total = Decimal(0)
    cost_total = Decimal(0)
    for item in detail.items:
        quantity = item.quantity
        if item.regular_price_snapshot is not None:
            regular_total += item.regular_price_snapshot * quantity
        if item.website_price_snapshot is not None:
            oliz_total += item.website_price_snapshot * quantity
        if item.cost_price_snapshot is not None:
            cost_total += item.cost_price_snapshot * quantity
        if (
            item.regular_price_snapshot is not None
            and item.base_price_used is not None
        ):
            company_discount_total += max(
                Decimal(0),
                item.regular_price_snapshot - item.base_price_used,
            ) * quantity
    return {
        "regular_total": quantize_money(regular_total),
        "oliz_total": quantize_money(oliz_total),
        "company_discount_total": quantize_money(company_discount_total),
        "cost_total": quantize_money(cost_total),
    }


def _render_form(
    request: Request,
    uow: UnitOfWorkDep,
    *,
    offer_id: uuid.UUID | None,
    detail: object | None = None,
    error: str | None = None,
    status_code: int = 200,
    form: object | None = None,
    prefill_product_id: uuid.UUID | None = None,
) -> HTMLResponse:
    campaigns, _ = list_campaigns(uow, state="active", limit=200)
    banks = list_banks(uow)
    products, _ = search_products(uow, query=None, limit=5, offset=0)
    initial_items: list[dict[str, object]] = []
    default_discount = get_default_dealer_discount(uow).default_percent
    values: dict[str, object] = {
        "customer_name": "",
        "customer_phone": "",
        "note": "",
        "payment_type": "cash",
        "channel": "",
        "bank_id": "",
        "installment_count": "",
        "card_type": "",
        "dealer_discount_percent": str(default_discount),
        "dealer_discount_cash_percent": str(default_discount),
        "cash_total_override": "",
        "card_total_override": "",
    }
    if form is None and detail is None and prefill_product_id is not None:
        dealer_discount = _decimal_value(str(values["dealer_discount_percent"])) or Decimal(10)
        dealer_discount_cash = _decimal_value(str(values["dealer_discount_cash_percent"])) or Decimal(10)
        preview = preview_offer_line(
            uow,
            prefill_product_id,
            dealer_discount_percent=dealer_discount,
            dealer_discount_cash_percent=dealer_discount_cash,
        )
        if preview is not None:
            initial_items = [
                _item_from_payload(
                    _line_payload(preview),
                    campaign_id="auto",
                    quantity=1,
                    gift_present="",
                    unit_price_cash="",
                    unit_price_card="",
                )
            ]
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
                "dealer_discount_cash_percent": str(
                    offer.dealer_discount_cash_percent
                ),
                "cash_total_override": (
                    str(offer.cash_total_override)
                    if offer.cash_total_override is not None
                    else ""
                ),
                "card_total_override": (
                    str(offer.card_total_override)
                    if offer.card_total_override is not None
                    else ""
                ),
            }
        )
        dealer_discount = _decimal_value(
            str(values["dealer_discount_percent"])
        ) or Decimal(10)
        dealer_discount_cash = _decimal_value(
            str(values["dealer_discount_cash_percent"])
        ) or Decimal(10)
        initial_items = _detail_initial_items(
            uow,
            detail,
            dealer_discount,
            dealer_discount_cash,
        )
    dealer_discount = _decimal_value(
        str(values["dealer_discount_percent"])
    ) or Decimal(10)
    dealer_discount_cash = _decimal_value(
        str(values["dealer_discount_cash_percent"])
    ) or Decimal(10)
    if form is not None:
        initial_items = _enrich_items_with_previews(
            uow,
            initial_items,
            dealer_discount,
            dealer_discount_cash,
        )
    product_previews = {}
    for product in products:
        preview = preview_offer_line(
            uow,
            product.id,
            dealer_discount_percent=dealer_discount,
            dealer_discount_cash_percent=dealer_discount_cash,
        )
        if preview is not None:
            product_previews[product.id] = _line_payload(preview)
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
            "product_previews": product_previews,
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
        "dealer_discount_cash_percent": str(
            get("dealer_discount_cash_percent")
            or get("dealer_discount_percent")
            or "10"
        ),
        "cash_total_override": str(get("cash_total_override") or ""),
        "card_total_override": str(get("card_total_override") or ""),
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
    cash_discount = _decimal_value(
        str(
            get("dealer_discount_cash_percent")
            or get("dealer_discount_percent")
            or "10"
        )
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
        dealer_discount_cash_percent=(
            cash_discount if cash_discount is not None else Decimal(10)
        ),
        note=str(get("note") or "") or None,
        cash_total_override=_decimal_value(
            str(get("cash_total_override") or "")
        ),
        card_total_override=_decimal_value(
            str(get("card_total_override") or "")
        ),
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
