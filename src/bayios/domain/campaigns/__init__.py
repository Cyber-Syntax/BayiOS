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
    """One product relation inside an immutable campaign version."""

    product_id: str | None
    product_name: str
    relation_type: ProductRelationType = ProductRelationType.RELATED
    quantity_required: int | None = None

    def __post_init__(self) -> None:
        if not self.product_name.strip():
            raise ValueError("Ürün adı anlık görüntüsü boş olamaz.")
        if self.quantity_required is not None and self.quantity_required <= 0:
            raise ValueError("Gerekli adet sıfırdan büyük olmalıdır.")


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
        _validate_product_links(self.products)

    def signature(self) -> tuple[object, ...]:
        """Stable representation used to decide whether an edit is effective."""
        products = tuple(
            sorted(
                (
                    link.relation_type.value,
                    link.product_id or "",
                    link.product_name,
                    link.quantity_required or 0,
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
