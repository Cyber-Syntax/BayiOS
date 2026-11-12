from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from bayios.application.campaigns import (
    CampaignInput,
    CampaignProductInput,
    archive_campaign,
    create_campaign,
    get_campaign_detail,
    list_campaigns,
    update_campaign,
)
from bayios.application.campaigns.io import (
    export_campaign_products_xlsx,
    export_campaigns_xlsx,
)
from bayios.application.dealer_pricing import (
    get_default_dealer_discount,
    update_default_dealer_discount,
)
from bayios.application.errors import NotFoundError, ValidationError
from bayios.application.products import get_product, search_products
from bayios.domain.campaigns import (
    BASE_PRICE_TYPE_LABELS,
    CAMPAIGN_TYPE_LABELS,
    DISCOUNT_TYPE_LABELS,
    PRODUCT_RELATION_TYPE_LABELS,
    BasePriceType,
    CampaignType,
    DiscountType,
    ProductRelationType,
)
from bayios.web.deps import ActorDep, UnitOfWorkDep
from bayios.web.templating import templates

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

TYPE_FILTERS = (("", "Tümü"),) + tuple(
    (campaign_type.value, CAMPAIGN_TYPE_LABELS[campaign_type])
    for campaign_type in CampaignType
)
STATE_FILTERS = (
    ("active", "Aktif / Yaklaşan"),
    ("history", "Geçmiş"),
    ("", "Tümü"),
)
TYPE_OPTIONS = tuple(
    (campaign_type.value, CAMPAIGN_TYPE_LABELS[campaign_type])
    for campaign_type in CampaignType
)
BASE_PRICE_OPTIONS = tuple(
    (base.value, BASE_PRICE_TYPE_LABELS[base]) for base in BasePriceType
)
DISCOUNT_TYPE_OPTIONS = tuple(
    (discount.value, DISCOUNT_TYPE_LABELS[discount]) for discount in DiscountType
)
RELATION_TYPE_OPTIONS = tuple(
    (relation.value, PRODUCT_RELATION_TYPE_LABELS[relation])
    for relation in ProductRelationType
)
GIFT_BASE_PRICE_OPTIONS = (("", "Varsayılan"),) + BASE_PRICE_OPTIONS
TEXT_FIELDS = (
    "name",
    "description",
    "campaign_type",
    "starts_at",
    "ends_at",
    "base_price_type",
    "discount_type",
    "discount_value",
    "gift_description",
    "gift_yes_base_price_type",
    "gift_no_base_price_type",
    "employee_note",
)
_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%d.%m.%y", "%d-%m-%y")


@router.get("", response_class=HTMLResponse)
def list_campaigns_route(
    request: Request,
    uow: UnitOfWorkDep,
    q: Annotated[str | None, Query()] = None,
    campaign_type: Annotated[str, Query()] = "",
    state: Annotated[str, Query()] = "active",
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query()] = 1,
    limit: Annotated[int, Query()] = 25,
) -> HTMLResponse:
    page = max(1, page)
    limit = max(1, limit)
    selected_type = (
        campaign_type
        if campaign_type in {value for value, _ in TYPE_FILTERS}
        else ""
    )
    selected_state = (
        state if state in {value for value, _ in STATE_FILTERS} else "active"
    )
    error = None
    try:
        from_moment = _parse_date(date_from)
        to_moment = _parse_date(date_to)
    except ValidationError as exc:
        error = str(exc)
        from_moment = None
        to_moment = None

    offset = (page - 1) * limit
    rows, total_count = list_campaigns(
        uow,
        query=q,
        campaign_type=selected_type or None,
        state=selected_state or None,
        date_from=from_moment,
        date_to=to_moment,
        limit=limit,
        offset=offset,
    )
    total_pages = max(1, math.ceil(total_count / limit))
    if page > total_pages:
        page = total_pages
        offset = (page - 1) * limit
        rows, total_count = list_campaigns(
            uow,
            query=q,
            campaign_type=selected_type or None,
            state=selected_state or None,
            date_from=from_moment,
            date_to=to_moment,
            limit=limit,
            offset=offset,
        )

    context = {
        "active_nav": "campaigns",
        "rows": rows,
        "q": q or "",
        "campaign_type": selected_type,
        "state": selected_state,
        "date_from": date_from or "",
        "date_to": date_to or "",
        "type_filters": TYPE_FILTERS,
        "state_filters": STATE_FILTERS,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "total_count": total_count,
        "error": error,
        "dealer_setting": get_default_dealer_discount(uow),
    }
    if request.headers.get("HX-Request") and not request.headers.get("HX-Boosted"):
        return templates.TemplateResponse(
            request, "campaigns/_results.html", context
        )
    return templates.TemplateResponse(request, "campaigns/list.html", context)


@router.get("/print", response_class=HTMLResponse)
def print_list_route(
    request: Request,
    uow: UnitOfWorkDep,
    q: Annotated[str | None, Query()] = None,
    campaign_type: Annotated[str, Query()] = "",
    state: Annotated[str, Query()] = "active",
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    selected_type = (
        campaign_type
        if campaign_type in {value for value, _ in TYPE_FILTERS}
        else ""
    )
    selected_state = (
        state if state in {value for value, _ in STATE_FILTERS} else "active"
    )
    try:
        from_moment = _parse_date(date_from)
        to_moment = _parse_date(date_to)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rows, _ = list_campaigns(
        uow,
        query=q,
        campaign_type=selected_type or None,
        state=selected_state or None,
        date_from=from_moment,
        date_to=to_moment,
        limit=10_000,
        offset=0,
    )
    return templates.TemplateResponse(
        request,
        "campaigns/print_list.html",
        {
            "active_nav": "campaigns",
            "rows": rows,
            "q": q or "",
            "campaign_type": selected_type,
            "state": selected_state,
            "date_from": date_from or "",
            "date_to": date_to or "",
            "generated_at": datetime.now(UTC),
        },
    )


@router.get("/export/xlsx")
def export_campaigns_route(
    uow: UnitOfWorkDep,
    q: Annotated[str | None, Query()] = None,
    campaign_type: Annotated[str, Query()] = "",
    state: Annotated[str, Query()] = "active",
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
) -> Response:
    selected_type = (
        campaign_type
        if campaign_type in {value for value, _ in TYPE_FILTERS}
        else ""
    )
    selected_state = (
        state if state in {value for value, _ in STATE_FILTERS} else "active"
    )
    try:
        from_moment = _parse_date(date_from)
        to_moment = _parse_date(date_to)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    content = export_campaigns_xlsx(
        uow,
        query=q,
        campaign_type=selected_type or None,
        state=selected_state or None,
        date_from=from_moment,
        date_to=to_moment,
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=bayios-kampanyalar.xlsx"},
    )


@router.get("/{campaign_id}/export/xlsx")
def export_campaign_detail_route(
    campaign_id: uuid.UUID,
    uow: UnitOfWorkDep,
) -> Response:
    try:
        content = export_campaign_products_xlsx(uow, campaign_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename=bayios-kampanya-{campaign_id}.xlsx"
            )
        },
    )


@router.post("/dealer-discount")
def update_dealer_discount_route(
    uow: UnitOfWorkDep,
    default_percent: Annotated[str, Form()],
    note: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    try:
        percent = _parse_decimal(default_percent)
        if percent is None:
            raise ValidationError("Varsayılan oran zorunludur.")
        update_default_dealer_discount(uow, percent, note=note)
    except (ValidationError, ValueError) as exc:
        query = urlencode({"msg": f"error:{exc}"})
        return RedirectResponse(url=f"/campaigns?{query}", status_code=303)
    query = urlencode({"msg": "dealer_discount_updated"})
    return RedirectResponse(url=f"/campaigns?{query}", status_code=303)


@router.get("/new", response_class=HTMLResponse)
def new_campaign_page(
    request: Request,
    uow: UnitOfWorkDep,
    q: Annotated[str | None, Query()] = None,
    product_id: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    selected: list[dict[str, object]] = []
    parsed_product = _optional_uuid(product_id)
    if parsed_product is not None:
        product = get_product(uow, parsed_product)
        if product is not None:
            selected.append(
                {
                    "product_id": str(product.id),
                    "product_name": product.name,
                    "relation_type": ProductRelationType.RELATED.value,
                    "quantity_required": "",
                }
            )
    return _render_form(
        request,
        uow,
        campaign_id=None,
        selected_products=selected,
        q=q,
    )


@router.get("/picker", response_class=HTMLResponse)
def product_picker(
    request: Request,
    uow: UnitOfWorkDep,
    q: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    products, _ = search_products(uow, query=q, limit=20, offset=0)
    return templates.TemplateResponse(
        request,
        "campaigns/_product_picker.html",
        {"products": products, "q": q or ""},
    )


@router.post("")
async def create_campaign_route(
    request: Request,
    uow: UnitOfWorkDep,
    actor: ActorDep,
) -> Response:
    form = await request.form()
    try:
        data = _campaign_input_from_form(form)
        campaign_id = create_campaign(uow, data, actor)
    except (ValidationError, ValueError) as exc:
        values, selected = _form_state_from_form(uow, form)
        return _render_form(
            request,
            uow,
            campaign_id=None,
            values=values,
            selected_products=selected,
            error=str(exc),
            status_code=400,
        )
    return _redirect(campaign_id, "created")


@router.get("/{campaign_id}", response_class=HTMLResponse)
def campaign_detail_page(
    request: Request,
    campaign_id: uuid.UUID,
    uow: UnitOfWorkDep,
    product_id: Annotated[str | None, Query()] = None,
    dealer_percent: Annotated[str | None, Query()] = None,
    msg: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    return _render_detail(
        request,
        uow,
        campaign_id,
        product_id=_optional_uuid(product_id),
        dealer_percent=_parse_decimal(dealer_percent),
        msg=msg,
    )


@router.get("/{campaign_id}/scenario", response_class=HTMLResponse)
def scenario_panel(
    request: Request,
    campaign_id: uuid.UUID,
    uow: UnitOfWorkDep,
    product_id: Annotated[str | None, Query()] = None,
    dealer_percent: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    parsed_product = _optional_uuid(product_id)
    parsed_percent = _parse_decimal(dealer_percent)
    error = None
    try:
        detail = get_campaign_detail(
            uow,
            campaign_id,
            product_id=parsed_product,
            dealer_percent=parsed_percent,
        )
    except ValidationError as exc:
        detail = get_campaign_detail(
            uow, campaign_id, product_id=parsed_product
        )
        error = str(exc)
    if detail is None:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadı.")
    return templates.TemplateResponse(
        request,
        "campaigns/_scenario_panel.html",
        {
            "campaign": detail,
            "dealer_percent_input": f"{detail.dealer_percent:.2f}",
            "base_price_labels": BASE_PRICE_TYPE_LABELS,
            "error": error,
        },
    )


@router.get("/{campaign_id}/print", response_class=HTMLResponse)
def print_detail_route(
    request: Request,
    campaign_id: uuid.UUID,
    uow: UnitOfWorkDep,
) -> HTMLResponse:
    detail = get_campaign_detail(uow, campaign_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadı.")
    return templates.TemplateResponse(
        request,
        "campaigns/print_detail.html",
        {
            "active_nav": "campaigns",
            "campaign": detail,
            "base_price_labels": BASE_PRICE_TYPE_LABELS,
            "generated_at": datetime.now(UTC),
        },
    )


@router.get("/{campaign_id}/edit", response_class=HTMLResponse)
def edit_campaign_page(
    request: Request,
    campaign_id: uuid.UUID,
    uow: UnitOfWorkDep,
) -> HTMLResponse:
    detail = get_campaign_detail(uow, campaign_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadı.")
    values, selected = _edit_form_state(detail)
    return _render_form(
        request,
        uow,
        campaign_id=campaign_id,
        values=values,
        selected_products=selected,
    )


@router.post("/{campaign_id}/edit")
async def update_campaign_route(
    request: Request,
    campaign_id: uuid.UUID,
    uow: UnitOfWorkDep,
    actor: ActorDep,
) -> Response:
    form = await request.form()
    try:
        data = _campaign_input_from_form(form)
        update_campaign(uow, campaign_id, data, actor)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValidationError, ValueError) as exc:
        values, selected = _form_state_from_form(uow, form)
        return _render_form(
            request,
            uow,
            campaign_id=campaign_id,
            values=values,
            selected_products=selected,
            error=str(exc),
            status_code=400,
        )
    return _redirect(campaign_id, "updated")


@router.post("/{campaign_id}/archive")
def archive_campaign_route(
    campaign_id: uuid.UUID,
    uow: UnitOfWorkDep,
) -> RedirectResponse:
    try:
        archive_campaign(uow, campaign_id, archived=True)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _redirect(campaign_id, "archived")


@router.post("/{campaign_id}/restore")
def restore_campaign_route(
    campaign_id: uuid.UUID,
    uow: UnitOfWorkDep,
) -> RedirectResponse:
    try:
        archive_campaign(uow, campaign_id, archived=False)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _redirect(campaign_id, "restored")


def _campaign_input_from_form(form: object) -> CampaignInput:
    get = form.get  # type: ignore[attr-defined]
    name = str(get("name") or "")
    campaign_type = _parse_enum(
        CampaignType,
        str(get("campaign_type") or ""),
        CampaignType.GENERAL,
        "kampanya tipi",
    )
    starts_at = _require_date(get("starts_at"), "Başlangıç tarihi")
    ends_at = _require_date(get("ends_at"), "Bitiş tarihi")
    base_price_type = _parse_enum(
        BasePriceType,
        str(get("base_price_type") or ""),
        BasePriceType.REGULAR,
        "fiyat tabanı",
    )
    discount_type = _parse_enum(
        DiscountType,
        str(get("discount_type") or ""),
        DiscountType.INFO_ONLY,
        "indirim türü",
    )
    return CampaignInput(
        name=name,
        campaign_type=campaign_type,
        starts_at=starts_at,
        ends_at=ends_at,
        base_price_type=base_price_type,
        description=str(get("description") or "") or None,
        discount_type=discount_type,
        discount_value=_parse_decimal(get("discount_value")),
        gift_description=str(get("gift_description") or "") or None,
        gift_optional=_parse_bool(get("gift_optional")),
        gift_yes_base_price_type=_parse_optional_enum(
            BasePriceType, get("gift_yes_base_price_type")
        ),
        gift_no_base_price_type=_parse_optional_enum(
            BasePriceType, get("gift_no_base_price_type")
        ),
        employee_note=str(get("employee_note") or "") or None,
        products=_parse_product_inputs(form),
    )


def _parse_product_inputs(form: object) -> tuple[CampaignProductInput, ...]:
    product_ids = [str(value) for value in form.getlist("product_id")]  # type: ignore[attr-defined]
    relations = [str(value) for value in form.getlist("relation_type")]  # type: ignore[attr-defined]
    quantities = [str(value) for value in form.getlist("quantity_required")]  # type: ignore[attr-defined]
    items: list[CampaignProductInput] = []
    for index, raw_id in enumerate(product_ids):
        if not raw_id.strip():
            continue
        product_id = _optional_uuid(raw_id)
        if product_id is None:
            raise ValidationError("Geçersiz ürün seçimi.")
        relation = _parse_enum(
            ProductRelationType,
            relations[index] if index < len(relations) else "",
            ProductRelationType.RELATED,
            "ürün ilişkisi",
        )
        quantity = _parse_optional_int(
            quantities[index] if index < len(quantities) else None
        )
        items.append(
            CampaignProductInput(
                product_id=product_id,
                relation_type=relation,
                quantity_required=quantity,
            )
        )
    return tuple(items)


def _form_state_from_form(
    uow: UnitOfWorkDep, form: object
) -> tuple[dict[str, object], list[dict[str, object]]]:
    values = _empty_form_values()
    for field in TEXT_FIELDS:
        values[field] = str(form.get(field) or "")  # type: ignore[attr-defined]
    values["gift_optional"] = _parse_bool(
        form.get("gift_optional")  # type: ignore[attr-defined]
    )
    return values, _selected_products_from_form(uow, form)


def _selected_products_from_form(
    uow: UnitOfWorkDep, form: object
) -> list[dict[str, object]]:
    product_ids = [str(value) for value in form.getlist("product_id")]  # type: ignore[attr-defined]
    relations = [str(value) for value in form.getlist("relation_type")]  # type: ignore[attr-defined]
    quantities = [str(value) for value in form.getlist("quantity_required")]  # type: ignore[attr-defined]
    selected: list[dict[str, object]] = []
    for index, raw_id in enumerate(product_ids):
        product_id = _optional_uuid(raw_id)
        if product_id is None:
            continue
        product = get_product(uow, product_id)
        selected.append(
            {
                "product_id": str(product_id),
                "product_name": product.name if product is not None else raw_id,
                "relation_type": (
                    relations[index]
                    if index < len(relations)
                    else ProductRelationType.RELATED.value
                ),
                "quantity_required": (
                    quantities[index] if index < len(quantities) else ""
                ),
            }
        )
    return selected


def _edit_form_state(
    detail: object,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    version = detail.current_version  # type: ignore[attr-defined]
    values: dict[str, object] = {
        "name": version.name,
        "description": version.description or "",
        "campaign_type": version.campaign_type,
        "starts_at": _iso_input(version.starts_at),
        "ends_at": _iso_input(version.ends_at),
        "base_price_type": version.base_price_type,
        "discount_type": version.discount_type,
        "discount_value": (
            str(version.discount_value)
            if version.discount_value is not None
            else ""
        ),
        "gift_description": version.gift_description or "",
        "gift_optional": version.gift_optional,
        "gift_yes_base_price_type": version.gift_yes_base_price_type or "",
        "gift_no_base_price_type": version.gift_no_base_price_type or "",
        "employee_note": version.employee_note or "",
    }
    selected = [
        {
            "product_id": str(product.product_id) if product.product_id else "",
            "product_name": product.product_name,
            "relation_type": product.relation_type,
            "quantity_required": (
                product.quantity_required
                if product.quantity_required is not None
                else ""
            ),
        }
        for product in version.products
    ]
    return values, selected


def _empty_form_values() -> dict[str, object]:
    return {
        "name": "",
        "description": "",
        "campaign_type": CampaignType.GENERAL.value,
        "starts_at": "",
        "ends_at": "",
        "base_price_type": BasePriceType.REGULAR.value,
        "discount_type": DiscountType.INFO_ONLY.value,
        "discount_value": "",
        "gift_description": "",
        "gift_optional": False,
        "gift_yes_base_price_type": "",
        "gift_no_base_price_type": "",
        "employee_note": "",
    }


def _render_form(
    request: Request,
    uow: UnitOfWorkDep,
    *,
    campaign_id: uuid.UUID | None,
    values: dict[str, object] | None = None,
    selected_products: list[dict[str, object]] | None = None,
    q: str | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    products, _ = search_products(uow, query=q, limit=20, offset=0)
    return templates.TemplateResponse(
        request,
        "campaigns/form.html",
        {
            "active_nav": "campaigns",
            "mode": "edit" if campaign_id is not None else "new",
            "campaign_id": campaign_id,
            "values": values or _empty_form_values(),
            "selected_products": selected_products or [],
            "products": products,
            "q": q or "",
            "type_options": TYPE_OPTIONS,
            "base_price_options": BASE_PRICE_OPTIONS,
            "discount_type_options": DISCOUNT_TYPE_OPTIONS,
            "relation_type_options": RELATION_TYPE_OPTIONS,
            "gift_base_price_options": GIFT_BASE_PRICE_OPTIONS,
            "error": error,
        },
        status_code=status_code,
    )


def _render_detail(
    request: Request,
    uow: UnitOfWorkDep,
    campaign_id: uuid.UUID,
    *,
    product_id: uuid.UUID | None = None,
    dealer_percent: Decimal | None = None,
    msg: str | None = None,
) -> HTMLResponse:
    error = None
    try:
        detail = get_campaign_detail(
            uow,
            campaign_id,
            product_id=product_id,
            dealer_percent=dealer_percent,
        )
    except ValidationError as exc:
        detail = get_campaign_detail(
            uow, campaign_id, product_id=product_id
        )
        error = str(exc)
    if detail is None:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadı.")
    return templates.TemplateResponse(
        request,
        "campaigns/detail.html",
        {
            "active_nav": "campaigns",
            "campaign": detail,
            "dealer_percent_input": f"{detail.dealer_percent:.2f}",
            "base_price_labels": BASE_PRICE_TYPE_LABELS,
            "msg": msg,
            "error": error,
            "today": datetime.now(UTC).date().isoformat(),
        },
    )


def _redirect(campaign_id: uuid.UUID, msg: str) -> RedirectResponse:
    query = urlencode({"msg": msg})
    return RedirectResponse(
        url=f"/campaigns/{campaign_id}?{query}", status_code=303
    )


def _parse_date(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    text = value.strip()
    for date_format in _DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValidationError("Tarih GG.AA.YYYY biçiminde olmalıdır.")


def _require_date(value: str | None, label: str) -> datetime:
    parsed = _parse_date(value)
    if parsed is None:
        raise ValidationError(f"{label} zorunludur.")
    return parsed


def _parse_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValidationError("Sayısal değer geçersiz.") from exc


def _parse_optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise ValidationError("Miktar tam sayı olmalıdır.") from exc
    if parsed <= 0:
        raise ValidationError("Miktar sıfırdan büyük olmalıdır.")
    return parsed


def _parse_bool(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "on", "yes"}


def _parse_enum[E: StrEnum](
    enum_type: type[E],
    value: str,
    default: E,
    label: str,
) -> E:
    if not value:
        return default
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValidationError(f"Geçersiz {label}.") from exc


def _parse_optional_enum[E: StrEnum](
    enum_type: type[E], value: object
) -> E | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return enum_type(text)
    except ValueError as exc:
        raise ValidationError("Geçersiz fiyat tabanı.") from exc


def _optional_uuid(value: str | None) -> uuid.UUID | None:
    if not value or not value.strip():
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _iso_input(value: datetime) -> str:
    if value.tzinfo is None:
        return value.strftime("%Y-%m-%d")
    return value.astimezone(UTC).strftime("%Y-%m-%d")
