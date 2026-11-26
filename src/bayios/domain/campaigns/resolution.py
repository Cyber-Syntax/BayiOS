from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations

from bayios.domain.campaigns import (
    BasePriceType,
    CampaignContract,
    CampaignProductLink,
    DiscountType,
    PaymentContext,
    link_discount_price,
)
from bayios.domain.dealer_pricing import HUNDRED, ZERO, quantize_money

# Pure basket-level campaign resolution.
#
# The POS applies at most one company discount per product line. A campaign can
# be a per-line discount (for example Düğün: 10% on every wedding product) or a
# one-time basket discount (for example 17.850 TL on a dryer when a qualifying
# appliance is also in the basket). A one-time amount is allocated pro rata
# across the participating lines. When several combinations are possible the
# resolution that gives the largest total discount wins, matching POS behaviour.


@dataclass(frozen=True)
class BasketLine:
    """One offer line as needed by the campaign engine."""

    key: str
    product_id: str
    category_id: str | None
    quantity: int
    regular_price: Decimal | None
    website_price: Decimal | None = None
    manual_price: Decimal | None = None

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("Sepet satırı miktarı sıfırdan büyük olmalıdır.")

    @property
    def regular_total(self) -> Decimal:
        return quantize_money((self.regular_price or ZERO) * self.quantity)


@dataclass(frozen=True)
class BasketCampaign:
    """An active campaign version in a form the resolver understands."""

    campaign_id: str
    version_id: str
    name: str
    version_no: int
    contract: CampaignContract


@dataclass(frozen=True)
class LineBenefit:
    """The company discount selected for one basket line."""

    key: str
    source: str
    campaign_id: str | None
    campaign_name: str | None
    campaign_version_id: str | None
    campaign_version_no: int | None
    base_price: Decimal | None
    final_price: Decimal | None
    unit_discount: Decimal
    unit_share: Decimal
    campaign_base_price: Decimal | None = None
    campaign_price: Decimal | None = None
    discount_type: str | None = None
    discount_value: Decimal | None = None
    base_price_type: str | None = None
    applies_per_unit: bool | None = None
    is_flat_allocation: bool = False
    warning: str | None = None


@dataclass(frozen=True)
class BasketResolution:
    lines: dict[str, LineBenefit]
    applied_campaign_ids: tuple[str, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Alternative:
    benefit: LineBenefit
    unit_discount: Decimal


@dataclass(frozen=True)
class _FlatApplication:
    campaign: BasketCampaign
    link: CampaignProductLink
    total: Decimal
    allocations: dict[str, Decimal]
    trigger_key: str | None
    target_keys: tuple[str, ...]
    score: Decimal
    warning: str | None = None

    @property
    def participant_keys(self) -> frozenset[str]:
        return frozenset(self.allocations)


def resolve_basket(
    lines: Sequence[BasketLine],
    campaigns: Sequence[BasketCampaign],
    *,
    preferences: Mapping[str, str] | None = None,
    payment: PaymentContext | None = None,
) -> BasketResolution:
    """Resolve the POS-consistent campaign discount for every line.

    preferences maps a line key to auto, none or a campaign id. auto allows
    every campaign, none keeps only Oliz and an explicit id restricts that line
    to the given campaign. A one-time campaign selected on any line is forced
    for the basket.
    """
    if not lines:
        return BasketResolution(lines={}, applied_campaign_ids=())

    preference_map = dict(preferences or {})
    basket_total = sum((line.regular_total for line in lines), ZERO)

    allowed_by_line: dict[str, frozenset[str]] = {}
    forced_flat_ids: set[str] = set()
    for line in lines:
        preference = (preference_map.get(line.key) or "auto").strip()
        if preference == "auto":
            allowed_by_line[line.key] = frozenset(
                campaign.campaign_id for campaign in campaigns
            )
        elif preference in ("", "none"):
            allowed_by_line[line.key] = frozenset()
        else:
            allowed_by_line[line.key] = frozenset({preference})
            campaign = next(
                (item for item in campaigns if item.campaign_id == preference),
                None,
            )
            if campaign is not None and campaign.contract.one_time_links:
                forced_flat_ids.add(preference)

    active_campaigns = [
        campaign
        for campaign in campaigns
        if _campaign_reaches_basket(
            campaign,
            lines,
            basket_total,
            allowed_by_line,
            payment,
        )
    ]

    base_alternatives = {
        line.key: _best_alternative(
            line,
            active_campaigns,
            allowed_by_line[line.key],
        )
        for line in lines
    }

    flat_applications: list[_FlatApplication] = []
    for campaign in active_campaigns:
        application = _best_flat_application(
            campaign,
            lines,
            base_alternatives,
            allowed_by_line,
        )
        if application is not None:
            flat_applications.append(application)

    selected_flats = _select_flat_combination(
        flat_applications,
        forced_flat_ids,
        lines,
        base_alternatives,
    )
    flat_by_line: dict[str, tuple[_FlatApplication, Decimal]] = {}
    for application in selected_flats:
        for line_key, allocation in application.allocations.items():
            flat_by_line[line_key] = (application, allocation)

    resolved: dict[str, LineBenefit] = {}
    warnings: list[str] = []
    applied: list[str] = []
    for line in lines:
        flat = flat_by_line.get(line.key)
        if flat is not None:
            application, allocation = flat
            resolved[line.key] = _flat_line_benefit(
                line, application, allocation
            )
            applied.append(application.campaign.campaign_id)
            if application.warning:
                warnings.append(application.warning)
            continue
        resolved[line.key] = base_alternatives[line.key].benefit

    for campaign_id in forced_flat_ids:
        if campaign_id not in {
            item.campaign.campaign_id for item in selected_flats
        }:
            campaign = next(
                (item for item in campaigns if item.campaign_id == campaign_id),
                None,
            )
            if campaign is not None:
                warnings.append(
                    f"{campaign.name}: sepet kampanyası bu sepet için uygulanamadı."
                )

    unique_applied = tuple(dict.fromkeys(applied))
    return BasketResolution(
        lines=resolved,
        applied_campaign_ids=unique_applied,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _campaign_reaches_basket(
    campaign: BasketCampaign,
    lines: Sequence[BasketLine],
    basket_total: Decimal,
    allowed_by_line: Mapping[str, frozenset[str]],
    payment: PaymentContext | None = None,
) -> bool:
    contract = campaign.contract
    if (
        contract.min_basket_total is not None
        and basket_total < contract.min_basket_total
    ):
        return False
    if payment is not None and not _payment_matches(contract, payment):
        return False
    if not _has_allowed_line(campaign, allowed_by_line):
        return False
    qualifying = contract.qualifying_links
    if qualifying and not _qualifying_satisfied(
        campaign.campaign_id, qualifying, lines, allowed_by_line
    ):
        return False
    if contract.explicit_benefit_links:
        return bool(
            _matching_lines(
                campaign.campaign_id,
                contract.explicit_benefit_links,
                lines,
                allowed_by_line,
            )
        )
    if contract.legacy_benefit_links:
        return bool(
            _matching_lines(
                campaign.campaign_id,
                contract.legacy_benefit_links,
                lines,
                allowed_by_line,
            )
        )
    return False


def _payment_matches(
    contract: CampaignContract, payment: PaymentContext
) -> bool:
    if not contract.payment_conditions:
        return True
    if payment.payment_type != "card":
        return False
    return any(
        condition.matches(payment) for condition in contract.payment_conditions
    )


def _qualifying_satisfied(
    campaign_id: str,
    qualifying: Sequence[CampaignProductLink],
    lines: Sequence[BasketLine],
    allowed_by_line: Mapping[str, frozenset[str]],
) -> bool:
    for link in qualifying:
        matching = _matching_lines(
            campaign_id, (link,), lines, allowed_by_line
        )
        if not matching:
            continue
        if link.quantity_required is not None:
            total = sum(line.quantity for line in matching)
            if total < link.quantity_required:
                continue
        return True
    return False


def _has_allowed_line(
    campaign: BasketCampaign,
    allowed_by_line: Mapping[str, frozenset[str]],
) -> bool:
    return any(
        campaign.campaign_id in allowed for allowed in allowed_by_line.values()
    )


def _matching_lines(
    campaign_id: str,
    links: Sequence[CampaignProductLink],
    lines: Sequence[BasketLine],
    allowed_by_line: Mapping[str, frozenset[str]],
) -> list[BasketLine]:
    matches: list[BasketLine] = []
    for line in lines:
        if campaign_id not in allowed_by_line.get(line.key, frozenset()):
            continue
        for link in links:
            if link.product_id is not None and link.product_id == line.product_id:
                matches.append(line)
                break
            if link.category_id is not None and link.category_id == line.category_id:
                matches.append(line)
                break
    return matches


def _best_alternative(
    line: BasketLine,
    campaigns: Sequence[BasketCampaign],
    allowed_campaign_ids: frozenset[str],
) -> _Alternative:
    candidates: list[LineBenefit] = []
    oliz = _oliz_benefit(line)
    if oliz is not None:
        candidates.append(oliz)
    for campaign in campaigns:
        if campaign.campaign_id not in allowed_campaign_ids:
            continue
        benefit = _per_line_benefit(campaign, line)
        if benefit is not None:
            candidates.append(benefit)
    if not candidates:
        regular = _regular_benefit(line)
        return _Alternative(benefit=regular, unit_discount=ZERO)
    best = max(
        candidates,
        key=lambda item: (
            item.unit_discount,
            item.source == "campaign",
        ),
    )
    return _Alternative(benefit=best, unit_discount=best.unit_discount)


def _regular_benefit(line: BasketLine) -> LineBenefit:
    return LineBenefit(
        key=line.key,
        source="none",
        campaign_id=None,
        campaign_name=None,
        campaign_version_id=None,
        campaign_version_no=None,
        base_price=line.regular_price,
        final_price=line.regular_price,
        unit_discount=ZERO,
        unit_share=ZERO,
    )


def _oliz_benefit(line: BasketLine) -> LineBenefit | None:
    website = line.website_price
    if website is None or website <= ZERO:
        return None
    regular = line.regular_price
    if regular is not None and website >= regular:
        return None
    price = quantize_money(website)
    base = quantize_money(regular) if regular is not None else price
    discount = max(quantize_money(base - price), ZERO)
    return LineBenefit(
        key=line.key,
        source="oliz",
        campaign_id=None,
        campaign_name="Oliz",
        campaign_version_id=None,
        campaign_version_no=None,
        base_price=price,
        final_price=price,
        unit_discount=discount,
        unit_share=discount,
    )


def _per_line_benefit(
    campaign: BasketCampaign, line: BasketLine
) -> LineBenefit | None:
    contract = campaign.contract
    links = contract.explicit_benefit_links
    if links:
        links = tuple(
            link for link in links if link.applies_per_unit is not False
        )
    else:
        links = contract.legacy_benefit_links
    matches = [link for link in links if _link_matches_line(link, line)]
    if not matches:
        return None
    best: LineBenefit | None = None
    for link in matches:
        base_type = link.base_price_type or contract.base_price_type
        base_price, base_warning = _resolve_base(line, base_type)
        if base_price is None:
            continue
        quote = link_discount_price(contract, link, base_price)
        if quote.final_price is None:
            continue
        discount = quote.discount_amount or ZERO
        benefit = LineBenefit(
            key=line.key,
            source="campaign",
            campaign_id=campaign.campaign_id,
            campaign_name=campaign.name,
            campaign_version_id=campaign.version_id,
            campaign_version_no=campaign.version_no,
            base_price=quote.base_price,
            final_price=quote.final_price,
            unit_discount=discount,
            unit_share=discount,
            campaign_base_price=quote.base_price,
            campaign_price=quote.final_price,
            discount_type=(link.discount_type or contract.discount_type).value,
            discount_value=(
                link.discount_value
                if link.discount_type is not None
                else contract.discount_value
            ),
            base_price_type=base_type.value,
            applies_per_unit=link.applies_per_unit,
            warning=_join_warnings(base_warning, quote.warning),
        )
        if best is None or benefit.unit_discount > best.unit_discount:
            best = benefit
    return best


def _best_flat_application(
    campaign: BasketCampaign,
    lines: Sequence[BasketLine],
    alternatives: Mapping[str, _Alternative],
    allowed_by_line: Mapping[str, frozenset[str]],
) -> _FlatApplication | None:
    contract = campaign.contract
    one_time_links = contract.one_time_links
    if not one_time_links:
        return None

    eligible_lines = [
        line
        for line in lines
        if campaign.campaign_id in allowed_by_line.get(line.key, frozenset())
    ]
    qualifying = contract.qualifying_links
    trigger_lines = (
        _matching_lines(
            campaign.campaign_id,
            qualifying,
            eligible_lines,
            allowed_by_line,
        )
        if qualifying
        else []
    )
    if qualifying and not trigger_lines:
        return None

    applications: list[_FlatApplication] = []
    for link in one_time_links:
        target_lines = [
            line for line in eligible_lines if _link_matches_line(link, line)
        ]
        if not target_lines:
            continue
        value, value_warning = _flat_value(link, contract, target_lines)
        if value <= ZERO:
            continue
        triggers: list[BasketLine | None] = (
            list(trigger_lines) if trigger_lines else [None]
        )
        for trigger in triggers:
            application = _try_flat_application(
                campaign,
                link,
                lines,
                target_lines,
                trigger,
                value,
                alternatives,
                value_warning,
            )
            if application is not None:
                applications.append(application)
    if not applications:
        return None
    return max(applications, key=lambda item: (item.score, item.total))


def _try_flat_application(
    campaign: BasketCampaign,
    link: CampaignProductLink,
    lines: Sequence[BasketLine],
    target_lines: list[BasketLine],
    trigger: BasketLine | None,
    value: Decimal,
    alternatives: Mapping[str, _Alternative],
    warning: str | None,
) -> _FlatApplication | None:
    participants: list[BasketLine] = []
    seen: set[str] = set()
    if trigger is not None:
        participants.append(trigger)
        seen.add(trigger.key)
    for line in target_lines:
        if line.key not in seen:
            participants.append(line)
            seen.add(line.key)

    current_targets = [line for line in target_lines if line.key in seen]
    while True:
        if not current_targets:
            return None
        allocations = _allocate_flat(
            value,
            [line for line in participants if line.key in seen],
        )
        declined: list[str] = []
        for line in current_targets:
            share = allocations.get(line.key, ZERO)
            unit_share = (
                quantize_money(share / line.quantity) if line.quantity else ZERO
            )
            alternative = alternatives.get(line.key)
            if (
                alternative is not None
                and unit_share < alternative.unit_discount
            ):
                declined.append(line.key)
        if not declined:
            break
        for key in declined:
            seen.discard(key)
        current_targets = [
            line for line in current_targets if line.key in seen
        ]
        if trigger is not None and trigger.key not in seen:
            return None

    if trigger is not None:
        trigger_share = allocations.get(trigger.key, ZERO)
        trigger_unit = (
            quantize_money(trigger_share / trigger.quantity)
            if trigger.quantity
            else ZERO
        )
        alternative = alternatives.get(trigger.key)
        if (
            alternative is not None
            and trigger_unit < alternative.unit_discount
        ):
            return None

    score = ZERO
    for line in lines:
        if line.key in seen:
            score += allocations.get(line.key, ZERO)
        else:
            alternative = alternatives.get(line.key)
            if alternative is not None:
                score += quantize_money(
                    alternative.unit_discount * line.quantity
                )
    total = quantize_money(sum(allocations.values(), ZERO))
    return _FlatApplication(
        campaign=campaign,
        link=link,
        total=total,
        allocations={
            key: quantize_money(share) for key, share in allocations.items()
        },
        trigger_key=trigger.key if trigger is not None else None,
        target_keys=tuple(line.key for line in current_targets),
        score=quantize_money(score),
        warning=warning,
    )


def _allocate_flat(
    total: Decimal, participants: Sequence[BasketLine]
) -> dict[str, Decimal]:
    weights = {
        line.key: quantize_money((line.regular_price or ZERO) * line.quantity)
        for line in participants
    }
    positive = {key: max(ZERO, weight) for key, weight in weights.items()}
    denominator = sum(positive.values(), ZERO)
    if denominator <= ZERO:
        positive = {line.key: Decimal(1) for line in participants}
        denominator = Decimal(len(participants))
    ordered = [line.key for line in participants]
    allocations: dict[str, Decimal] = {}
    allocated = ZERO
    for key in ordered[:-1]:
        share = quantize_money(total * positive[key] / denominator)
        allocations[key] = share
        allocated += share
    allocations[ordered[-1]] = quantize_money(total - allocated)
    return allocations


def _flat_line_benefit(
    line: BasketLine,
    application: _FlatApplication,
    allocation: Decimal,
) -> LineBenefit:
    unit_share = (
        quantize_money(allocation / line.quantity) if line.quantity else ZERO
    )
    base = _base_for_link(line, application.link, application.campaign.contract)
    final = (
        quantize_money(base - unit_share) if base is not None else None
    )
    return LineBenefit(
        key=line.key,
        source="campaign",
        campaign_id=application.campaign.campaign_id,
        campaign_name=application.campaign.name,
        campaign_version_id=application.campaign.version_id,
        campaign_version_no=application.campaign.version_no,
        base_price=base,
        final_price=final,
        unit_discount=unit_share,
        unit_share=unit_share,
        campaign_base_price=base,
        campaign_price=final,
        discount_type=(
            application.link.discount_type.value
            if application.link.discount_type is not None
            else application.campaign.contract.discount_type.value
        ),
        discount_value=(
            application.link.discount_value
            if application.link.discount_value is not None
            else application.campaign.contract.discount_value
        ),
        base_price_type=(
            application.link.base_price_type
            or application.campaign.contract.base_price_type
        ).value,
        applies_per_unit=False,
        is_flat_allocation=True,
        warning=application.warning,
    )


def _flat_value(
    link: CampaignProductLink,
    contract: CampaignContract,
    target_lines: Sequence[BasketLine],
) -> tuple[Decimal, str | None]:
    discount_type = link.discount_type or contract.discount_type
    value = (
        link.discount_value
        if link.discount_type is not None
        else contract.discount_value
    )
    base_total = quantize_money(
        sum(
            (_base_for_link(line, link, contract) or ZERO) * line.quantity
            for line in target_lines
        )
    )
    if discount_type is DiscountType.FIXED_AMOUNT:
        if value is None:
            return ZERO, "Sabit indirim değeri tanımlı değil."
        if value > base_total:
            return base_total, "Sabit indirim taban fiyatı aşıyor."
        return quantize_money(value), None
    if discount_type is DiscountType.PERCENT:
        if value is None:
            return ZERO, "Yüzde indirim değeri tanımlı değil."
        return quantize_money(base_total * value / HUNDRED), None
    if discount_type is DiscountType.SPECIAL_PRICE:
        if value is None:
            return ZERO, "Özel fiyat tanımlı değil."
        return max(quantize_money(base_total - value), ZERO), None
    return ZERO, None


def _select_flat_combination(
    applications: Sequence[_FlatApplication],
    forced_ids: set[str],
    lines: Sequence[BasketLine],
    alternatives: Mapping[str, _Alternative],
) -> list[_FlatApplication]:
    if not applications:
        return []
    unique: dict[str, _FlatApplication] = {}
    for application in applications:
        current = unique.get(application.campaign.campaign_id)
        if current is None or application.score > current.score:
            unique[application.campaign.campaign_id] = application
    candidates = list(unique.values())
    candidates.sort(key=lambda item: item.score, reverse=True)

    def valid(selected: Sequence[_FlatApplication]) -> bool:
        if forced_ids and not forced_ids.issubset(
            {item.campaign.campaign_id for item in selected}
        ):
            return False
        used: set[str] = set()
        for application in selected:
            if used & application.participant_keys:
                return False
            used |= application.participant_keys
        return True

    def score(selected: Sequence[_FlatApplication]) -> Decimal:
        used: dict[str, Decimal] = {}
        for application in selected:
            used.update(application.allocations)
        total = ZERO
        for line in lines:
            if line.key in used:
                total += used[line.key]
            else:
                alternative = alternatives.get(line.key)
                if alternative is not None:
                    total += quantize_money(
                        alternative.unit_discount * line.quantity
                    )
        return quantize_money(total)

    best: list[_FlatApplication] = []
    best_score = score([])
    forced_best: list[_FlatApplication] = []
    forced_best_score: Decimal | None = None
    limit = min(len(candidates), 8)
    for size in range(1, limit + 1):
        for combo in combinations(candidates[:limit], size):
            selected = list(combo)
            if not valid(selected):
                continue
            combo_score = score(selected)
            if combo_score > best_score:
                best = selected
                best_score = combo_score
            if (
                forced_ids
                and forced_ids.issubset(
                    {item.campaign.campaign_id for item in selected}
                )
                and (
                    forced_best_score is None
                    or combo_score > forced_best_score
                )
            ):
                forced_best = selected
                forced_best_score = combo_score
    if forced_ids:
        return forced_best
    return best


def _link_matches_line(link: CampaignProductLink, line: BasketLine) -> bool:
    if link.product_id is not None:
        return link.product_id == line.product_id
    if link.category_id is not None:
        return link.category_id == line.category_id
    return False


def _resolve_base(
    line: BasketLine, base_type: BasePriceType
) -> tuple[Decimal | None, str | None]:
    if base_type is BasePriceType.REGULAR:
        return line.regular_price, None
    if base_type is BasePriceType.MANUAL:
        if line.manual_price is not None:
            return line.manual_price, None
        return (
            line.regular_price,
            "Elle girilen fiyat tanımlı değil; normal fiyat kullanıldı.",
        )
    if line.website_price is not None:
        return line.website_price, None
    return (
        line.regular_price,
        "Oliz fiyatı tanımlı değil; normal fiyat kullanıldı.",
    )


def _base_for_link(
    line: BasketLine,
    link: CampaignProductLink,
    contract: CampaignContract,
) -> Decimal | None:
    base_type = link.base_price_type or contract.base_price_type
    base, _warning = _resolve_base(line, base_type)
    return base


def _join_warnings(*warnings: str | None) -> str | None:
    present = [warning for warning in warnings if warning]
    return "; ".join(present) if present else None
