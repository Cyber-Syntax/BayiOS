from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from bayios.domain.commissions import (
    ProfitTargetType,
    ReferencePrice,
    calculate_reference_price,
    quantize_money,
)

ZERO = Decimal(0)
HUNDRED = Decimal(100)
DEALER_SHARE_PERCENT = Decimal("85.00")


class OfferStatus(StrEnum):
    DRAFT = "draft"
    PRESENTED = "presented"
    ACCEPTED = "accepted"
    LOST = "lost"
    EXPIRED = "expired"


class PaymentType(StrEnum):
    CASH = "cash"
    CARD = "card"


OFFER_STATUS_LABELS: dict[OfferStatus, str] = {
    OfferStatus.DRAFT: "Taslak",
    OfferStatus.PRESENTED: "Müşteriye sunuldu",
    OfferStatus.ACCEPTED: "Kabul edildi",
    OfferStatus.LOST: "Kaybedildi",
    OfferStatus.EXPIRED: "Geçersiz",
}
PAYMENT_TYPE_LABELS: dict[PaymentType, str] = {
    PaymentType.CASH: "Nakit",
    PaymentType.CARD: "Kart",
}
STATUS_TRANSITIONS: dict[OfferStatus, frozenset[OfferStatus]] = {
    OfferStatus.DRAFT: frozenset(
        {OfferStatus.PRESENTED, OfferStatus.LOST, OfferStatus.EXPIRED}
    ),
    OfferStatus.PRESENTED: frozenset(
        {OfferStatus.ACCEPTED, OfferStatus.LOST, OfferStatus.EXPIRED}
    ),
    OfferStatus.ACCEPTED: frozenset(),
    OfferStatus.LOST: frozenset(),
    OfferStatus.EXPIRED: frozenset(),
}


@dataclass(frozen=True)
class OfferPriceLayers:
    cost_price: Decimal | None = None
    regular_price: Decimal | None = None
    website_price: Decimal | None = None
    campaign_price: Decimal | None = None
    campaign_name: str | None = None
    campaign_gift_present: bool | None = None

    def __post_init__(self) -> None:
        for value in (
            self.cost_price,
            self.regular_price,
            self.website_price,
            self.campaign_price,
        ):
            if value is not None and value < ZERO:
                raise ValueError("Teklif fiyat katmanları negatif olamaz.")

    @property
    def base_price(self) -> Decimal | None:
        if self.campaign_price is not None:
            return self.campaign_price
        if self.website_price is not None:
            return self.website_price
        return self.regular_price

    @property
    def base_source(self) -> str:
        if self.campaign_price is not None:
            return "Kampanya"
        if self.website_price is not None:
            return "Oliz"
        return "Normal"


@dataclass(frozen=True)
class OfferItemQuote:
    quantity: int
    base_price: Decimal | None
    dealer_discount_percent: Decimal
    suggested_cash_price: Decimal | None
    suggested_card_price: Decimal | None
    unit_price_cash: Decimal | None
    unit_price_card: Decimal | None
    line_total_cash: Decimal | None
    line_total_card: Decimal | None
    reference: ReferencePrice
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class OfferTotals:
    cash_total: Decimal
    card_total: Decimal
    selected_total: Decimal


def quote_offer_item(
    layers: OfferPriceLayers,
    *,
    quantity: int,
    dealer_discount_percent: Decimal,
    commission_percent: Decimal,
    target_type: ProfitTargetType | None,
    target_value: Decimal | None,
    cash_floor: Decimal | None = None,
    card_floor: Decimal | None = None,
    unit_price_cash: Decimal | None = None,
    unit_price_card: Decimal | None = None,
) -> OfferItemQuote:
    if quantity <= 0:
        raise ValueError("Miktar sıfırdan büyük olmalıdır.")
    if not (ZERO <= dealer_discount_percent <= HUNDRED):
        raise ValueError("Bayi indirimi %0 ile %100 arasında olmalıdır.")

    base_price = layers.base_price
    reference = calculate_reference_price(
        layers.cost_price,
        target_type,
        target_value,
        commission_percent,
    )
    warnings: list[str] = []
    if reference.warning:
        warnings.append(reference.warning)
    if layers.campaign_price is not None and layers.website_price is not None:
        warnings.append("Kampanya seçildiği için Oliz fiyatı uygulanmadı.")

    if base_price is None:
        warnings.append("Teklif fiyatı için ürün fiyatı tanımlı değil.")
        return OfferItemQuote(
            quantity=quantity,
            base_price=None,
            dealer_discount_percent=dealer_discount_percent,
            suggested_cash_price=None,
            suggested_card_price=None,
            unit_price_cash=unit_price_cash,
            unit_price_card=unit_price_card,
            line_total_cash=None,
            line_total_card=None,
            reference=reference,
            warnings=tuple(warnings),
        )

    suggested_cash = quantize_money(
        base_price * (HUNDRED - dealer_discount_percent) / HUNDRED
    )
    suggested_card = (
        reference.price if reference.price is not None else suggested_cash
    )
    final_cash = (
        quantize_money(unit_price_cash)
        if unit_price_cash is not None
        else suggested_cash
    )
    final_card = (
        quantize_money(unit_price_card)
        if unit_price_card is not None
        else suggested_card
    )
    if final_cash < ZERO or final_card < ZERO:
        raise ValueError("Teklif fiyatı negatif olamaz.")
    if cash_floor is not None and final_cash < cash_floor:
        warnings.append("Nakit fiyat ürün nakit tabanının altında.")
    if card_floor is not None and final_card < card_floor:
        warnings.append("Kart fiyat ürün kart tabanının altında.")
    if layers.cost_price is not None and final_cash < layers.cost_price:
        warnings.append("Nakit fiyat maliyetin altında.")
    if reference.price is not None and final_card < reference.price:
        warnings.append("Kart fiyat kâr referansının altında.")

    return OfferItemQuote(
        quantity=quantity,
        base_price=base_price,
        dealer_discount_percent=dealer_discount_percent,
        suggested_cash_price=suggested_cash,
        suggested_card_price=suggested_card,
        unit_price_cash=final_cash,
        unit_price_card=final_card,
        line_total_cash=quantize_money(final_cash * quantity),
        line_total_card=quantize_money(final_card * quantity),
        reference=reference,
        warnings=tuple(warnings),
    )


def summarize_offer(
    quotes: tuple[OfferItemQuote, ...] | list[OfferItemQuote],
    payment_type: PaymentType,
) -> OfferTotals:
    cash_total = sum(
        (quote.line_total_cash or ZERO for quote in quotes), ZERO
    )
    card_total = sum(
        (quote.line_total_card or ZERO for quote in quotes), ZERO
    )
    selected_total = cash_total if payment_type is PaymentType.CASH else card_total
    return OfferTotals(
        cash_total=quantize_money(cash_total),
        card_total=quantize_money(card_total),
        selected_total=quantize_money(selected_total),
    )


def can_transition_status(
    current: OfferStatus, target: OfferStatus
) -> bool:
    return target in STATUS_TRANSITIONS[current]


def ensure_status_transition(current: OfferStatus, target: OfferStatus) -> None:
    if target is current:
        raise ValueError("Teklif zaten bu durumda.")
    if not can_transition_status(current, target):
        raise ValueError(
            f"{OFFER_STATUS_LABELS[current]} durumundan "
            f"{OFFER_STATUS_LABELS[target]} durumuna geçilemez."
        )


def is_editable(status: OfferStatus) -> bool:
    return status is OfferStatus.DRAFT


def ensure_editable(status: OfferStatus) -> None:
    if not is_editable(status):
        raise ValueError("Yalnızca taslak teklif düzenlenebilir.")
