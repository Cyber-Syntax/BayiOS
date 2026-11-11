from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from bayios.application.commissions import (
    CommissionRateInput,
    activate_commission_period,
    add_commission_limit,
    add_commission_rate,
    create_commission_period,
    deactivate_commission_period,
    delete_commission_limit,
    delete_commission_period,
    delete_commission_rate,
    get_commission_period_detail,
    list_commission_periods,
    update_commission_limit,
    update_commission_rate,
)
from bayios.application.errors import NotFoundError, ValidationError
from bayios.domain.commissions import (
    CARD_TYPE_LABELS,
    CHANNEL_LABELS,
    ODERO_TIER_LABELS,
    PERIOD_STATUS_LABELS,
    PRODUCT_GROUP_LABELS,
    CardType,
    OderoTier,
    PaymentChannel,
    ProductCommissionGroup,
)
from bayios.domain.commissions import (
    CommissionLimit as DomainLimit,
)
from bayios.web.deps import UnitOfWorkDep
from bayios.web.templating import templates

router = APIRouter(prefix="/commissions", tags=["commissions"])


@router.get("", response_class=HTMLResponse)
def commission_periods_page(
    request: Request, uow: UnitOfWorkDep
) -> HTMLResponse:
    periods = list_commission_periods(uow)
    return templates.TemplateResponse(
        request,
        "commissions/list.html",
        {
            "active_nav": "commissions",
            "periods": periods,
            "status_labels": PERIOD_STATUS_LABELS,
            "now": datetime.now(UTC),
        },
    )


@router.post("")
def create_period_route(
    uow: UnitOfWorkDep,
    year: Annotated[str, Form()],
    month: Annotated[str, Form()],
    copy_from_id: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    try:
        period = create_commission_period(
            uow,
            int(year),
            int(month),
            copy_from_id=_optional_uuid(copy_from_id),
        )
    except (ValueError, ValidationError) as exc:
        return RedirectResponse(
            url=f"/commissions?{urlencode({'msg': f'error:{exc}'})}",
            status_code=303,
        )
    return RedirectResponse(url=f"/commissions/{period.id}", status_code=303)


@router.get("/{period_id}", response_class=HTMLResponse)
def commission_period_detail_page(
    request: Request, period_id: uuid.UUID, uow: UnitOfWorkDep
) -> HTMLResponse:
    detail = get_commission_period_detail(uow, period_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Komisyon dönemi bulunamadı.")
    return templates.TemplateResponse(
        request,
        "commissions/detail.html",
        {
            "active_nav": "commissions",
            "detail": detail,
            "status_labels": PERIOD_STATUS_LABELS,
            "channel_labels": {
                value: label
                for value, label in (
                    (item.value, CHANNEL_LABELS[item])
                    for item in PaymentChannel
                )
            },
            "group_labels": {
                value: label
                for value, label in (
                    (item.value, PRODUCT_GROUP_LABELS[item])
                    for item in ProductCommissionGroup
                )
            },
            "card_labels": {
                value: label
                for value, label in (
                    (item.value, CARD_TYPE_LABELS[item]) for item in CardType
                )
            },
            "tier_labels": {
                value: label
                for value, label in (
                    (item.value, ODERO_TIER_LABELS[item]) for item in OderoTier
                )
            },
            "bank_names": {
                str(bank.id): bank.name for bank in detail.banks
            },
            "channel_options": tuple(
                (item.value, CHANNEL_LABELS[item]) for item in PaymentChannel
            ),
            "group_options": tuple(
                (item.value, PRODUCT_GROUP_LABELS[item])
                for item in ProductCommissionGroup
            ),
            "card_options": tuple(
                (item.value, CARD_TYPE_LABELS[item]) for item in CardType
            ),
            "tier_options": tuple(
                (item.value, ODERO_TIER_LABELS[item]) for item in OderoTier
            ),
            "msg": request.query_params.get("msg"),
        },
    )


@router.post("/{period_id}/activate")
def activate_period_route(
    period_id: uuid.UUID, uow: UnitOfWorkDep
) -> RedirectResponse:
    try:
        activate_commission_period(uow, period_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse(
        url=f"/commissions/{period_id}?{urlencode({'msg': 'activated'})}",
        status_code=303,
    )


@router.post("/{period_id}/rates")
def add_rate_route(
    period_id: uuid.UUID,
    uow: UnitOfWorkDep,
    channel: Annotated[str, Form()],
    installment_count: Annotated[str, Form()],
    commission_percent: Annotated[str, Form()],
    product_group: Annotated[str | None, Form()] = None,
    bank_id: Annotated[str | None, Form()] = None,
    amount_tier: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    try:
        item = CommissionRateInput(
            channel=PaymentChannel(channel),
            bank_id=_optional_uuid(bank_id),
            product_group=(
                ProductCommissionGroup(product_group) if product_group else None
            ),
            installment_count=_required_int(installment_count),
            commission_percent=_required_decimal(commission_percent),
            amount_tier=(
                OderoTier(amount_tier) if amount_tier else None
            ),
        )
        add_commission_rate(uow, period_id, item)
    except (ValueError, ValidationError, NotFoundError) as exc:
        return _redirect_error(period_id, exc)
    return RedirectResponse(
        url=f"/commissions/{period_id}?{urlencode({'msg': 'rate_added'})}",
        status_code=303,
    )


@router.post("/{period_id}/rates/{rate_id}/edit")
def update_rate_route(
    period_id: uuid.UUID,
    rate_id: uuid.UUID,
    uow: UnitOfWorkDep,
    commission_percent: Annotated[str, Form()],
) -> RedirectResponse:
    try:
        update_commission_rate(
            uow,
            period_id,
            rate_id,
            _required_decimal(commission_percent),
        )
    except (ValueError, ValidationError, NotFoundError) as exc:
        return _redirect_error(period_id, exc)
    return RedirectResponse(
        url=f"/commissions/{period_id}?{urlencode({'msg': 'rate_updated'})}",
        status_code=303,
    )


@router.post("/{period_id}/rates/{rate_id}/delete")
def delete_rate_route(
    period_id: uuid.UUID, rate_id: uuid.UUID, uow: UnitOfWorkDep
) -> RedirectResponse:
    try:
        delete_commission_rate(uow, period_id, rate_id)
    except (ValidationError, NotFoundError) as exc:
        return _redirect_error(period_id, exc)
    return RedirectResponse(
        url=f"/commissions/{period_id}?{urlencode({'msg': 'rate_deleted'})}",
        status_code=303,
    )


@router.post("/{period_id}/limits")
def add_limit_route(
    period_id: uuid.UUID,
    uow: UnitOfWorkDep,
    max_installments: Annotated[str, Form()],
    channel: Annotated[str | None, Form()] = None,
    bank_id: Annotated[str | None, Form()] = None,
    product_group: Annotated[str | None, Form()] = None,
    card_type: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    try:
        limit = DomainLimit(
            max_installments=_required_int(max_installments),
            channel=PaymentChannel(channel) if channel else None,
            bank_id=str(_optional_uuid(bank_id)) if bank_id else None,
            product_group=(
                ProductCommissionGroup(product_group) if product_group else None
            ),
            card_type=CardType(card_type) if card_type else None,
        )
        add_commission_limit(uow, period_id, limit)
    except (ValueError, ValidationError, NotFoundError) as exc:
        return _redirect_error(period_id, exc)
    return RedirectResponse(
        url=f"/commissions/{period_id}?{urlencode({'msg': 'limit_added'})}",
        status_code=303,
    )


@router.post("/{period_id}/deactivate")
def deactivate_period_route(
    period_id: uuid.UUID, uow: UnitOfWorkDep
) -> RedirectResponse:
    try:
        deactivate_commission_period(uow, period_id)
    except (NotFoundError, ValidationError) as exc:
        return _redirect_error(period_id, exc)
    return RedirectResponse(
        url=f"/commissions/{period_id}?{urlencode({'msg': 'deactivated'})}",
        status_code=303,
    )


@router.post("/{period_id}/delete")
def delete_period_route(
    period_id: uuid.UUID, uow: UnitOfWorkDep
) -> RedirectResponse:
    try:
        delete_commission_period(uow, period_id)
    except (NotFoundError, ValidationError) as exc:
        return RedirectResponse(
            url=f"/commissions?{urlencode({'msg': f'error:{exc}'})}",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/commissions?{urlencode({'msg': 'deleted'})}",
        status_code=303,
    )


@router.post("/{period_id}/limits/{limit_id}/edit")
def update_limit_route(
    period_id: uuid.UUID,
    limit_id: uuid.UUID,
    uow: UnitOfWorkDep,
    max_installments: Annotated[str, Form()],
) -> RedirectResponse:
    try:
        update_commission_limit(
            uow,
            period_id,
            limit_id,
            _required_int(max_installments),
        )
    except (ValueError, ValidationError, NotFoundError) as exc:
        return _redirect_error(period_id, exc)
    return RedirectResponse(
        url=f"/commissions/{period_id}?{urlencode({'msg': 'limit_updated'})}",
        status_code=303,
    )


@router.post("/{period_id}/limits/{limit_id}/delete")
def delete_limit_route(
    period_id: uuid.UUID, limit_id: uuid.UUID, uow: UnitOfWorkDep
) -> RedirectResponse:
    try:
        delete_commission_limit(uow, period_id, limit_id)
    except (ValidationError, NotFoundError) as exc:
        return _redirect_error(period_id, exc)
    return RedirectResponse(
        url=f"/commissions/{period_id}?{urlencode({'msg': 'limit_deleted'})}",
        status_code=303,
    )


def _redirect_error(period_id: uuid.UUID, exc: Exception) -> RedirectResponse:
    return RedirectResponse(
        url=f"/commissions/{period_id}?{urlencode({'msg': f'error:{exc}'})}",
        status_code=303,
    )


def _optional_uuid(value: str | None) -> uuid.UUID | None:
    if not value or not value.strip():
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValidationError("Geçersiz banka seçimi.") from exc


def _required_int(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValidationError("Taksit sayısı tam sayı olmalıdır.") from exc


def _required_decimal(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", ".").strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValidationError("Komisyon oranı geçersiz.") from exc
