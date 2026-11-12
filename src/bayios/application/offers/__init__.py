from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from bayios.adapters.db.models.offers import Offer, OfferHistory, OfferItem
from bayios.application.campaigns import _contract_from_row
from bayios.application.commissions import resolve_commission
from bayios.application.errors import NotFoundError, ValidationError
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.reservations import NewReservationItem, create_reservation
from bayios.domain.campaigns import CampaignPriceInput, campaign_scenarios
from bayios.domain.commissions import (
    CardType,
    PaymentChannel,
    ProductCommissionGroup,
    ProfitTargetType,
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
from bayios.domain.products import ActorContext


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
        margin = (
            (selected.profit / selected.total_revenue * Decimal(100))
            if selected.profit is not None and selected.total_revenue
            else None
        )
        lines.append(
            OfferProfitLine(
                item=analysis.item,
                sale_price=(
                    analysis.sale_price_cash
                    if offer.payment_type == PaymentType.CASH.value
                    else analysis.sale_price_card
                ),
                installment_count=selected.installment_count,
                commission_percent=selected.commission_percent,
                net_after_commission=selected.net_after_commission,
                campaign_share=selected.campaign_share,
                oliz_share=selected.oliz_share,
                total_revenue=selected.total_revenue,
                cost=selected.cost,
                profit=selected.profit,
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
    product_group: ProductCommissionGroup
    campaign_version_id: uuid.UUID | None = None
    campaign_snapshot: dict[str, object] | None = None


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
        raise ValidationError("Bayi indirimi %0 ile %100 arasında olmalıdır.")

    with uow:
        prepared = _prepare_items(uow, data)
        base_total = sum(
            (item.layers.base_price or Decimal(0)) * item.input.quantity
            for item in prepared
        )

    commission_percent = Decimal(0)
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
            total=base_total,
        )
        commission_percent = resolution.commission_percent
        period = resolution.period
        commission_options = [
            {"installment": installment, "percent": str(percent)}
            for installment, percent in resolution.options
        ]

    with uow:
        offer = Offer(
            id=uuid.uuid4(),
            customer_name=_clean(data.customer_name),
            customer_phone=_clean(data.customer_phone),
            status=OfferStatus.DRAFT.value,
            payment_type=data.payment_type.value,
            channel=data.channel.value if data.channel else None,
            bank_id=data.bank_id,
            installment_count=data.installment_count,
            card_type=data.card_type.value if data.card_type else None,
            dealer_discount_percent=data.dealer_discount_percent,
            commission_period_id=period.id if period else None,
            commission_period_key_snapshot=period.period_key if period else None,
            commission_percent_snapshot=(
                commission_percent if data.payment_type is PaymentType.CARD else None
            ),
            commission_options_snapshot=commission_options,
            dealer_share_percent_snapshot=DEALER_SHARE_PERCENT,
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
    with uow:
        offer = uow.offers.get_for_update(offer_id)
        if offer is None:
            raise NotFoundError("Teklif bulunamadı.")
        if offer.status != OfferStatus.DRAFT.value:
            raise ValidationError("Yalnızca taslak teklif düzenlenebilir.")
        prepared = _prepare_items(uow, data)
        base_total = sum(
            (item.layers.base_price or Decimal(0)) * item.input.quantity
            for item in prepared
        )
    commission_percent = Decimal(0)
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
            total=base_total,
        )
        commission_percent = resolution.commission_percent
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
        offer.customer_name = _clean(data.customer_name)
        offer.customer_phone = _clean(data.customer_phone)
        offer.payment_type = data.payment_type.value
        offer.channel = data.channel.value if data.channel else None
        offer.bank_id = data.bank_id
        offer.installment_count = data.installment_count
        offer.card_type = data.card_type.value if data.card_type else None
        offer.dealer_discount_percent = data.dealer_discount_percent
        offer.commission_period_id = period.id if period else None
        offer.commission_period_key_snapshot = period.period_key if period else None
        offer.commission_percent_snapshot = (
            commission_percent if data.payment_type is PaymentType.CARD else None
        )
        offer.commission_options_snapshot = commission_options
        offer.dealer_share_percent_snapshot = DEALER_SHARE_PERCENT
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
            website_price=product.website_discounted_price,
        )
        campaign_version_id = None
        campaign_snapshot = None
        campaign_id = item.campaign_id
        if campaign_id is None and item.auto_campaign:
            active_links = uow.campaigns.active_for_product(
                product.id, as_of=datetime.now(UTC)
            )
            if active_links:
                campaign_id = active_links[0].campaign.id
        if campaign_id is not None:
            campaign_price, campaign_name, snapshot = _campaign_price(
                uow,
                campaign_id,
                product,
                item.gift_present,
                data.dealer_discount_percent,
                layers,
            )
            campaign_version_id = uuid.UUID(str(snapshot["version_id"]))
            campaign_snapshot = snapshot
            layers = OfferPriceLayers(
                cost_price=layers.cost_price,
                regular_price=layers.regular_price,
                website_price=None,
                campaign_price=campaign_price,
                campaign_name=campaign_name,
                campaign_gift_present=item.gift_present,
            )
        prepared.append(
            _PreparedItem(
                product=product,
                input=item,
                layers=layers,
                pricing=pricing,
                dealer_discount=data.dealer_discount_percent,
                product_group=product_group,
                campaign_version_id=campaign_version_id,
                campaign_snapshot=campaign_snapshot,
            )
        )
    return prepared


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
    if chosen is None or chosen.final_price is None:
        raise ValidationError("Seçilen kampanya için fiyat senaryosu üretilemedi.")
    snapshot = {
        "campaign_id": str(campaign_id),
        "version_id": str(version.id),
        "version_no": version.version_no,
        "name": version.name,
        "campaign_type": contract.campaign_type.value,
        "base_price_type": contract.base_price_type.value,
        "discount_type": contract.discount_type.value,
        "discount_value": (
            str(contract.discount_value)
            if contract.discount_value is not None
            else None
        ),
        "gift_present": chosen.gift_present,
        "final_price": str(chosen.final_price),
        "warning": chosen.warning,
    }
    return chosen.final_price, version.name, snapshot


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
            commission_percent=commission_percent,
            target_type=target_type,
            target_value=target_value,
            cash_floor=getattr(prepared_item.pricing, "cash_floor_price", None),
            card_floor=getattr(prepared_item.pricing, "card_floor_price", None),
            unit_price_cash=prepared_item.input.unit_price_cash,
            unit_price_card=prepared_item.input.unit_price_card,
        )
        product = prepared_item.product
        rows.append(
            OfferItem(
                id=uuid.uuid4(),
                offer_id=offer.id,
                product_id=product.id,
                product_name_snapshot=product.name,
                quantity=prepared_item.input.quantity,
                regular_price_snapshot=product.regular_price,
                website_price_snapshot=product.website_discounted_price,
                cost_price_snapshot=product.cost_price,
                campaign_version_id=prepared_item.campaign_version_id,
                campaign_name_snapshot=prepared_item.layers.campaign_name,
                campaign_snapshot=prepared_item.campaign_snapshot,
                campaign_gift_present=prepared_item.layers.campaign_gift_present,
                base_price_used=quote.base_price,
                dealer_discount_percent=prepared_item.dealer_discount,
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
