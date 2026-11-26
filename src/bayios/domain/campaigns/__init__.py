from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from bayios.domain.dealer_pricing import (
    DEFAULT_DEALER_DISCOUNT_PERCENT,
    HUNDRED,
    ZERO,
    quantize_money,
    validate_dealer_percent,
)


class CampaignType(StrEnum):
    GENERAL = "general"
    PRODUCT_DISCOUNT = "product_discount"
    BUNDLE = "bundle"
    GIFT = "gift"
    COUPON = "coupon"
    SPECIAL = "special"


class DiscountType(StrEnum):
    PERCENT = "percent"
    FIXED_AMOUNT = "fixed_amount"
    SPECIAL_PRICE = "special_price"
    GIFT = "gift"
    INFO_ONLY = "info_only"


class BasePriceType(StrEnum):
    REGULAR = "regular"
    WEBSITE_DISCOUNTED = "website_discounted"
    MANUAL = "manual"


class ProductRelationType(StrEnum):
    QUALIFYING = "qualifying"
    BENEFIT = "benefit"
    GIFT = "gift"
    RELATED = "related"


class TargetType(StrEnum):
    PRODUCT = "product"
    CATEGORY = "category"


class CampaignState(StrEnum):
    ACTIVE = "active"
    SCHEDULED = "scheduled"
    EXPIRED = "expired"
    ARCHIVED = "archived"


CAMPAIGN_TYPE_LABELS: dict[CampaignType, str] = {
    CampaignType.GENERAL: "Genel",
    CampaignType.PRODUCT_DISCOUNT: "Ürün indirimi",
    CampaignType.BUNDLE: "Birlikte alım",
    CampaignType.GIFT: "Hediye",
    CampaignType.COUPON: "Kupon",
    CampaignType.SPECIAL: "Özel",
}

DISCOUNT_TYPE_LABELS: dict[DiscountType, str] = {
    DiscountType.PERCENT: "Yüzde",
    DiscountType.FIXED_AMOUNT: "Sabit tutar",
    DiscountType.SPECIAL_PRICE: "Özel fiyat",
    DiscountType.GIFT: "Hediye",
    DiscountType.INFO_ONLY: "Sadece bilgi",
}

BASE_PRICE_TYPE_LABELS: dict[BasePriceType, str] = {
    BasePriceType.REGULAR: "Normal fiyat",
    BasePriceType.WEBSITE_DISCOUNTED: "Oliz / web indirimli",
    BasePriceType.MANUAL: "Elle girilen",
}

PRODUCT_RELATION_TYPE_LABELS: dict[ProductRelationType, str] = {
    ProductRelationType.QUALIFYING: "Şart ürünü",
    ProductRelationType.BENEFIT: "Fayda ürünü",
    ProductRelationType.GIFT: "Hediye ürünü",
    ProductRelationType.RELATED: "İlgili ürün",
}

CAMPAIGN_STATE_LABELS: dict[CampaignState, str] = {
    CampaignState.ACTIVE: "Aktif",
    CampaignState.SCHEDULED: "Yaklaşan",
    CampaignState.EXPIRED: "Süresi geçti",
    CampaignState.ARCHIVED: "Arşivde",
}


@dataclass(frozen=True)
class CampaignProductLink:
    """One product or category relation inside an immutable campaign version.

    A challenge product (relation_type qualifying) triggers the campaign. A
    benefit relation (benefit/related) is where the campaign discount is
    applied. Category relations use category_id and keep the category name in
    product_name so the snapshot survives category deletion.

    discount_type/discount_value/base_price_type/applies_per_unit are optional
    per-relation benefit rules. When they are empty the campaign own discount
    fields are used for backward compatibility (legacy campaigns such as
    Düğün). applies_per_unit=False means the rule is a one-time basket discount
    and its amount is allocated across the participating lines.
    """

    product_id: str | None
    product_name: str
    relation_type: ProductRelationType = ProductRelationType.RELATED
    quantity_required: int | None = None
    category_id: str | None = None
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = None
    base_price_type: BasePriceType | None = None
    applies_per_unit: bool | None = None
    gift_price: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.product_name.strip():
            raise ValueError("Ürün adı anlık görüntüsü boş olamaz.")
        if self.quantity_required is not None and self.quantity_required <= 0:
            raise ValueError("Gerekli adet sıfırdan büyük olmalıdır.")
        if self.product_id is not None and self.category_id is not None:
            raise ValueError(
                "Kampanya ilişkisi ürün veya kategori olabilir; ikisi birlikte olamaz."
            )
        if self.discount_type is not None:
            _validate_discount(self.discount_type, self.discount_value)
        elif self.discount_value is not None:
            raise ValueError("İndirim değeri için indirim türü girilmelidir.")
        if self.gift_price is not None and self.gift_price < ZERO:
            raise ValueError("Hediye fiyatı negatif olamaz.")

    @property
    def target_type(self) -> TargetType:
        return (
            TargetType.CATEGORY
            if self.category_id is not None
            else TargetType.PRODUCT
        )

    @property
    def target_id(self) -> str | None:
        return self.category_id if self.category_id is not None else self.product_id


@dataclass(frozen=True)
class CampaignPaymentCondition:
    """One payment eligibility rule for a campaign.

    Empty fields mean "any". A campaign with no conditions is valid for every
    payment. Cash payments only use campaigns without conditions; card
    payments match channel, bank, card type and installment count.
    """

    channel: str | None = None
    bank_ids: tuple[str, ...] = ()
    card_type: str | None = None
    card_network: str | None = None
    installment_count: int | None = None

    def __post_init__(self) -> None:
        if self.channel is not None and self.channel not in (
            "pos",
            "odero",
            "chippin",
        ):
            raise ValueError("Geçersiz ödeme kanalı.")
        if self.card_type is not None and self.card_type not in (
            "consumer",
            "business",
        ):
            raise ValueError("Geçersiz kart tipi.")
        if self.installment_count is not None and self.installment_count <= 0:
            raise ValueError("Taksit sayısı sıfırdan büyük olmalıdır.")
        if len(set(self.bank_ids)) != len(self.bank_ids):
            raise ValueError("Ödeme koşulunda aynı banka tekrar edemez.")
        if self.card_network is not None and not self.card_network.strip():
            raise ValueError("Kart ağı boş olamaz.")

    def matches(self, payment: PaymentContext) -> bool:
        if payment.payment_type != "card":
            return False
        if self.channel is not None and self.channel != payment.channel:
            return False
        if self.bank_ids and payment.bank_id not in self.bank_ids:
            return False
        if self.card_type is not None and self.card_type != payment.card_type:
            return False
        if (
            self.card_network is not None
            and self.card_network.strip().casefold()
            != (payment.card_network or "").strip().casefold()
        ):
            return False
        return not (
            self.installment_count is not None
            and self.installment_count != payment.installment_count
        )


@dataclass(frozen=True)
class PaymentContext:
    """The payment selected on an offer, used for campaign eligibility."""

    payment_type: str
    channel: str | None = None
    bank_id: str | None = None
    card_type: str | None = None
    card_network: str | None = None
    installment_count: int | None = None


@dataclass(frozen=True)
class CampaignContract:
    """The business fields that make up one immutable campaign version."""

    name: str
    campaign_type: CampaignType
    starts_at: datetime
    ends_at: datetime
    base_price_type: BasePriceType = BasePriceType.REGULAR
    description: str | None = None
    discount_type: DiscountType = DiscountType.INFO_ONLY
    discount_value: Decimal | None = None
    gift_description: str | None = None
    gift_optional: bool = False
    gift_yes_base_price_type: BasePriceType | None = None
    gift_no_base_price_type: BasePriceType | None = None
    employee_note: str | None = None
    conditions: tuple[str, ...] = ()
    source_category: str | None = None
    source_product_count: int | None = None
    combines_with_others: bool = True
    exclusion_group: str | None = None
    min_basket_total: Decimal | None = None
    payment_conditions: tuple[CampaignPaymentCondition, ...] = ()
    products: tuple[CampaignProductLink, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Kampanya adı boş olamaz.")
        _validate_date_range(self.starts_at, self.ends_at)
        _validate_discount(self.discount_type, self.discount_value)
        if self.campaign_type is CampaignType.GIFT and not _has_text(self.gift_description):
            raise ValueError("Hediye kampanyalarında hediye açıklaması zorunludur.")
        if self.discount_type is DiscountType.GIFT and not _has_text(self.gift_description):
            raise ValueError("Hediye indirimlerinde hediye açıklaması zorunludur.")
        if self.gift_optional and not _has_text(self.gift_description):
            raise ValueError("İsteğe bağlı hediyelerde hediye açıklaması zorunludur.")
        if self.source_product_count is not None and self.source_product_count < 0:
            raise ValueError("Kaynak ürün sayısı negatif olamaz.")
        if self.min_basket_total is not None and self.min_basket_total < ZERO:
            raise ValueError("Sepet alt sınırı negatif olamaz.")
        if self.exclusion_group is not None and not self.exclusion_group.strip():
            raise ValueError("Dışlama grubu boş olamaz.")
        if self.payment_conditions:
            for condition in self.payment_conditions:
                if not isinstance(condition, CampaignPaymentCondition):
                    raise TypeError("Ödeme koşulu geçersiz.")
        _validate_product_links(self.products)

    @property
    def qualifying_links(self) -> tuple[CampaignProductLink, ...]:
        return tuple(
            link
            for link in self.products
            if link.relation_type is ProductRelationType.QUALIFYING
        )

    @property
    def explicit_benefit_links(self) -> tuple[CampaignProductLink, ...]:
        return tuple(
            link
            for link in self.products
            if link.relation_type
            in (ProductRelationType.BENEFIT, ProductRelationType.RELATED)
            and link.discount_type is not None
        )

    @property
    def legacy_benefit_links(self) -> tuple[CampaignProductLink, ...]:
        if self.explicit_benefit_links:
            return ()
        return tuple(
            link
            for link in self.products
            if link.relation_type
            in (ProductRelationType.BENEFIT, ProductRelationType.RELATED)
        )

    @property
    def gift_links(self) -> tuple[CampaignProductLink, ...]:
        return tuple(
            link
            for link in self.products
            if link.relation_type is ProductRelationType.GIFT
            and link.product_id is not None
        )

    @property
    def one_time_links(self) -> tuple[CampaignProductLink, ...]:
        return tuple(
            link
            for link in self.explicit_benefit_links
            if link.applies_per_unit is False
        )

    def signature(self) -> tuple[object, ...]:
        """Stable representation used to decide whether an edit is effective."""
        products = tuple(
            sorted(
                (
                    link.relation_type.value,
                    link.product_id or "",
                    link.category_id or "",
                    link.product_name,
                    link.quantity_required or 0,
                    link.discount_type.value if link.discount_type else "",
                    link.discount_value,
                    link.base_price_type.value if link.base_price_type else "",
                    link.applies_per_unit if link.applies_per_unit is not None else "",
                    link.gift_price,
                )
                for link in self.products
            )
        )
        return (
            self.name,
            self.description or "",
            self.campaign_type.value,
            self.starts_at,
            self.ends_at,
            self.base_price_type.value,
            self.discount_type.value,
            self.discount_value,
            self.gift_description or "",
            self.gift_optional,
            self.gift_yes_base_price_type.value
            if self.gift_yes_base_price_type is not None
            else None,
            self.gift_no_base_price_type.value
            if self.gift_no_base_price_type is not None
            else None,
            self.employee_note or "",
            tuple(condition.strip() for condition in self.conditions if condition.strip()),
            self.source_category or "",
            self.source_product_count or 0,
            self.combines_with_others,
            self.exclusion_group or "",
            self.min_basket_total,
            tuple(
                (
                    condition.channel or "",
                    condition.bank_ids,
                    condition.card_type or "",
                    condition.card_network or "",
                    condition.installment_count or 0,
                )
                for condition in self.payment_conditions
            ),
            products,
        )


@dataclass(frozen=True)
class CampaignVersion:
    version_no: int
    contract: CampaignContract

    def __post_init__(self) -> None:
        if self.version_no <= 0:
            raise ValueError("Kampanya sürüm numarası sıfırdan büyük olmalıdır.")


def next_version_no(current_version_no: int | None) -> int:
    """Return the next immutable version number for a campaign."""
    if current_version_no is None:
        return 1
    if current_version_no <= 0:
        raise ValueError("Mevcut kampanya sürüm numarası sıfırdan büyük olmalıdır.")
    return current_version_no + 1


def is_same_contract(left: CampaignContract, right: CampaignContract) -> bool:
    """True when an edit would not change any business field or relation."""
    return left.signature() == right.signature()


def classify_campaign(
    *,
    starts_at: datetime,
    ends_at: datetime,
    archived: bool,
    as_of: datetime,
) -> CampaignState:
    """Classify a campaign for active/history filters at a given moment."""
    _validate_date_range(starts_at, ends_at)
    _ensure_comparable(as_of, starts_at)
    if archived:
        return CampaignState.ARCHIVED
    if as_of < starts_at:
        return CampaignState.SCHEDULED
    if as_of > ends_at:
        return CampaignState.EXPIRED
    return CampaignState.ACTIVE


def is_active_state(state: CampaignState) -> bool:
    return state is CampaignState.ACTIVE


def is_history_state(state: CampaignState) -> bool:
    return state in (CampaignState.EXPIRED, CampaignState.ARCHIVED)


def is_visible_in_active_list(state: CampaignState) -> bool:
    """Scheduled campaigns stay visible as upcoming guide entries."""
    return state in (CampaignState.ACTIVE, CampaignState.SCHEDULED)


@dataclass(frozen=True)
class CampaignPriceInput:
    """Product prices used by the campaign guide scenario."""

    regular_price: Decimal | None = None
    website_discounted_price: Decimal | None = None
    cash_floor_price: Decimal | None = None
    card_floor_price: Decimal | None = None
    manual_base_price: Decimal | None = None

    def __post_init__(self) -> None:
        for value in (
            self.regular_price,
            self.website_discounted_price,
            self.cash_floor_price,
            self.card_floor_price,
            self.manual_base_price,
        ):
            if value is not None and value < ZERO:
                raise ValueError("Kampanya fiyat girdileri negatif olamaz.")


@dataclass(frozen=True)
class CampaignScenario:
    """One gift-present or gift-absent price example for the guide.

    Product-specific cash/card floors are carried alongside the calculated
    price and are never folded into the general dealer discount.
    """

    gift_present: bool
    base_price_type: BasePriceType
    base_price: Decimal | None
    dealer_percent: Decimal
    discount_amount: Decimal | None
    final_price: Decimal | None
    cash_floor_price: Decimal | None
    card_floor_price: Decimal | None
    gift_description: str | None = None
    warning: str | None = None
    is_informational: bool = False


@dataclass(frozen=True)
class CampaignOfferPrice:
    """Campaign price before the dealer discount.

    The campaign guide applies the dealer discount to show a scenario; the
    offer needs the campaign's own discount first so the dealer discount can
    be applied exactly once afterwards.
    """

    base_price: Decimal | None
    discount_amount: Decimal | None
    final_price: Decimal | None
    warning: str | None = None


def campaign_discount_price(
    contract: CampaignContract, base_price: Decimal | None
) -> CampaignOfferPrice:
    """Apply the campaign's own discount to a base price, without dealer discount."""
    return _discount_price(
        contract.discount_type,
        contract.discount_value,
        base_price,
        campaign_type=contract.campaign_type,
    )


def link_discount_price(
    contract: CampaignContract,
    link: CampaignProductLink,
    base_price: Decimal | None,
) -> CampaignOfferPrice:
    """Apply one relation's benefit rule, falling back to the campaign fields."""
    if link.discount_type is None:
        return campaign_discount_price(contract, base_price)
    return _discount_price(
        link.discount_type,
        link.discount_value,
        base_price,
        campaign_type=contract.campaign_type,
    )


def _discount_price(
    discount_type: DiscountType,
    discount_value: Decimal | None,
    base_price: Decimal | None,
    *,
    campaign_type: CampaignType,
) -> CampaignOfferPrice:
    if base_price is None:
        return CampaignOfferPrice(
            base_price=None,
            discount_amount=None,
            final_price=None,
            warning="Taban fiyat tanımlı değil.",
        )

    base = quantize_money(base_price)
    warning: str | None = None
    if (
        discount_type is DiscountType.INFO_ONLY
        or campaign_type is CampaignType.COUPON
        or discount_type is DiscountType.GIFT
    ):
        # Information-only, coupon and gift campaigns do not change the price.
        return CampaignOfferPrice(
            base_price=base,
            discount_amount=ZERO,
            final_price=base,
        )
    if discount_type is DiscountType.PERCENT:
        value = discount_value or ZERO
        discount = quantize_money(base * value / HUNDRED)
        final = quantize_money(base - discount)
    elif discount_type is DiscountType.FIXED_AMOUNT:
        value = discount_value
        if value is None:
            raise ValueError("Sabit tutar indirimi için değer girilmelidir.")
        if value > base:
            discount = base
            final = ZERO
            warning = "Sabit indirim taban fiyatı aşıyor."
        else:
            discount = quantize_money(value)
            final = quantize_money(base - discount)
    elif discount_type is DiscountType.SPECIAL_PRICE:
        value = discount_value
        if value is None:
            raise ValueError("Özel fiyat için değer girilmelidir.")
        final = quantize_money(value)
        discount = quantize_money(base - final)
        if final > base:
            warning = "Özel fiyat taban fiyatın üzerinde."
    else:
        # GIFT / INFO_ONLY: the gift or note is not a price discount.
        discount = ZERO
        final = base

    return CampaignOfferPrice(
        base_price=base,
        discount_amount=discount,
        final_price=final,
        warning=warning,
    )


def campaign_scenarios(
    contract: CampaignContract,
    prices: CampaignPriceInput,
    dealer_percent: Decimal = DEFAULT_DEALER_DISCOUNT_PERCENT,
) -> tuple[CampaignScenario, ...]:
    """Build guide scenarios for a campaign version.

    ``dealer_percent`` is the editable guide rate for percent/gift campaigns;
    fixed-amount and special-price campaigns use their stored discount value.
    """
    percent = validate_dealer_percent(dealer_percent)

    if (
        contract.discount_type is DiscountType.INFO_ONLY
        or contract.campaign_type is CampaignType.COUPON
    ):
        return (
            _build_scenario(
                contract,
                prices,
                percent,
                gift_present=bool(contract.gift_description),
                base_type=contract.base_price_type,
                informational=True,
            ),
        )

    if contract.gift_description:
        scenarios = [
            _build_scenario(
                contract,
                prices,
                percent,
                gift_present=True,
                base_type=contract.gift_yes_base_price_type or BasePriceType.REGULAR,
            )
        ]
        if contract.gift_optional:
            scenarios.append(
                _build_scenario(
                    contract,
                    prices,
                    percent,
                    gift_present=False,
                    base_type=contract.gift_no_base_price_type
                    or BasePriceType.WEBSITE_DISCOUNTED,
                )
            )
        return tuple(scenarios)

    return (
        _build_scenario(
            contract,
            prices,
            percent,
            gift_present=False,
            base_type=contract.base_price_type,
        ),
    )


def _build_scenario(
    contract: CampaignContract,
    prices: CampaignPriceInput,
    dealer_percent: Decimal,
    *,
    gift_present: bool,
    base_type: BasePriceType,
    informational: bool = False,
) -> CampaignScenario:
    base_price, warning = _resolve_base_price(base_type, prices)
    floors = {
        "cash_floor_price": _maybe_quantize(prices.cash_floor_price),
        "card_floor_price": _maybe_quantize(prices.card_floor_price),
        "gift_description": contract.gift_description,
    }
    if base_price is None:
        return CampaignScenario(
            gift_present=gift_present,
            base_price_type=base_type,
            base_price=None,
            dealer_percent=dealer_percent,
            discount_amount=None,
            final_price=None,
            warning=_join_warnings(warning, "Taban fiyat tanımlı değil."),
            is_informational=informational,
            **floors,
        )

    base_price = quantize_money(base_price)
    if informational:
        return CampaignScenario(
            gift_present=gift_present,
            base_price_type=base_type,
            base_price=base_price,
            dealer_percent=dealer_percent,
            discount_amount=None,
            final_price=None,
            warning=warning,
            is_informational=True,
            **floors,
        )

    if contract.discount_type in (DiscountType.PERCENT, DiscountType.GIFT):
        discount_amount = quantize_money(base_price * dealer_percent / HUNDRED)
        final_price = quantize_money(base_price - discount_amount)
    elif contract.discount_type is DiscountType.FIXED_AMOUNT:
        value = contract.discount_value
        if value is None:
            raise ValueError("Sabit tutar indirimi için değer girilmelidir.")
        if value > base_price:
            discount_amount = base_price
            final_price = ZERO
            warning = _join_warnings(warning, "Sabit indirim taban fiyatı aşıyor.")
        else:
            discount_amount = quantize_money(value)
            final_price = quantize_money(base_price - discount_amount)
    elif contract.discount_type is DiscountType.SPECIAL_PRICE:
        value = contract.discount_value
        if value is None:
            raise ValueError("Özel fiyat için değer girilmelidir.")
        final_price = quantize_money(value)
        discount_amount = quantize_money(base_price - final_price)
        if final_price > base_price:
            warning = _join_warnings(warning, "Özel fiyat taban fiyatın üzerinde.")
    else:
        raise ValueError(f"Desteklenmeyen indirim türü: {contract.discount_type}")

    return CampaignScenario(
        gift_present=gift_present,
        base_price_type=base_type,
        base_price=base_price,
        dealer_percent=dealer_percent,
        discount_amount=discount_amount,
        final_price=final_price,
        warning=warning,
        **floors,
    )


def _resolve_base_price(
    base_type: BasePriceType,
    prices: CampaignPriceInput,
) -> tuple[Decimal | None, str | None]:
    if base_type is BasePriceType.REGULAR:
        return prices.regular_price, None
    if base_type is BasePriceType.MANUAL:
        if prices.manual_base_price is not None:
            return prices.manual_base_price, None
        return prices.regular_price, "Elle girilen fiyat tanımlı değil; normal fiyat kullanıldı."
    if prices.website_discounted_price is not None:
        return prices.website_discounted_price, None
    return prices.regular_price, "Oliz fiyatı tanımlı değil; normal fiyat kullanıldı."


def _maybe_quantize(value: Decimal | None) -> Decimal | None:
    return quantize_money(value) if value is not None else None


def _join_warnings(*warnings: str | None) -> str | None:
    present = [warning for warning in warnings if warning]
    return "; ".join(present) if present else None


def _has_text(value: str | None) -> bool:
    return bool(value and value.strip())


def _validate_date_range(starts_at: datetime, ends_at: datetime) -> None:
    _ensure_comparable(starts_at, ends_at)
    if ends_at < starts_at:
        raise ValueError("Kampanya bitiş tarihi başlangıç tarihinden önce olamaz.")


def _ensure_comparable(left: datetime, right: datetime) -> None:
    if (left.tzinfo is None) != (right.tzinfo is None):
        raise ValueError("Kampanya tarihleri aynı saat dilimi bilgisine sahip olmalıdır.")


def _validate_discount(
    discount_type: DiscountType, discount_value: Decimal | None
) -> None:
    if discount_type is DiscountType.PERCENT:
        if discount_value is None:
            raise ValueError("Yüzde indirimi için değer girilmelidir.")
        if not (ZERO <= discount_value <= HUNDRED):
            raise ValueError("Yüzde indirimi %0 ile %100 arasında olmalıdır.")
    elif discount_type in (DiscountType.FIXED_AMOUNT, DiscountType.SPECIAL_PRICE):
        if discount_value is None:
            label = (
                "Sabit tutar indirimi"
                if discount_type is DiscountType.FIXED_AMOUNT
                else "Özel fiyat"
            )
            raise ValueError(f"{label} için değer girilmelidir.")
        if discount_value < ZERO:
            raise ValueError("İndirim değeri negatif olamaz.")
    elif discount_value is not None:
        label = (
            "Hediye indirimi"
            if discount_type is DiscountType.GIFT
            else "Bilgi amaçlı indirim"
        )
        raise ValueError(f"{label} değer almaz.")


def _validate_product_links(products: tuple[CampaignProductLink, ...]) -> None:
    seen: set[tuple[str, str]] = set()
    for link in products:
        key = (link.product_id or link.product_name, link.relation_type.value)
        if key in seen:
            raise ValueError("Kampanya sürümünde aynı ürün ilişkisi tekrar edemez.")
        seen.add(key)
