from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from bayios.adapters.db.models.offers import Offer, OfferHistory, OfferItem
from bayios.application.campaigns import _contract_from_row
from bayios.application.commissions import (
    _domain_limits,
    _domain_rates,
    resolve_commission,
)
from bayios.application.errors import NotFoundError, ValidationError
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.reservations import (
    NewReservationItem,
    create_reservation,
    deliver_item,
)
from bayios.domain.campaigns import (
    CampaignPriceInput,
    campaign_discount_price,
    campaign_scenarios,
)
from bayios.domain.commissions import (
    CHANNEL_LABELS,
    CardType,
    PaymentChannel,
    ProductCommissionGroup,
    ProfitTargetType,
    effective_max_installments,
    matching_commission_rate,
    quantize_money,
)
from bayios.domain.offers import (
    DEALER_SHARE_PERCENT,
    OfferPriceLayers,
    OfferStatus,
    PaymentType,
    ensure_status_transition,
    quote_offer_item,
    summarize_offer,
)
from bayios.domain.offers.pricing import (
    SCENARIO_LABELS,
    CompanyDiscountSource,
    CompanyPriceCandidate,
    PricingScenario,
    oliz_candidate,
    regular_candidate,
    select_company_price,
)
from bayios.domain.products import ActorContext, normalize_website_price


class OfferPaymentType(StrEnum):
    CASH = "cash"
    CARD = "card"


@dataclass(frozen=True)
class OfferItemInput:
    product_id: uuid.UUID
    quantity: int
    campaign_id: uuid.UUID | None = None
    gift_present: bool | None = None
    unit_price_cash: Decimal | None = None
    unit_price_card: Decimal | None = None
    auto_campaign: bool = False


@dataclass(frozen=True)
class OfferInput:
    customer_name: str | None
    customer_phone: str | None
    payment_type: PaymentType
    dealer_discount_percent: Decimal
    items: tuple[OfferItemInput, ...]
    channel: PaymentChannel | None = None
    bank_id: uuid.UUID | None = None
    installment_count: int | None = None
    card_type: CardType | None = None
    note: str | None = None
    dealer_discount_cash_percent: Decimal = Decimal(10)


@dataclass(frozen=True)
class OfferDetail:
    offer: Offer
    items: tuple[OfferItem, ...]
    history: tuple[OfferHistory, ...]


@dataclass(frozen=True)
class InstallmentProfit:
    installment_count: int
    commission_percent: Decimal
    net_after_commission: Decimal
    campaign_share: Decimal
    oliz_share: Decimal
    total_revenue: Decimal
    cost: Decimal | None
    profit: Decimal | None


@dataclass(frozen=True)
class OfferLineAnalysis:
    item: OfferItem
    sale_price_cash: Decimal | None
    sale_price_card: Decimal | None
    installments: tuple[InstallmentProfit, ...]


@dataclass(frozen=True)
class OfferProfitLine:
    item: OfferItem
    quantity: int
    sale_price: Decimal | None
    installment_count: int
    commission_percent: Decimal
    net_after_commission: Decimal
    campaign_share: Decimal
    oliz_share: Decimal
    total_revenue: Decimal
    cost: Decimal | None
    profit: Decimal | None
    margin_percent: Decimal | None


@dataclass(frozen=True)
class OfferProfitSummary:
    lines: tuple[OfferProfitLine, ...]
    total_revenue: Decimal
    total_cost: Decimal
    total_profit: Decimal
    margin_percent: Decimal | None
    has_missing_cost: bool


def build_offer_line_analyses(
    detail: OfferDetail,
) -> tuple[OfferLineAnalysis, ...]:
    offer = detail.offer
    share = offer.dealer_share_percent_snapshot or DEALER_SHARE_PERCENT
    raw_options = offer.commission_options_snapshot or []
    parsed_options = [
        (
            int(row["installment"]),
            Decimal(str(row["percent"])),
        )
        for row in raw_options
        if isinstance(row, dict) and row.get("installment") is not None
    ]
    analyses: list[OfferLineAnalysis] = []
    is_v2 = getattr(offer, "pricing_version", "legacy") == "v2"
    for item in detail.items:
        sale_cash = item.unit_price_cash
        sale_card = item.unit_price_card
        is_cash = offer.payment_type == PaymentType.CASH.value
        sale = sale_cash if is_cash else sale_card
        if sale is None:
            analyses.append(
                OfferLineAnalysis(
                    item=item,
                    sale_price_cash=sale_cash,
                    sale_price_card=sale_card,
                    installments=(),
                )
            )
            continue
        options = (
            [(0, Decimal(0))]
            if is_cash
            else parsed_options
            or (
                [
                    (
                        offer.installment_count or 1,
                        offer.commission_percent_snapshot or Decimal(0),
                    )
                ]
                if offer.installment_count
                else []
            )
        )
        rows: list[InstallmentProfit] = []
        for installment, percent in options:
            net = quantize_money(sale * (Decimal(100) - percent) / Decimal(100))
            if is_v2:
                company_share = quantize_money(
                    (item.company_share_amount or Decimal(0))
                    * share
                    / Decimal(100)
                )
                source = item.company_discount_source or "none"
                campaign_share = (
                    company_share if source == "campaign" else Decimal(0)
                )
                oliz_share = (
                    company_share if source == "oliz" else Decimal(0)
                )
            else:
                campaign_share = _campaign_share(item, sale, share)
                oliz_share = _oliz_share(item, share)
            total = quantize_money(net + campaign_share + oliz_share)
            profit = (
                quantize_money(total - item.cost_price_snapshot)
                if item.cost_price_snapshot is not None
                else None
            )
            rows.append(
                InstallmentProfit(
                    installment_count=installment,
                    commission_percent=percent,
                    net_after_commission=net,
                    campaign_share=campaign_share,
                    oliz_share=oliz_share,
                    total_revenue=total,
                    cost=item.cost_price_snapshot,
                    profit=profit,
                )
            )
        analyses.append(
            OfferLineAnalysis(
                item=item,
                sale_price_cash=sale_cash,
                sale_price_card=sale_card,
                installments=tuple(rows),
            )
        )
    return tuple(analyses)


def build_offer_profit_summary(detail: OfferDetail) -> OfferProfitSummary:
    offer = detail.offer
    lines: list[OfferProfitLine] = []
    for analysis in build_offer_line_analyses(detail):
        if not analysis.installments:
            continue
        selected = analysis.installments[0]
        if offer.payment_type == PaymentType.CARD.value and offer.installment_count:
            selected = next(
                (
                    row
                    for row in analysis.installments
                    if row.installment_count == offer.installment_count
                ),
                selected,
            )
        elif offer.payment_type == PaymentType.CASH.value:
            selected = analysis.installments[0]
        quantity = analysis.item.quantity
        line_net = quantize_money(selected.net_after_commission * quantity)
        line_campaign = quantize_money(selected.campaign_share * quantity)
        line_oliz = quantize_money(selected.oliz_share * quantity)
        line_revenue = quantize_money(selected.total_revenue * quantity)
        line_cost = (
            quantize_money(selected.cost * quantity)
            if selected.cost is not None
            else None
        )
        line_profit = (
            quantize_money(line_revenue - line_cost)
            if line_cost is not None
            else None
        )
        margin = (
            (line_profit / line_revenue * Decimal(100))
            if line_profit is not None and line_revenue
            else None
        )
        lines.append(
            OfferProfitLine(
                item=analysis.item,
                quantity=quantity,
                sale_price=(
                    analysis.sale_price_cash
                    if offer.payment_type == PaymentType.CASH.value
                    else analysis.sale_price_card
                ),
                installment_count=selected.installment_count,
                commission_percent=selected.commission_percent,
                net_after_commission=line_net,
                campaign_share=line_campaign,
                oliz_share=line_oliz,
                total_revenue=line_revenue,
                cost=line_cost,
                profit=line_profit,
                margin_percent=quantize_money(margin) if margin is not None else None,
            )
        )
    total_revenue = sum((line.total_revenue for line in lines), Decimal(0))
    total_cost = sum(
        (line.cost for line in lines if line.cost is not None), Decimal(0)
    )
    total_profit = sum(
        (line.profit for line in lines if line.profit is not None), Decimal(0)
    )
    has_missing_cost = any(line.cost is None for line in lines)
    margin = (
        quantize_money(total_profit / total_revenue * Decimal(100))
        if total_revenue and not has_missing_cost
        else None
    )
    return OfferProfitSummary(
        lines=tuple(lines),
        total_revenue=quantize_money(total_revenue),
        total_cost=quantize_money(total_cost),
        total_profit=quantize_money(total_profit),
        margin_percent=margin,
        has_missing_cost=has_missing_cost,
    )


def _campaign_share(
    item: OfferItem, sale_price: Decimal, share_percent: Decimal
) -> Decimal:
    snapshot = item.campaign_snapshot or {}
    raw_amount = snapshot.get("campaign_discount_amount")
    if raw_amount is not None:
        return quantize_money(
            Decimal(str(raw_amount)) * share_percent / Decimal(100)
        )
    discount_type = snapshot.get("discount_type")
    raw_value = snapshot.get("discount_value")
    if not discount_type or raw_value is None:
        return Decimal(0)
    value = Decimal(str(raw_value))
    if discount_type == "percent":
        discount = sale_price * value / Decimal(100)
    elif discount_type == "fixed_amount":
        discount = min(value, sale_price)
    elif discount_type == "special_price":
        base = item.regular_price_snapshot or sale_price
        discount = max(Decimal(0), base - value)
    else:
        discount = Decimal(0)
    return quantize_money(discount * share_percent / Decimal(100))


def _oliz_share(item: OfferItem, share_percent: Decimal) -> Decimal:
    if item.campaign_snapshot:
        return Decimal(0)
    regular = item.regular_price_snapshot
    website = item.website_price_snapshot
    if regular is None or website is None or regular <= website:
        return Decimal(0)
    return quantize_money(
        (regular - website) * share_percent / Decimal(100)
    )


@dataclass(frozen=True)
class _PreparedItem:
    product: object
    input: OfferItemInput
    layers: OfferPriceLayers
    pricing: object
    dealer_discount: Decimal
    dealer_discount_cash: Decimal
    product_group: ProductCommissionGroup
    category_id: uuid.UUID | None = None
    campaign_version_id: uuid.UUID | None = None
    campaign_snapshot: dict[str, object] | None = None
    company: CompanyPriceCandidate | None = None
    best_campaign: CompanyPriceCandidate | None = None
    regular_price: Decimal | None = None
    oliz_price: Decimal | None = None
    cost_price: Decimal | None = None


def _estimate_card_total(prepared: list[_PreparedItem]) -> Decimal:
    total = Decimal(0)
    for item in prepared:
        unit = item.input.unit_price_card
        if unit is None and item.layers.base_price is not None:
            unit = (
                item.layers.base_price
                * (Decimal(100) - item.dealer_discount)
                / Decimal(100)
            )
        if unit is None:
            continue
        total += quantize_money(unit) * item.input.quantity
    return quantize_money(total)


@dataclass(frozen=True)
class _ComparisonItem:
    sale_card: Decimal
    sale_cash: Decimal
    quantity: int
    cost: Decimal | None
    campaign_snapshot: dict[str, object] | None
    regular_price: Decimal | None
    website_price: Decimal | None
    product_group: ProductCommissionGroup
    company_source: str = "none"
    company_discount_amount: Decimal = Decimal(0)
    company_share_amount: Decimal = Decimal(0)


@dataclass(frozen=True)
class OfferComparisonOption:
    payment_type: str
    channel: str | None
    channel_label: str
    bank_id: uuid.UUID | None
    bank_name: str
    installment_count: int
    commission_percent: Decimal
    commission_source: str
    card_total: Decimal
    cash_total: Decimal
    monthly_payment: Decimal | None
    net_after_commission: Decimal
    company_share: Decimal
    campaign_share: Decimal
    oliz_share: Decimal
    total_revenue: Decimal
    cost: Decimal
    profit: Decimal | None
    margin_percent: Decimal | None
    has_missing_cost: bool


@dataclass(frozen=True)
class OfferScenarioSummary:
    key: str
    label: str
    sale_cash: Decimal
    sale_card: Decimal
    company_share: Decimal
    total_revenue: Decimal
    cost: Decimal
    cash_profit: Decimal | None
    card_profit: Decimal | None
    margin_percent: Decimal | None
    has_missing_cost: bool
    partial: bool = False


@dataclass(frozen=True)
class OfferComparison:
    cash: OfferComparisonOption
    options: tuple[OfferComparisonOption, ...]
    card_total: Decimal
    cash_total: Decimal
    card_type: str
    has_missing_cost: bool
    scenarios: tuple[OfferScenarioSummary, ...] = ()
    has_oliz: bool = False
    regular_total: Decimal = Decimal(0)
    oliz_total: Decimal = Decimal(0)
    company_discount_total: Decimal = Decimal(0)
    cost_total: Decimal = Decimal(0)
    selected_scenario: str = "auto"


def _option_profit(
    items: tuple[_ComparisonItem, ...],
    *,
    commission_percent: Decimal,
    share_percent: Decimal,
    sale_attr: str,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal | None, bool, Decimal]:
    net_total = Decimal(0)
    campaign_total = Decimal(0)
    oliz_total = Decimal(0)
    company_total = Decimal(0)
    revenue_total = Decimal(0)
    cost_total = Decimal(0)
    has_missing_cost = False
    for item in items:
        sale = getattr(item, sale_attr)
        net = quantize_money(
            sale * (Decimal(100) - commission_percent) / Decimal(100)
        )
        company_share = quantize_money(
            item.company_share_amount * share_percent / Decimal(100)
        )
        if item.company_source == "campaign":
            campaign = company_share
            oliz = Decimal(0)
        elif item.company_source == "oliz":
            campaign = Decimal(0)
            oliz = company_share
        else:
            campaign = Decimal(0)
            oliz = Decimal(0)
        revenue = quantize_money(net + company_share)
        net_total += net * item.quantity
        campaign_total += campaign * item.quantity
        oliz_total += oliz * item.quantity
        company_total += company_share * item.quantity
        revenue_total += revenue * item.quantity
        if item.cost is None:
            has_missing_cost = True
        else:
            cost_total += item.cost * item.quantity
    if has_missing_cost:
        profit = None
    else:
        profit = quantize_money(revenue_total - cost_total)
    return (
        quantize_money(net_total),
        quantize_money(campaign_total),
        quantize_money(oliz_total),
        quantize_money(company_total),
        quantize_money(revenue_total),
        cost_total,
        profit,
        has_missing_cost,
    )


def _comparison_row(
    items: tuple[_ComparisonItem, ...],
    *,
    payment_type: str,
    channel: PaymentChannel | None,
    bank: object | None,
    installment_count: int,
    commission_percent: Decimal,
    commission_source: str,
    card_total: Decimal,
    cash_total: Decimal,
    share_percent: Decimal,
) -> OfferComparisonOption:
    sale_attr = "sale_cash" if payment_type == PaymentType.CASH.value else "sale_card"
    (
        net_total,
        campaign_total,
        oliz_total,
        company_total,
        revenue_total,
        cost_total,
        profit,
        missing,
    ) = _option_profit(
        items,
        commission_percent=commission_percent,
        share_percent=share_percent,
        sale_attr=sale_attr,
    )
    margin = (
        quantize_money(profit / revenue_total * Decimal(100))
        if profit is not None and revenue_total
        else None
    )
    return OfferComparisonOption(
        payment_type=payment_type,
        channel=channel.value if channel else None,
        channel_label=CHANNEL_LABELS.get(channel, "Nakit") if channel else "Nakit",
        bank_id=getattr(bank, "id", None),
        bank_name=getattr(bank, "name", "Genel (tüm bankalar)") if bank else "Genel (tüm bankalar)",
        installment_count=installment_count,
        commission_percent=commission_percent,
        commission_source=commission_source,
        card_total=card_total,
        cash_total=cash_total,
        monthly_payment=(
            quantize_money(card_total / installment_count)
            if payment_type == PaymentType.CARD.value and installment_count
            else None
        ),
        net_after_commission=net_total,
        company_share=company_total,
        campaign_share=campaign_total,
        oliz_share=oliz_total,
        total_revenue=revenue_total,
        cost=quantize_money(cost_total),
        profit=profit,
        margin_percent=margin,
        has_missing_cost=missing,
    )


def preview_offer_comparison(
    uow: UnitOfWork, data: OfferInput
) -> OfferComparison:
    now = datetime.now(UTC)
    with uow:
        period = uow.commissions.get_active_period(now)
        if period is None:
            raise ValidationError("Aktif komisyon dönemi tanımlı değil.")
        raw_rates = uow.commissions.get_rates(period.id)
        raw_limits = uow.commissions.get_limits(period.id)
        rates = _domain_rates(raw_rates)
        limits = _domain_limits(raw_limits)
        banks = list(uow.commissions.get_banks(active_only=True))
        prepared = _prepare_items(uow, data)

    if not prepared:
        raise ValidationError("En az bir ürün satırı gereklidir.")

    items = tuple(_comparison_item_from_prepared(item) for item in prepared)
    card_total = sum((item.sale_card * item.quantity for item in items), Decimal(0))
    cash_total = sum((item.sale_cash * item.quantity for item in items), Decimal(0))
    card_total = quantize_money(card_total)
    cash_total = quantize_money(cash_total)
    share_percent = DEALER_SHARE_PERCENT
    regular_total = quantize_money(
        sum(
            (
                (item.regular_price or Decimal(0)) * item.input.quantity
                for item in prepared
            ),
            Decimal(0),
        )
    )
    oliz_total = quantize_money(
        sum(
            (
                (item.oliz_price or Decimal(0)) * item.input.quantity
                for item in prepared
            ),
            Decimal(0),
        )
    )
    company_discount_total = quantize_money(
        sum(
            (
                (item.company.discount_amount if item.company else Decimal(0))
                * item.input.quantity
                for item in prepared
            ),
            Decimal(0),
        )
    )
    cost_total = quantize_money(
        sum(
            (
                (item.cost_price or Decimal(0)) * item.input.quantity
                for item in prepared
            ),
            Decimal(0),
        )
    )
    cash = _comparison_row(
        items,
        payment_type=PaymentType.CASH.value,
        channel=None,
        bank=None,
        installment_count=0,
        commission_percent=Decimal(0),
        commission_source="none",
        card_total=Decimal(0),
        cash_total=cash_total,
        share_percent=share_percent,
    )
    product_group = items[0].product_group
    category_ids = [
        str(item.category_id)
        for item in prepared
        if item.category_id is not None
    ]
    options: list[OfferComparisonOption] = []
    for channel in PaymentChannel:
        for bank in (None, *banks):
            bank_id = str(bank.id) if bank is not None else None
            maximum = effective_max_installments(
                rates,
                limits,
                channel=channel,
                bank_id=bank_id,
                product_group=product_group,
                card_type=data.card_type or CardType.CONSUMER,
                total=card_total,
                category_ids=category_ids,
            )
            for installment in range(1, maximum + 1):
                rate = matching_commission_rate(
                    rates,
                    channel=channel,
                    bank_id=bank_id,
                    product_group=product_group,
                    installment_count=installment,
                    total=card_total,
                )
                if rate is None:
                    continue
                options.append(
                    _comparison_row(
                        items,
                        payment_type=PaymentType.CARD.value,
                        channel=channel,
                        bank=bank,
                        installment_count=installment,
                        commission_percent=rate.commission_percent,
                        commission_source=(
                            "bank_specific" if rate.bank_id else "general"
                        ),
                        card_total=card_total,
                        cash_total=Decimal(0),
                        share_percent=share_percent,
                    )
                )
    options.sort(
        key=lambda row: (
            row.channel or "",
            row.bank_name,
            row.installment_count,
        )
    )
    selected_commission = Decimal(0)
    selected_bank = str(data.bank_id) if data.bank_id is not None else None
    for option in options:
        option_bank = str(option.bank_id) if option.bank_id is not None else None
        if (
            option.channel == (data.channel.value if data.channel else None)
            and option_bank == selected_bank
            and option.installment_count == data.installment_count
        ):
            selected_commission = option.commission_percent
            break
    if selected_commission == Decimal(0) and options:
        selected_commission = options[0].commission_percent

    scenario_specs: list[PricingScenario] = [
        PricingScenario.NORMAL,
        PricingScenario.DEALER,
    ]
    if any(item.oliz_price is not None for item in prepared):
        scenario_specs.append(PricingScenario.OLIZ)
    if any(item.best_campaign is not None for item in prepared):
        scenario_specs.extend(
            [PricingScenario.CAMPAIGN, PricingScenario.CAMPAIGN_DEALER]
        )
    if any(
        item.input.unit_price_cash is not None
        or item.input.unit_price_card is not None
        for item in prepared
    ):
        scenario_specs.append(PricingScenario.MANUAL)
    scenarios = tuple(
        _scenario_summary(
            prepared,
            scenario,
            share_percent=share_percent,
            card_commission_percent=selected_commission,
        )
        for scenario in scenario_specs
    )
    return OfferComparison(
        cash=cash,
        options=tuple(options),
        card_total=card_total,
        cash_total=cash_total,
        card_type=(data.card_type or CardType.CONSUMER).value,
        has_missing_cost=any(item.cost is None for item in items),
        scenarios=scenarios,
        has_oliz=any(item.oliz_price is not None for item in prepared),
        regular_total=regular_total,
        oliz_total=oliz_total,
        company_discount_total=company_discount_total,
        cost_total=cost_total,
    )


def _comparison_item_from_prepared(item: _PreparedItem) -> _ComparisonItem:
    base = item.layers.base_price or Decimal(0)
    card = item.input.unit_price_card
    if card is None:
        card = base * (Decimal(100) - item.dealer_discount) / Decimal(100)
    cash = item.input.unit_price_cash
    if cash is None:
        cash = base * (Decimal(100) - item.dealer_discount_cash) / Decimal(100)
    company = item.company
    return _ComparisonItem(
        sale_card=quantize_money(card),
        sale_cash=quantize_money(cash),
        quantity=item.input.quantity,
        cost=item.layers.cost_price,
        campaign_snapshot=item.campaign_snapshot,
        regular_price=item.layers.regular_price,
        website_price=item.oliz_price,
        product_group=item.product_group,
        company_source=(
            company.source.value if company is not None else "none"
        ),
        company_discount_amount=(
            company.discount_amount if company is not None else Decimal(0)
        ),
        company_share_amount=(
            company.share_amount if company is not None else Decimal(0)
        ),
    )


def _discounted(price: Decimal, percent: Decimal) -> Decimal:
    return quantize_money(price * (Decimal(100) - percent) / Decimal(100))


def _scenario_item(
    item: _PreparedItem, scenario: PricingScenario
) -> tuple[_ComparisonItem, bool]:
    regular = item.regular_price
    oliz = item.oliz_price
    campaign = item.best_campaign
    selected = item.company
    dealer = item.dealer_discount
    dealer_cash = item.dealer_discount_cash
    partial = False

    if scenario in (PricingScenario.NORMAL, PricingScenario.DEALER):
        base = regular
        source = "none"
        share = Decimal(0)
        if base is None:
            partial = True
            base = Decimal(0)
        if scenario is PricingScenario.NORMAL:
            cash = base
            card = base
        else:
            cash = _discounted(base, dealer_cash)
            card = _discounted(base, dealer)
        campaign_snapshot = None
    elif scenario is PricingScenario.OLIZ:
        if oliz is None:
            partial = True
            base = regular or Decimal(0)
            share = Decimal(0)
            source = "none"
        else:
            base = oliz
            share = max(Decimal(0), (regular or oliz) - oliz)
            source = "oliz"
        cash = _discounted(base, dealer_cash)
        card = _discounted(base, dealer)
        campaign_snapshot = None
    elif scenario in (PricingScenario.CAMPAIGN, PricingScenario.CAMPAIGN_DEALER):
        if campaign is None:
            partial = True
            base = regular or Decimal(0)
            share = Decimal(0)
            source = "none"
            campaign_snapshot = None
        else:
            base = campaign.price
            share = campaign.share_amount
            source = "campaign"
            campaign_snapshot = campaign.snapshot
        if scenario is PricingScenario.CAMPAIGN:
            cash = base
            card = base
        else:
            cash = _discounted(base, dealer_cash)
            card = _discounted(base, dealer)
    else:  # MANUAL
        if selected is None:
            partial = True
            base = regular or Decimal(0)
            share = Decimal(0)
            source = "none"
        else:
            base = selected.price
            share = selected.share_amount
            source = selected.source.value
        cash = (
            quantize_money(item.input.unit_price_cash)
            if item.input.unit_price_cash is not None
            else _discounted(base, dealer_cash)
        )
        card = (
            quantize_money(item.input.unit_price_card)
            if item.input.unit_price_card is not None
            else _discounted(base, dealer)
        )
        campaign_snapshot = (
            selected.snapshot
            if selected is not None
            and selected.source is CompanyDiscountSource.CAMPAIGN
            else None
        )

    discount = max(Decimal(0), (regular or base) - base)
    return (
        _ComparisonItem(
            sale_card=quantize_money(card),
            sale_cash=quantize_money(cash),
            quantity=item.input.quantity,
            cost=item.cost_price,
            campaign_snapshot=campaign_snapshot,
            regular_price=regular,
            website_price=oliz,
            product_group=item.product_group,
            company_source=source,
            company_discount_amount=discount,
            company_share_amount=share,
        ),
        partial,
    )


def _scenario_summary(
    prepared: list[_PreparedItem],
    scenario: PricingScenario,
    *,
    share_percent: Decimal,
    card_commission_percent: Decimal,
) -> OfferScenarioSummary:
    items: list[_ComparisonItem] = []
    partial = False
    for item in prepared:
        comparison, item_partial = _scenario_item(item, scenario)
        items.append(comparison)
        partial = partial or item_partial
    sale_cash = quantize_money(
        sum((item.sale_cash * item.quantity for item in items), Decimal(0))
    )
    sale_card = quantize_money(
        sum((item.sale_card * item.quantity for item in items), Decimal(0))
    )
    company_share = quantize_money(
        sum(
            (
                quantize_money(
                    item.company_share_amount * share_percent / Decimal(100)
                )
                * item.quantity
                for item in items
            ),
            Decimal(0),
        )
    )
    missing_cost = any(item.cost is None for item in items)
    cost_total = quantize_money(
        sum(
            (item.cost * item.quantity for item in items if item.cost is not None),
            Decimal(0),
        )
    )
    cash_revenue = quantize_money(sale_cash + company_share)
    card_net = quantize_money(
        sale_card * (Decimal(100) - card_commission_percent) / Decimal(100)
    )
    card_revenue = quantize_money(card_net + company_share)
    if missing_cost:
        cash_profit = None
        card_profit = None
        margin = None
    else:
        cash_profit = quantize_money(cash_revenue - cost_total)
        card_profit = quantize_money(card_revenue - cost_total)
        margin = (
            quantize_money(card_profit / card_revenue * Decimal(100))
            if card_revenue
            else None
        )
    label = SCENARIO_LABELS[scenario]
    if partial:
        label = f"{label} (kısmi)"
    return OfferScenarioSummary(
        key=scenario.value,
        label=label,
        sale_cash=sale_cash,
        sale_card=sale_card,
        company_share=company_share,
        total_revenue=card_revenue,
        cost=cost_total,
        cash_profit=cash_profit,
        card_profit=card_profit,
        margin_percent=margin,
        has_missing_cost=missing_cost,
        partial=partial,
    )


def create_offer(
    uow: UnitOfWork,
    data: OfferInput,
    actor: ActorContext | None = None,
) -> uuid.UUID:
    actor = actor or ActorContext()
    now = datetime.now(UTC)
    if not data.items:
        raise ValidationError("En az bir ürün satırı gereklidir.")
    if not (Decimal(0) <= data.dealer_discount_percent <= Decimal(100)):
        raise ValidationError("Kart bayi indirimi %0 ile %100 arasında olmalıdır.")
    if not (
        Decimal(0) <= data.dealer_discount_cash_percent <= Decimal(100)
    ):
        raise ValidationError("Nakit bayi indirimi %0 ile %100 arasında olmalıdır.")

    with uow:
        prepared = _prepare_items(uow, data)
        card_total_estimate = _estimate_card_total(prepared)

    commission_percent = Decimal(0)
    commission_source = "none"
    period = None
    commission_options: list[dict[str, object]] | None = None
    if data.payment_type is PaymentType.CARD:
        if (
            data.channel is None
            or data.installment_count is None
            or data.card_type is None
        ):
            raise ValidationError(
                "Kart teklifi için kanal, taksit ve kart tipi zorunludur."
            )
        resolution = resolve_commission(
            uow,
            channel=data.channel,
            bank_id=data.bank_id,
            product_group=prepared[0].product_group,
            card_type=data.card_type,
            installment_count=data.installment_count,
            total=card_total_estimate,
            category_ids=[
                item.category_id
                for item in prepared
                if item.category_id is not None
            ],
        )
        commission_percent = resolution.commission_percent
        commission_source = resolution.commission_source
        period = resolution.period
        commission_options = [
            {"installment": installment, "percent": str(percent)}
            for installment, percent in resolution.options
        ]

    with uow:
        selected_bank_id = (
            data.bank_id if data.payment_type is PaymentType.CARD else None
        )
        bank = (
            uow.commissions.get_bank(selected_bank_id)
            if selected_bank_id is not None
            else None
        )
        if selected_bank_id is not None and bank is None:
            raise ValidationError("Seçilen banka bulunamadı.")
        extra_totals = _offer_totals(prepared)
        offer = Offer(
            id=uuid.uuid4(),
            customer_name=_clean(data.customer_name),
            customer_phone=_clean(data.customer_phone),
            status=OfferStatus.DRAFT.value,
            payment_type=data.payment_type.value,
            channel=data.channel.value if data.channel else None,
            bank_id=selected_bank_id,
            bank_name_snapshot=bank.name if bank is not None else None,
            installment_count=data.installment_count,
            card_type=data.card_type.value if data.card_type else None,
            dealer_discount_percent=data.dealer_discount_percent,
            dealer_discount_cash_percent=data.dealer_discount_cash_percent,
            commission_period_id=period.id if period else None,
            commission_period_key_snapshot=period.period_key if period else None,
            commission_percent_snapshot=(
                commission_percent if data.payment_type is PaymentType.CARD else None
            ),
            commission_source=commission_source,
            commission_options_snapshot=commission_options,
            dealer_share_percent_snapshot=DEALER_SHARE_PERCENT,
            pricing_version="v2",
            regular_total=extra_totals.regular_total,
            oliz_total=extra_totals.oliz_total,
            company_discount_total=extra_totals.company_discount_total,
            cost_total=extra_totals.cost_total,
            note=_clean(data.note),
            created_at=now,
            updated_at=now,
            created_by_name=actor.worker_name,
            created_by_device=actor.device_name,
        )
        uow.offers.add(offer)
        items = _build_items(
            uow, offer, prepared, data, commission_percent, actor, now
        )
        uow.offers.add_items(items)
        totals = _totals(prepared, data, commission_percent)
        offer.cash_total = totals.cash_total
        offer.card_total = totals.card_total
        offer.selected_total = totals.selected_total
        uow.offers.save(offer)
        uow.offers.add_history(
            OfferHistory(
                id=uuid.uuid4(),
                offer_id=offer.id,
                old_status=None,
                new_status=OfferStatus.DRAFT.value,
                note="Teklif oluşturuldu",
                changed_at=now,
                changed_by_name=actor.worker_name,
                changed_by_device=actor.device_name,
            )
        )
        uow.commit()
        return offer.id


def update_offer(
    uow: UnitOfWork,
    offer_id: uuid.UUID,
    data: OfferInput,
    actor: ActorContext | None = None,
) -> uuid.UUID:
    actor = actor or ActorContext()
    now = datetime.now(UTC)
    if not (Decimal(0) <= data.dealer_discount_percent <= Decimal(100)):
        raise ValidationError("Kart bayi indirimi %0 ile %100 arasında olmalıdır.")
    if not (
        Decimal(0) <= data.dealer_discount_cash_percent <= Decimal(100)
    ):
        raise ValidationError("Nakit bayi indirimi %0 ile %100 arasında olmalıdır.")
    with uow:
        offer = uow.offers.get_for_update(offer_id)
        if offer is None:
            raise NotFoundError("Teklif bulunamadı.")
        if offer.status != OfferStatus.DRAFT.value:
            raise ValidationError("Yalnızca taslak teklif düzenlenebilir.")
        prepared = _prepare_items(uow, data)
        card_total_estimate = _estimate_card_total(prepared)
    commission_percent = Decimal(0)
    commission_source = "none"
    period = None
    commission_options: list[dict[str, object]] | None = None
    if data.payment_type is PaymentType.CARD:
        if not data.channel or not data.installment_count or not data.card_type:
            raise ValidationError(
                "Kart teklifi için kanal, taksit ve kart tipi zorunludur."
            )
        resolution = resolve_commission(
            uow,
            channel=data.channel,
            bank_id=data.bank_id,
            product_group=prepared[0].product_group,
            card_type=data.card_type,
            installment_count=data.installment_count,
            total=card_total_estimate,
            category_ids=[
                item.category_id
                for item in prepared
                if item.category_id is not None
            ],
        )
        commission_percent = resolution.commission_percent
        commission_source = resolution.commission_source
        period = resolution.period
        commission_options = [
            {"installment": installment, "percent": str(percent)}
            for installment, percent in resolution.options
        ]

    with uow:
        offer = uow.offers.get_for_update(offer_id)
        if offer is None:
            raise NotFoundError("Teklif bulunamadı.")
        uow.offers.delete_items(offer_id)
        selected_bank_id = (
            data.bank_id if data.payment_type is PaymentType.CARD else None
        )
        bank = (
            uow.commissions.get_bank(selected_bank_id)
            if selected_bank_id is not None
            else None
        )
        if selected_bank_id is not None and bank is None:
            raise ValidationError("Seçilen banka bulunamadı.")
        offer.customer_name = _clean(data.customer_name)
        offer.customer_phone = _clean(data.customer_phone)
        offer.payment_type = data.payment_type.value
        offer.channel = data.channel.value if data.channel else None
        offer.bank_id = selected_bank_id
        offer.bank_name_snapshot = bank.name if bank is not None else None
        offer.installment_count = data.installment_count
        offer.card_type = data.card_type.value if data.card_type else None
        offer.dealer_discount_percent = data.dealer_discount_percent
        offer.dealer_discount_cash_percent = data.dealer_discount_cash_percent
        offer.commission_period_id = period.id if period else None
        offer.commission_period_key_snapshot = period.period_key if period else None
        offer.commission_percent_snapshot = (
            commission_percent if data.payment_type is PaymentType.CARD else None
        )
        offer.commission_source = commission_source
        offer.commission_options_snapshot = commission_options
        offer.dealer_share_percent_snapshot = DEALER_SHARE_PERCENT
        extra_totals = _offer_totals(prepared)
        offer.pricing_version = "v2"
        offer.regular_total = extra_totals.regular_total
        offer.oliz_total = extra_totals.oliz_total
        offer.company_discount_total = extra_totals.company_discount_total
        offer.cost_total = extra_totals.cost_total
        offer.note = _clean(data.note)
        offer.updated_at = now
        items = _build_items(
            uow, offer, prepared, data, commission_percent, actor, now
        )
        uow.offers.add_items(items)
        totals = _totals(prepared, data, commission_percent)
        offer.cash_total = totals.cash_total
        offer.card_total = totals.card_total
        offer.selected_total = totals.selected_total
        uow.offers.save(offer)
        uow.commit()
        return offer.id


def delete_offer(uow: UnitOfWork, offer_id: uuid.UUID) -> None:
    with uow:
        offer = uow.offers.get_for_update(offer_id)
        if offer is None:
            raise NotFoundError("Teklif bulunamadı.")
        uow.offers.delete(offer_id)
        uow.commit()


def get_offer_detail(uow: UnitOfWork, offer_id: uuid.UUID) -> OfferDetail | None:
    with uow:
        offer = uow.offers.get(offer_id)
        if offer is None:
            return None
        return OfferDetail(
            offer=offer,
            items=tuple(uow.offers.get_items(offer_id)),
            history=tuple(uow.offers.get_history(offer_id)),
        )


def list_offers(
    uow: UnitOfWork,
    *,
    status: str | None = None,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    with uow:
        return uow.offers.list(
            status=status, query=query, limit=limit, offset=offset
        )


def set_offer_status(
    uow: UnitOfWork,
    offer_id: uuid.UUID,
    target_status: str,
    *,
    note: str | None = None,
    actor: ActorContext | None = None,
) -> None:
    actor = actor or ActorContext()
    now = datetime.now(UTC)
    with uow:
        offer = uow.offers.get_for_update(offer_id)
        if offer is None:
            raise NotFoundError("Teklif bulunamadı.")
        try:
            target = OfferStatus(target_status)
            current = OfferStatus(offer.status)
            ensure_status_transition(current, target)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        offer.status = target.value
        offer.updated_at = now
        uow.offers.save(offer)
        uow.offers.add_history(
            OfferHistory(
                id=uuid.uuid4(),
                offer_id=offer.id,
                old_status=current.value,
                new_status=target.value,
                note=_clean(note),
                changed_at=now,
                changed_by_name=actor.worker_name,
                changed_by_device=actor.device_name,
            )
        )
        uow.commit()


def convert_offer_to_reservation(
    uow: UnitOfWork,
    offer_id: uuid.UUID,
    actor: ActorContext | None = None,
) -> uuid.UUID:
    actor = actor or ActorContext()
    with uow:
        offer = uow.offers.get(offer_id)
        if offer is None:
            raise NotFoundError("Teklif bulunamadı.")
        if offer.converted_reservation_id is not None:
            return offer.converted_reservation_id
        if offer.status != OfferStatus.ACCEPTED.value:
            raise ValidationError("Yalnızca kabul edilmiş teklif rezervasyona dönüşür.")
        items = uow.offers.get_items(offer_id)
        reservation_items = []
        for item in items:
            if item.product_id is None:
                raise ValidationError(
                    "Ürünü silinmiş teklif satırı rezervasyona dönüştürülemez."
                )
            reservation_items.append(
                NewReservationItem(item.product_id, item.quantity)
            )
        customer_name = offer.customer_name or "Teklif müşterisi"
        note = f"Teklif #{offer.offer_number} dönüşümü"

    view = create_reservation(
        uow,
        customer_name=customer_name,
        items=reservation_items,
        note=note,
        actor=actor,
    )
    with uow:
        offer = uow.offers.get_for_update(offer_id)
        if offer is not None:
            offer.converted_reservation_id = view.id
            uow.offers.save(offer)
            uow.commit()
    return view.id


def reserve_offer(
    uow: UnitOfWork,
    offer_id: uuid.UUID,
    actor: ActorContext | None = None,
) -> uuid.UUID:
    """Create a reservation from an offer and mark the offer accepted.

    This is the quick path from the offer detail screen. It is idempotent: an
    offer that already has a converted reservation returns the same id.
    """
    actor = actor or ActorContext()
    with uow:
        offer = uow.offers.get_for_update(offer_id)
        if offer is None:
            raise NotFoundError("Teklif bulunamadı.")
        if offer.converted_reservation_id is not None:
            return offer.converted_reservation_id
        if offer.status in (OfferStatus.LOST.value, OfferStatus.EXPIRED.value):
            raise ValidationError(
                "Kaybedilmiş veya geçersiz teklif rezervasyona dönüştürülemez."
            )
        items = uow.offers.get_items(offer_id)
        reservation_items: list[NewReservationItem] = []
        for item in items:
            if item.product_id is None:
                raise ValidationError(
                    "Ürünü silinmiş teklif satırı rezervasyona dönüştürülemez."
                )
            reservation_items.append(
                NewReservationItem(item.product_id, item.quantity)
            )
        if not reservation_items:
            raise ValidationError("Teklifte rezervasyona alınacak ürün yok.")
        customer_name = offer.customer_name or "Teklif müşterisi"
        offer_number = offer.offer_number
        note = f"Teklif #{offer_number} rezervasyonu"

    view = create_reservation(
        uow,
        customer_name=customer_name,
        items=reservation_items,
        note=note,
        actor=actor,
    )
    with uow:
        offer = uow.offers.get_for_update(offer_id)
        if offer is not None:
            offer.converted_reservation_id = view.id
            if offer.status != OfferStatus.ACCEPTED.value:
                old_status = offer.status
                offer.status = OfferStatus.ACCEPTED.value
                uow.offers.add_history(
                    OfferHistory(
                        id=uuid.uuid4(),
                        offer_id=offer.id,
                        old_status=old_status,
                        new_status=OfferStatus.ACCEPTED.value,
                        note=f"Rezervasyon açıldı: #{view.reservation_number}",
                        changed_at=datetime.now(UTC),
                        changed_by_name=actor.worker_name,
                        changed_by_device=actor.device_name,
                    )
                )
            uow.offers.save(offer)
            uow.commit()
    return view.id


def sell_offer(
    uow: UnitOfWork,
    offer_id: uuid.UUID,
    *,
    low_stock_reason: str | None = None,
    actor: ActorContext | None = None,
) -> uuid.UUID:
    """Create a reservation from the offer and immediately deliver all lines.

    Stock is reduced through the normal reservation delivery path so stock
    movements and reservation events stay consistent. Repeated clicks are
    idempotent per reservation line.
    """
    actor = actor or ActorContext()
    reason = _clean(low_stock_reason)
    with uow:
        offer = uow.offers.get(offer_id)
        if offer is None:
            raise NotFoundError("Teklif bulunamadı.")
        if offer.status in (OfferStatus.LOST.value, OfferStatus.EXPIRED.value):
            raise ValidationError(
                "Kaybedilmiş veya geçersiz teklif teslim edilemez."
            )
        offer_number = offer.offer_number

    reservation_id = reserve_offer(uow, offer_id, actor)
    with uow:
        if uow.reservations.get(reservation_id) is None:
            raise NotFoundError("Rezervasyon bulunamadı.")
        lines = uow.reservations.get_items(reservation_id)
        quantities: dict[uuid.UUID, int] = {}
        for line in lines:
            open_quantity = (
                line.quantity - line.delivered_quantity - line.cancelled_quantity
            )
            if open_quantity <= 0:
                continue
            if line.product_id is None:
                raise ValidationError(
                    "Ürün kaydı silinmiş; teslimat yapılamaz."
                )
            quantities[line.product_id] = (
                quantities.get(line.product_id, 0) + open_quantity
            )
        products = {
            product.id: product
            for product in uow.products.get_by_ids(list(quantities))
        }
        for product_id, quantity in quantities.items():
            product = products.get(product_id)
            if product is None:
                raise ValidationError(
                    "Ürün kaydı silinmiş; teslimat yapılamaz."
                )
            if quantity > product.physical_stock and reason is None:
                raise ValidationError(
                    "Fiziksel stok yetersiz; teslim için gerekçe girilmelidir."
                )
        actions = [
            (
                line.id,
                line.quantity - line.delivered_quantity - line.cancelled_quantity,
            )
            for line in lines
            if line.quantity - line.delivered_quantity - line.cancelled_quantity > 0
        ]

    for line_id, quantity in actions:
        deliver_item(
            uow,
            line_id,
            quantity=quantity,
            idempotency_key=f"offer-sale:{offer_id}:{line_id}",
            low_stock_reason=reason,
            note=f"Teklif #{offer_number} hızlı satış",
            actor=actor,
        )
    return reservation_id


def _prepare_items(
    uow: UnitOfWork, data: OfferInput
) -> list[_PreparedItem]:
    products = {
        product.id: product
        for product in uow.products.get_by_ids(
            [item.product_id for item in data.items]
        )
    }
    prepared: list[_PreparedItem] = []
    for item in data.items:
        product = products.get(item.product_id)
        if product is None:
            raise ValidationError("Seçilen ürünlerden bazıları bulunamadı.")
        pricing = uow.dealer_pricing.get(product.id)
        category = (
            uow.products.get_category(product.category_id)
            if getattr(product, "category_id", None)
            else None
        )
        group_value = getattr(category, "commission_group", "other") if category else "other"
        try:
            product_group = ProductCommissionGroup(group_value)
        except ValueError:
            product_group = ProductCommissionGroup.OTHER
        layers = OfferPriceLayers(
            cost_price=product.cost_price,
            regular_price=product.regular_price,
            website_price=normalize_website_price(
                product.website_discounted_price
            ),
        )
        campaign_candidates: list[CompanyPriceCandidate] = []
        mode = "none"
        if item.campaign_id is not None:
            mode = str(item.campaign_id)
            campaign_candidates.append(
                _campaign_candidate(
                    uow,
                    item.campaign_id,
                    product,
                    item.gift_present,
                    data.dealer_discount_percent,
                    layers,
                )
            )
        elif item.auto_campaign:
            mode = "auto"
            seen_campaigns: set[uuid.UUID] = set()
            for link in uow.campaigns.active_for_product(
                product.id, as_of=datetime.now(UTC)
            ):
                if link.campaign.id in seen_campaigns:
                    continue
                seen_campaigns.add(link.campaign.id)
                try:
                    campaign_candidates.append(
                        _campaign_candidate(
                            uow,
                            link.campaign.id,
                            product,
                            item.gift_present,
                            data.dealer_discount_percent,
                            layers,
                        )
                    )
                except (ValidationError, ValueError):
                    # A broken campaign must not hide the other valid offers.
                    continue
        selected = select_company_price(
            regular_price=layers.regular_price,
            oliz_price=layers.website_price,
            campaigns=tuple(campaign_candidates),
            mode=mode,
        )
        best_campaign = max(
            campaign_candidates,
            key=lambda candidate: candidate.discount_amount,
            default=None,
        )
        campaign_version_id = None
        campaign_snapshot = None
        if selected is not None and selected.source is CompanyDiscountSource.CAMPAIGN:
            campaign_snapshot = selected.snapshot
            if campaign_snapshot is not None:
                campaign_version_id = uuid.UUID(
                    str(campaign_snapshot["version_id"])
                )
            layers = OfferPriceLayers(
                cost_price=layers.cost_price,
                regular_price=layers.regular_price,
                website_price=None,
                campaign_price=selected.price,
                campaign_name=selected.campaign_name,
                campaign_gift_present=item.gift_present,
            )
        elif selected is not None and selected.source is CompanyDiscountSource.OLIZ:
            layers = OfferPriceLayers(
                cost_price=layers.cost_price,
                regular_price=layers.regular_price,
                website_price=selected.price,
            )
        elif selected is not None:
            layers = OfferPriceLayers(
                cost_price=layers.cost_price,
                regular_price=layers.regular_price,
                website_price=None,
            )
        prepared.append(
            _PreparedItem(
                product=product,
                input=item,
                layers=layers,
                pricing=pricing,
                dealer_discount=data.dealer_discount_percent,
                dealer_discount_cash=data.dealer_discount_cash_percent,
                product_group=product_group,
                category_id=getattr(product, "category_id", None),
                campaign_version_id=campaign_version_id,
                campaign_snapshot=campaign_snapshot,
                company=selected,
                best_campaign=best_campaign,
                regular_price=layers.regular_price,
                oliz_price=normalize_website_price(
                    product.website_discounted_price
                ),
                cost_price=layers.cost_price,
            )
        )
    return prepared


def _campaign_candidate(
    uow: UnitOfWork,
    campaign_id: uuid.UUID,
    product: object,
    gift_present: bool | None,
    dealer_discount: Decimal,
    layers: OfferPriceLayers,
) -> CompanyPriceCandidate:
    campaign_price, campaign_name, snapshot = _campaign_price(
        uow,
        campaign_id,
        product,
        gift_present,
        dealer_discount,
        layers,
    )
    regular = layers.regular_price
    if regular is not None and campaign_price is not None:
        discount = max(quantize_money(regular - campaign_price), Decimal(0))
    else:
        discount = Decimal(0)
    raw_share = snapshot.get("campaign_discount_amount")
    share = Decimal(str(raw_share)) if raw_share is not None else Decimal(0)
    raw_base = snapshot.get("campaign_base_price")
    raw_price = snapshot.get("campaign_price")
    return CompanyPriceCandidate(
        source=CompanyDiscountSource.CAMPAIGN,
        price=campaign_price,
        discount_amount=discount,
        share_amount=share,
        campaign_id=str(campaign_id),
        campaign_name=campaign_name,
        campaign_discount_amount=share,
        campaign_base_price=(
            Decimal(str(raw_base)) if raw_base is not None else None
        ),
        campaign_price=(
            Decimal(str(raw_price)) if raw_price is not None else campaign_price
        ),
        warning=snapshot.get("warning"),
        snapshot=snapshot,
    )



@dataclass(frozen=True)
class LineCampaignPreview:
    key: str
    source: str
    campaign_id: str | None
    campaign_name: str | None
    price: Decimal
    discount_amount: Decimal
    share_amount: Decimal
    discount_type: str | None = None
    discount_value: Decimal | None = None
    gift_description: str | None = None


@dataclass(frozen=True)
class OfferLinePreview:
    product_id: str
    product_name: str
    regular_price: Decimal | None
    oliz_price: Decimal | None
    cost_price: Decimal | None
    previews: dict[str, LineCampaignPreview]


def preview_offer_line(
    uow: UnitOfWork,
    product_id: uuid.UUID,
    *,
    dealer_discount_percent: Decimal,
    dealer_discount_cash_percent: Decimal,
    gift_present: bool | None = None,
) -> OfferLinePreview | None:
    """Return campaign/Oliz previews for one product in the offer basket."""
    with uow:
        product = uow.products.get_by_id(product_id)
        if product is None:
            return None
        layers = OfferPriceLayers(
            cost_price=product.cost_price,
            regular_price=product.regular_price,
            website_price=normalize_website_price(
                product.website_discounted_price
            ),
        )
        candidates: list[CompanyPriceCandidate] = []
        seen: set[uuid.UUID] = set()
        for link in uow.campaigns.active_for_product(
            product.id, as_of=datetime.now(UTC)
        ):
            if link.campaign.id in seen:
                continue
            seen.add(link.campaign.id)
            try:
                candidates.append(
                    _campaign_candidate(
                        uow,
                        link.campaign.id,
                        product,
                        gift_present,
                        dealer_discount_percent,
                        layers,
                    )
                )
            except (ValidationError, ValueError):
                continue
        oliz = oliz_candidate(layers.regular_price, layers.website_price)
        regular = regular_candidate(layers.regular_price)
        auto = select_company_price(
            regular_price=layers.regular_price,
            oliz_price=layers.website_price,
            campaigns=tuple(candidates),
            mode="auto",
        )

    previews: dict[str, LineCampaignPreview] = {}
    none_candidate = oliz or regular
    if none_candidate is not None:
        previews["none"] = _line_preview(none_candidate, "none")
    for candidate in candidates:
        if candidate.campaign_id is not None:
            previews[candidate.campaign_id] = _line_preview(
                candidate, candidate.campaign_id
            )
    if auto is not None:
        previews["auto"] = _line_preview(auto, "auto")
    return OfferLinePreview(
        product_id=str(product.id),
        product_name=product.name,
        regular_price=layers.regular_price,
        oliz_price=layers.website_price,
        cost_price=layers.cost_price,
        previews=previews,
    )


def _line_preview(
    candidate: CompanyPriceCandidate, key: str
) -> LineCampaignPreview:
    snapshot = candidate.snapshot or {}
    raw_value = snapshot.get("discount_value")
    return LineCampaignPreview(
        key=key,
        source=candidate.source.value,
        campaign_id=candidate.campaign_id,
        campaign_name=candidate.campaign_name,
        price=candidate.price,
        discount_amount=candidate.discount_amount,
        share_amount=candidate.share_amount,
        discount_type=(
            str(snapshot["discount_type"])
            if snapshot.get("discount_type") is not None
            else None
        ),
        discount_value=(
            Decimal(str(raw_value)) if raw_value is not None else None
        ),
        gift_description=(
            str(snapshot["gift_description"])
            if snapshot.get("gift_description") is not None
            else None
        ),
    )


def _campaign_price(
    uow: UnitOfWork,
    campaign_id: uuid.UUID,
    product: object,
    gift_present: bool | None,
    dealer_discount: Decimal,
    layers: OfferPriceLayers,
) -> tuple[Decimal | None, str | None, dict[str, object]]:
    version = uow.campaigns.get_current_version(campaign_id)
    if version is None:
        raise ValidationError("Seçilen kampanya bulunamadı.")
    links = uow.campaigns.get_version_products(version.id)
    contract = _contract_from_row(version, links)
    prices = CampaignPriceInput(
        regular_price=layers.regular_price,
        website_discounted_price=layers.website_price,
    )
    scenarios = campaign_scenarios(contract, prices, dealer_discount)
    chosen = next(
        (
            scenario
            for scenario in scenarios
            if scenario.gift_present is bool(gift_present)
        ),
        scenarios[0] if scenarios else None,
    )
    if chosen is None:
        raise ValidationError("Seçilen kampanya için fiyat senaryosu üretilemedi.")
    quote = campaign_discount_price(contract, chosen.base_price)
    if quote.final_price is None:
        raise ValidationError("Seçilen kampanya için fiyat senaryosu üretilemedi.")
    warning = "; ".join(
        item for item in (chosen.warning, quote.warning) if item
    ) or None
    snapshot = {
        "campaign_id": str(campaign_id),
        "version_id": str(version.id),
        "version_no": version.version_no,
        "name": version.name,
        "description": contract.description,
        "gift_description": contract.gift_description,
        "campaign_type": contract.campaign_type.value,
        "base_price_type": contract.base_price_type.value,
        "discount_type": contract.discount_type.value,
        "discount_value": (
            str(contract.discount_value)
            if contract.discount_value is not None
            else None
        ),
        "gift_present": chosen.gift_present,
        "campaign_base_price": (
            str(quote.base_price) if quote.base_price is not None else None
        ),
        "campaign_price": str(quote.final_price),
        "campaign_discount_amount": str(quote.discount_amount or Decimal(0)),
        "final_price": str(quote.final_price),
        "warning": warning,
    }
    return quote.final_price, version.name, snapshot


def _build_items(
    uow: UnitOfWork,
    offer: Offer,
    prepared: list[_PreparedItem],
    data: OfferInput,
    commission_percent: Decimal,
    actor: ActorContext,
    now: datetime,
) -> list[OfferItem]:
    target = uow.commissions.get_profit_target(
        scope_type="global", scope_id=None, as_of=now
    )
    target_type = (
        ProfitTargetType(target.target_type) if target is not None else None
    )
    target_value = target.target_value if target is not None else None
    rows: list[OfferItem] = []
    for position, prepared_item in enumerate(prepared):
        quote = quote_offer_item(
            prepared_item.layers,
            quantity=prepared_item.input.quantity,
            dealer_discount_percent=prepared_item.dealer_discount,
            dealer_discount_cash_percent=prepared_item.dealer_discount_cash,
            commission_percent=commission_percent,
            target_type=target_type,
            target_value=target_value,
            cash_floor=getattr(prepared_item.pricing, "cash_floor_price", None),
            card_floor=getattr(prepared_item.pricing, "card_floor_price", None),
            unit_price_cash=prepared_item.input.unit_price_cash,
            unit_price_card=prepared_item.input.unit_price_card,
        )
        product = prepared_item.product
        company = prepared_item.company
        rows.append(
            OfferItem(
                id=uuid.uuid4(),
                offer_id=offer.id,
                product_id=product.id,
                product_name_snapshot=product.name,
                quantity=prepared_item.input.quantity,
                regular_price_snapshot=prepared_item.regular_price,
                website_price_snapshot=prepared_item.oliz_price,
                cost_price_snapshot=prepared_item.cost_price,
                campaign_version_id=prepared_item.campaign_version_id,
                campaign_name_snapshot=prepared_item.layers.campaign_name,
                campaign_snapshot=prepared_item.campaign_snapshot,
                campaign_gift_present=prepared_item.layers.campaign_gift_present,
                base_price_used=quote.base_price,
                company_discount_source=(
                    company.source.value if company is not None else "none"
                ),
                company_discount_amount=(
                    company.discount_amount if company is not None else Decimal(0)
                ),
                company_share_amount=(
                    company.share_amount if company is not None else Decimal(0)
                ),
                campaign_discount_amount=(
                    company.campaign_discount_amount
                    if company is not None
                    else None
                ),
                campaign_base_price=(
                    company.campaign_base_price if company is not None else None
                ),
                campaign_price=(
                    company.campaign_price if company is not None else None
                ),
                dealer_discount_percent=prepared_item.dealer_discount,
                dealer_discount_cash_percent=prepared_item.dealer_discount_cash,
                suggested_cash_price=quote.suggested_cash_price,
                suggested_card_price=quote.suggested_card_price,
                unit_price_cash=quote.unit_price_cash,
                unit_price_card=quote.unit_price_card,
                line_total_cash=quote.line_total_cash,
                line_total_card=quote.line_total_card,
                warning_text="; ".join(quote.warnings) or None,
                position=position,
            )
        )
    return rows


def _totals(
    prepared: list[_PreparedItem],
    data: OfferInput,
    commission_percent: Decimal,
) -> object:
    quotes = []
    for item in prepared:
        quotes.append(
            quote_offer_item(
                item.layers,
                quantity=item.input.quantity,
                dealer_discount_percent=item.dealer_discount,
                dealer_discount_cash_percent=item.dealer_discount_cash,
                commission_percent=commission_percent,
                target_type=None,
                target_value=None,
                cash_floor=getattr(item.pricing, "cash_floor_price", None),
                card_floor=getattr(item.pricing, "card_floor_price", None),
                unit_price_cash=item.input.unit_price_cash,
                unit_price_card=item.input.unit_price_card,
            )
        )
    return summarize_offer(quotes, data.payment_type)


@dataclass(frozen=True)
class _OfferTotals:
    regular_total: Decimal
    oliz_total: Decimal
    company_discount_total: Decimal
    cost_total: Decimal


def _offer_totals(prepared: list[_PreparedItem]) -> _OfferTotals:
    regular_total = Decimal(0)
    oliz_total = Decimal(0)
    company_discount_total = Decimal(0)
    cost_total = Decimal(0)
    for item in prepared:
        quantity = item.input.quantity
        if item.regular_price is not None:
            regular_total += item.regular_price * quantity
        if item.oliz_price is not None:
            oliz_total += item.oliz_price * quantity
        if item.company is not None:
            company_discount_total += item.company.discount_amount * quantity
        if item.cost_price is not None:
            cost_total += item.cost_price * quantity
    return _OfferTotals(
        regular_total=quantize_money(regular_total),
        oliz_total=quantize_money(oliz_total),
        company_discount_total=quantize_money(company_discount_total),
        cost_total=quantize_money(cost_total),
    )


def _product_group_for(product: object) -> ProductCommissionGroup:
    group = getattr(product, "commission_group", None)
    if group is None:
        category = getattr(product, "category", None)
        group = getattr(category, "commission_group", "other") if category else "other"
    try:
        return ProductCommissionGroup(group)
    except ValueError:
        return ProductCommissionGroup.OTHER


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
