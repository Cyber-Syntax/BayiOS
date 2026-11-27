from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from bayios.adapters.db.models.campaigns import (
    DealerDiscountSetting,
    DealerDiscountSettingHistory,
    DealerPricing,
    DealerPricingHistory,
)
from bayios.application.errors import NotFoundError, ValidationError
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.domain.dealer_pricing import (
    DEFAULT_DEALER_DISCOUNT_PERCENT,
    validate_dealer_percent,
    validate_floor_prices,
)
from bayios.domain.products import ActorContext


@dataclass(frozen=True)
class DealerPricingHistoryView:
    old_cash_floor: Decimal | None
    new_cash_floor: Decimal | None
    old_card_floor: Decimal | None
    new_card_floor: Decimal | None
    note: str | None
    changed_at: datetime
    changed_by_name: str | None


@dataclass(frozen=True)
class DealerPricingView:
    product_id: uuid.UUID
    cash_floor_price: Decimal | None
    card_floor_price: Decimal | None
    note: str | None
    updated_at: datetime | None
    updated_by_name: str | None
    history: tuple[DealerPricingHistoryView, ...]


@dataclass(frozen=True)
class DealerDiscountSettingHistoryView:
    old_percent: Decimal
    new_percent: Decimal
    note: str | None
    changed_at: datetime
    changed_by_name: str | None


@dataclass(frozen=True)
class DealerDiscountSettingView:
    default_percent: Decimal
    updated_at: datetime | None
    updated_by_name: str | None
    history: tuple[DealerDiscountSettingHistoryView, ...]


def get_dealer_pricing(
    uow: UnitOfWork,
    product_id: uuid.UUID,
    *,
    limit: int = 50,
) -> DealerPricingView | None:
    with uow:
        product = uow.products.get_by_id(product_id)
        if product is None:
            return None
        pricing = uow.dealer_pricing.get(product_id)
        history = uow.dealer_pricing.get_history(product_id, limit)
        return _pricing_view(product_id, pricing, history)


def update_dealer_pricing(
    uow: UnitOfWork,
    product_id: uuid.UUID,
    cash_floor_price: Decimal | None,
    card_floor_price: Decimal | None,
    note: str | None = None,
    actor: ActorContext | None = None,
) -> DealerPricingView:
    actor = actor or ActorContext()
    now = datetime.now(UTC)
    try:
        cash, card = validate_floor_prices(cash_floor_price, card_floor_price)
    except ValueError as exc:
        raise ValidationError(
            "Nakit ve kart taban fiyatları negatif olamaz."
        ) from exc

    with uow:
        product = uow.products.get_by_id(product_id)
        if product is None:
            raise NotFoundError("Ürün bulunamadı.")

        pricing = apply_dealer_pricing_values(
            uow,
            product_id=product_id,
            cash_floor_price=cash,
            card_floor_price=card,
            note=note,
            actor=actor,
            now=now,
        )
        uow.commit()
        history = uow.dealer_pricing.get_history(product_id)
        return _pricing_view(product_id, pricing, history)


def apply_dealer_pricing_values(
    uow: UnitOfWork,
    *,
    product_id: uuid.UUID,
    cash_floor_price: Decimal | None,
    card_floor_price: Decimal | None,
    note: str | None,
    actor: ActorContext,
    now: datetime,
) -> DealerPricing:
    """Apply cash/card floor prices inside an active unit of work.

    The caller owns the transaction; this helper never commits. It is shared by
    the manual form and the Excel import so both write identical history rows.
    """
    pricing = uow.dealer_pricing.get_for_update(product_id)
    clean_note = _clean_text(note)
    if pricing is None:
        pricing = DealerPricing(
            id=uuid.uuid4(),
            product_id=product_id,
            cash_floor_price=cash_floor_price,
            card_floor_price=card_floor_price,
            note=clean_note,
            created_at=now,
            updated_at=now,
            updated_by_name=actor.worker_name,
            updated_by_device=actor.device_name,
        )
        uow.dealer_pricing.add(pricing)
        if cash_floor_price is not None or card_floor_price is not None:
            uow.dealer_pricing.add_history(
                _pricing_history(
                    product_id,
                    old_cash=None,
                    new_cash=cash_floor_price,
                    old_card=None,
                    new_card=card_floor_price,
                    note=clean_note,
                    actor=actor,
                    now=now,
                )
            )
        return pricing

    old_cash = pricing.cash_floor_price
    old_card = pricing.card_floor_price
    changed = old_cash != cash_floor_price or old_card != card_floor_price
    pricing.cash_floor_price = cash_floor_price
    pricing.card_floor_price = card_floor_price
    pricing.note = clean_note
    pricing.updated_at = now
    pricing.updated_by_name = actor.worker_name
    pricing.updated_by_device = actor.device_name
    if changed:
        uow.dealer_pricing.add_history(
            _pricing_history(
                product_id,
                old_cash=old_cash,
                new_cash=cash_floor_price,
                old_card=old_card,
                new_card=card_floor_price,
                note=clean_note,
                actor=actor,
                now=now,
            )
        )
    return pricing


def get_default_dealer_discount(
    uow: UnitOfWork,
    *,
    limit: int = 50,
) -> DealerDiscountSettingView:
    with uow:
        setting = uow.dealer_pricing.get_setting()
        if setting is None:
            return DealerDiscountSettingView(
                default_percent=DEFAULT_DEALER_DISCOUNT_PERCENT,
                updated_at=None,
                updated_by_name=None,
                history=(),
            )
        history = uow.dealer_pricing.get_setting_history(setting.id, limit)
        return _setting_view(setting, history)


def update_default_dealer_discount(
    uow: UnitOfWork,
    default_percent: Decimal,
    note: str | None = None,
    actor: ActorContext | None = None,
) -> DealerDiscountSettingView:
    actor = actor or ActorContext()
    now = datetime.now(UTC)
    try:
        percent = validate_dealer_percent(default_percent)
    except ValueError as exc:
        raise ValidationError(
            "Bayi indirimi oranı %0 ile %100 arasında olmalıdır."
        ) from exc

    with uow:
        setting = uow.dealer_pricing.get_setting_for_update()
        if setting is None:
            setting = DealerDiscountSetting(
                id=uuid.uuid4(),
                setting_key="default",
                default_percent=percent,
                updated_at=now,
                updated_by_name=actor.worker_name,
                updated_by_device=actor.device_name,
            )
            uow.dealer_pricing.add_setting(setting)
            if percent != DEFAULT_DEALER_DISCOUNT_PERCENT:
                uow.dealer_pricing.add_setting_history(
                    _setting_history(
                        setting.id,
                        old_percent=DEFAULT_DEALER_DISCOUNT_PERCENT,
                        new_percent=percent,
                        note=_clean_text(note),
                        actor=actor,
                        now=now,
                    )
                )
        else:
            old_percent = setting.default_percent
            if old_percent != percent:
                uow.dealer_pricing.add_setting_history(
                    _setting_history(
                        setting.id,
                        old_percent=old_percent,
                        new_percent=percent,
                        note=_clean_text(note),
                        actor=actor,
                        now=now,
                    )
                )
            setting.default_percent = percent
            setting.updated_at = now
            setting.updated_by_name = actor.worker_name
            setting.updated_by_device = actor.device_name

        uow.commit()
        history = uow.dealer_pricing.get_setting_history(setting.id)
        return _setting_view(setting, history)


def _pricing_view(
    product_id: uuid.UUID,
    pricing: DealerPricing | None,
    history: Sequence[DealerPricingHistory],
) -> DealerPricingView:
    return DealerPricingView(
        product_id=product_id,
        cash_floor_price=(
            pricing.cash_floor_price if pricing is not None else None
        ),
        card_floor_price=(
            pricing.card_floor_price if pricing is not None else None
        ),
        note=pricing.note if pricing is not None else None,
        updated_at=pricing.updated_at if pricing is not None else None,
        updated_by_name=(
            pricing.updated_by_name if pricing is not None else None
        ),
        history=tuple(
            DealerPricingHistoryView(
                old_cash_floor=row.old_cash_floor,
                new_cash_floor=row.new_cash_floor,
                old_card_floor=row.old_card_floor,
                new_card_floor=row.new_card_floor,
                note=row.note,
                changed_at=row.changed_at,
                changed_by_name=row.changed_by_name,
            )
            for row in history
        ),
    )


def _setting_view(
    setting: DealerDiscountSetting,
    history: Sequence[DealerDiscountSettingHistory],
) -> DealerDiscountSettingView:
    return DealerDiscountSettingView(
        default_percent=setting.default_percent,
        updated_at=setting.updated_at,
        updated_by_name=setting.updated_by_name,
        history=tuple(
            DealerDiscountSettingHistoryView(
                old_percent=row.old_percent,
                new_percent=row.new_percent,
                note=row.note,
                changed_at=row.changed_at,
                changed_by_name=row.changed_by_name,
            )
            for row in history  # type: ignore[union-attr]
        ),
    )


def _pricing_history(
    product_id: uuid.UUID,
    *,
    old_cash: Decimal | None,
    new_cash: Decimal | None,
    old_card: Decimal | None,
    new_card: Decimal | None,
    note: str | None,
    actor: ActorContext,
    now: datetime,
) -> DealerPricingHistory:
    return DealerPricingHistory(
        id=uuid.uuid4(),
        product_id=product_id,
        old_cash_floor=old_cash,
        new_cash_floor=new_cash,
        old_card_floor=old_card,
        new_card_floor=new_card,
        note=note,
        changed_at=now,
        changed_by_name=actor.worker_name,
        changed_by_device=actor.device_name,
    )


def _setting_history(
    setting_id: uuid.UUID,
    *,
    old_percent: Decimal,
    new_percent: Decimal,
    note: str | None,
    actor: ActorContext,
    now: datetime,
) -> DealerDiscountSettingHistory:
    return DealerDiscountSettingHistory(
        id=uuid.uuid4(),
        dealer_discount_setting_id=setting_id,
        old_percent=old_percent,
        new_percent=new_percent,
        note=note,
        changed_at=now,
        changed_by_name=actor.worker_name,
        changed_by_device=actor.device_name,
    )


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
