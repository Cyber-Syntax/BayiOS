from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from bayios.domain.commissions import quantize_money

ZERO = Decimal(0)
HUNDRED = Decimal(100)


class CompanyDiscountSource(StrEnum):
    """Where the company base price comes from."""

    NONE = "none"
    CAMPAIGN = "campaign"
    OLIZ = "oliz"


class PricingScenario(StrEnum):
    """A what-if price scenario shown on the offer screen."""

    NORMAL = "normal"
    DEALER = "dealer"
    OLIZ = "oliz"
    CAMPAIGN = "campaign"
    CAMPAIGN_DEALER = "campaign_dealer"
    MANUAL = "manual"


SCENARIO_LABELS: dict[PricingScenario, str] = {
    PricingScenario.NORMAL: "Normal fiyat",
    PricingScenario.DEALER: "Bayi indirimi",
    PricingScenario.OLIZ: "Oliz",
    PricingScenario.CAMPAIGN: "Kampanya",
    PricingScenario.CAMPAIGN_DEALER: "Kampanya + bayi",
    PricingScenario.MANUAL: "Manuel fiyat",
}


@dataclass(frozen=True)
class CompanyPriceCandidate:
    """A candidate company base price before the dealer discount."""

    source: CompanyDiscountSource
    price: Decimal
    discount_amount: Decimal
    share_amount: Decimal
    campaign_id: str | None = None
    campaign_name: str | None = None
    campaign_discount_amount: Decimal | None = None
    campaign_base_price: Decimal | None = None
    campaign_price: Decimal | None = None
    warning: str | None = None
    snapshot: dict[str, object] | None = None


@dataclass(frozen=True)
class UnitPricing:
    """Per-unit prices and company support for one offer line."""

    company_source: CompanyDiscountSource
    company_price: Decimal
    company_discount: Decimal
    company_share: Decimal
    suggested_cash: Decimal
    suggested_card: Decimal
    unit_cash: Decimal
    unit_card: Decimal
    campaign_id: str | None = None
    campaign_name: str | None = None
    campaign_discount_amount: Decimal | None = None
    campaign_base_price: Decimal | None = None
    campaign_price: Decimal | None = None
    warning: str | None = None


@dataclass(frozen=True)
class ProfitLine:
    sale_price: Decimal
    commission_percent: Decimal
    net_after_commission: Decimal
    company_share: Decimal
    total_revenue: Decimal
    cost: Decimal | None
    profit: Decimal | None
    margin_percent: Decimal | None

    @property
    def has_missing_cost(self) -> bool:
        return self.cost is None


def regular_candidate(regular_price: Decimal | None) -> CompanyPriceCandidate | None:
    if regular_price is None:
        return None
    price = quantize_money(regular_price)
    return CompanyPriceCandidate(
        source=CompanyDiscountSource.NONE,
        price=price,
        discount_amount=ZERO,
        share_amount=ZERO,
    )


def oliz_candidate(
    regular_price: Decimal | None, oliz_price: Decimal | None
) -> CompanyPriceCandidate | None:
    if oliz_price is None or oliz_price <= ZERO:
        return None
    if regular_price is not None and oliz_price >= regular_price:
        return None
    price = quantize_money(oliz_price)
    regular = quantize_money(regular_price) if regular_price is not None else price
    discount = max(quantize_money(regular - price), ZERO)
    return CompanyPriceCandidate(
        source=CompanyDiscountSource.OLIZ,
        price=price,
        discount_amount=discount,
        share_amount=discount,
    )


def select_company_price(
    *,
    regular_price: Decimal | None,
    oliz_price: Decimal | None,
    campaigns: Sequence[CompanyPriceCandidate] = (),
    mode: str = "auto",
) -> CompanyPriceCandidate | None:
    """Pick the company base price.

    ``mode`` is ``auto`` (largest discount), ``none`` (no campaign, Oliz only)
    or a campaign id (explicit campaign selection).
    """
    candidates = list(campaigns)
    oliz = oliz_candidate(regular_price, oliz_price)
    regular = regular_candidate(regular_price)

    if mode == "none":
        return oliz or regular

    if mode != "auto":
        explicit = next(
            (candidate for candidate in candidates if candidate.campaign_id == mode),
            None,
        )
        return explicit or oliz or regular

    priced = [candidate for candidate in candidates if candidate.price > ZERO]
    if oliz is not None:
        priced.append(oliz)
    if not priced:
        return regular
    best = max(
        priced,
        key=lambda candidate: (
            candidate.discount_amount,
            candidate.source is CompanyDiscountSource.CAMPAIGN,
        ),
    )
    return best


def price_unit(
    candidate: CompanyPriceCandidate,
    *,
    dealer_discount_percent: Decimal,
    dealer_discount_cash_percent: Decimal,
    unit_price_cash: Decimal | None = None,
    unit_price_card: Decimal | None = None,
) -> UnitPricing:
    """Apply the dealer discount once to the selected company price."""
    suggested_cash = quantize_money(
        candidate.price * (HUNDRED - dealer_discount_cash_percent) / HUNDRED
    )
    suggested_card = quantize_money(
        candidate.price * (HUNDRED - dealer_discount_percent) / HUNDRED
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
    return UnitPricing(
        company_source=candidate.source,
        company_price=candidate.price,
        company_discount=candidate.discount_amount,
        company_share=candidate.share_amount,
        suggested_cash=suggested_cash,
        suggested_card=suggested_card,
        unit_cash=final_cash,
        unit_card=final_card,
        campaign_id=candidate.campaign_id,
        campaign_name=candidate.campaign_name,
        campaign_discount_amount=candidate.campaign_discount_amount,
        campaign_base_price=candidate.campaign_base_price,
        campaign_price=candidate.campaign_price,
        warning=candidate.warning,
    )


def company_share_for(
    pricing: UnitPricing, share_percent: Decimal
) -> Decimal:
    """Dealer's 85% share of a campaign/Oliz discount; dealer discount adds nothing."""
    if share_percent < ZERO or share_percent > HUNDRED:
        raise ValueError("Bayi payı %0 ile %100 arasında olmalıdır.")
    return quantize_money(pricing.company_share * share_percent / HUNDRED)


def profit_line(
    *,
    sale_price: Decimal,
    quantity: int,
    commission_percent: Decimal,
    company_share_per_unit: Decimal,
    cost_price: Decimal | None,
) -> ProfitLine:
    """Profit after commission and only the company-funded share."""
    if quantity <= 0:
        raise ValueError("Miktar sıfırdan büyük olmalıdır.")
    net = quantize_money(
        sale_price * (HUNDRED - commission_percent) / HUNDRED
    )
    share = quantize_money(company_share_per_unit * quantity)
    revenue = quantize_money(net * quantity + share)
    if cost_price is None:
        profit = None
        margin = None
    else:
        profit = quantize_money(revenue - cost_price * quantity)
        margin = (
            quantize_money(profit / revenue * HUNDRED) if revenue else None
        )
    return ProfitLine(
        sale_price=quantize_money(sale_price),
        commission_percent=commission_percent,
        net_after_commission=quantize_money(net * quantity),
        company_share=share,
        total_revenue=revenue,
        cost=cost_price,
        profit=profit,
        margin_percent=margin,
    )
