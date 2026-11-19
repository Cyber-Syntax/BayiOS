from __future__ import annotations

import calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

MONEY_QUANTUM = Decimal("0.01")
ZERO = Decimal(0)
HUNDRED = Decimal(100)
ODERO_THRESHOLD = Decimal("20000.00")

POS_MAX_INSTALLMENTS = 8
ODERO_MAX_INSTALLMENTS = 5
CHIPPIN_MAX_INSTALLMENTS = 6
BUSINESS_MAX_INSTALLMENTS = 2


class PaymentChannel(StrEnum):
    POS = "pos"
    ODERO = "odero"
    CHIPPIN = "chippin"


class ProductCommissionGroup(StrEnum):
    KLIMA = "klima"
    OTHER = "other"


class CardType(StrEnum):
    CONSUMER = "consumer"
    BUSINESS = "business"


class OderoTier(StrEnum):
    UNDER_20000 = "under_20000"
    OVER_20000 = "over_20000"


class CommissionPeriodStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class ProfitTargetType(StrEnum):
    PERCENT = "percent"
    FIXED_AMOUNT = "fixed_amount"


CHANNEL_LABELS: dict[PaymentChannel, str] = {
    PaymentChannel.POS: "POS",
    PaymentChannel.ODERO: "Ödero (mail order)",
    PaymentChannel.CHIPPIN: "Chippin",
}
PRODUCT_GROUP_LABELS: dict[ProductCommissionGroup, str] = {
    ProductCommissionGroup.KLIMA: "Klima",
    ProductCommissionGroup.OTHER: "Diğer",
}
CARD_TYPE_LABELS: dict[CardType, str] = {
    CardType.CONSUMER: "Bireysel",
    CardType.BUSINESS: "Business",
}
ODERO_TIER_LABELS: dict[OderoTier, str] = {
    OderoTier.UNDER_20000: "20.000 TL altı",
    OderoTier.OVER_20000: "20.000 TL ve üzeri",
}
PERIOD_STATUS_LABELS: dict[CommissionPeriodStatus, str] = {
    CommissionPeriodStatus.DRAFT: "Taslak",
    CommissionPeriodStatus.ACTIVE: "Aktif",
    CommissionPeriodStatus.INACTIVE: "Pasif",
    CommissionPeriodStatus.ARCHIVED: "Arşivde",
}


def commission_group_for_category_name(name: str) -> ProductCommissionGroup:
    """Derive the commission group from the product category name.

    TV is not a separate commission group; it uses the standard group. Any
    per-category installment difference is period data, not a rate group.
    """
    normalized = name.strip().lower()
    if "klima" in normalized:
        return ProductCommissionGroup.KLIMA
    return ProductCommissionGroup.OTHER


def odero_tier(total: Decimal) -> OderoTier:
    if total < ZERO:
        raise ValueError("Sepet toplamı negatif olamaz.")
    return (
        OderoTier.UNDER_20000
        if total < ODERO_THRESHOLD
        else OderoTier.OVER_20000
    )


def amount_tier_for(
    channel: PaymentChannel,
    product_group: ProductCommissionGroup | None,
    total: Decimal,
) -> OderoTier | None:
    """Return the Ödero basket tier; Klima does not use a tier."""
    if channel is not PaymentChannel.ODERO:
        return None
    if product_group is ProductCommissionGroup.KLIMA:
        return None
    return odero_tier(total)


@dataclass(frozen=True)
class CommissionRate:
    channel: PaymentChannel
    bank_id: str | None
    product_group: ProductCommissionGroup | None
    installment_count: int
    commission_percent: Decimal
    amount_tier: OderoTier | None = None

    def __post_init__(self) -> None:
        if self.installment_count <= 0:
            raise ValueError("Taksit sayısı sıfırdan büyük olmalıdır.")
        if not (ZERO <= self.commission_percent <= HUNDRED):
            raise ValueError("Komisyon oranı %0 ile %100 arasında olmalıdır.")
        if self.channel in (PaymentChannel.POS, PaymentChannel.ODERO) and self.product_group is None:
            raise ValueError("POS ve Ödero komisyonunda ürün grubu zorunludur.")
        if self.channel is PaymentChannel.ODERO:
            if (
                self.product_group is ProductCommissionGroup.KLIMA
                and self.amount_tier is not None
            ):
                raise ValueError("Klima komisyonunda tutar bandı kullanılmaz.")
            if (
                self.product_group is not ProductCommissionGroup.KLIMA
                and self.amount_tier is None
            ):
                raise ValueError("Ödero komisyonunda tutar bandı zorunludur.")
        if self.channel is not PaymentChannel.ODERO and self.amount_tier is not None:
            raise ValueError("Tutar bandı yalnızca Ödero için kullanılır.")

    @property
    def rate_group(self) -> ProductCommissionGroup | None:
        return self.product_group

    @property
    def scope_key(self) -> str:
        return "|".join(
            (
                self.channel.value,
                self.bank_id or "-",
                self.product_group.value if self.product_group else "-",
                self.amount_tier.value if self.amount_tier else "-",
                str(self.installment_count),
            )
        )


@dataclass(frozen=True)
class CommissionLimit:
    max_installments: int
    channel: PaymentChannel | None = None
    bank_id: str | None = None
    product_group: ProductCommissionGroup | None = None
    category_id: str | None = None
    card_type: CardType | None = None

    def __post_init__(self) -> None:
        if self.max_installments <= 0:
            raise ValueError("Taksit limiti sıfırdan büyük olmalıdır.")
        if not any(
            (
                self.channel,
                self.bank_id,
                self.product_group,
                self.category_id,
                self.card_type,
            )
        ):
            raise ValueError("Taksit limiti en az bir kapsam alanı içermelidir.")
        if self.category_id is not None and self.bank_id is not None:
            raise ValueError("Kategori taksit sınırı bankadan bağımsız olmalıdır.")

    @property
    def scope_key(self) -> str:
        return "|".join(
            (
                self.channel.value if self.channel else "-",
                self.bank_id or "-",
                self.product_group.value if self.product_group else "-",
                self.category_id or "-",
                self.card_type.value if self.card_type else "-",
            )
        )

    def _matches_dimensions(
        self,
        *,
        channel: PaymentChannel,
        product_group: ProductCommissionGroup,
        card_type: CardType,
    ) -> bool:
        if self.channel is not None and self.channel is not channel:
            return False
        if (
            self.product_group is not None
            and self.product_group is not product_group
        ):
            return False
        return not (
            self.card_type is not None and self.card_type is not card_type
        )

    def matches(
        self,
        *,
        channel: PaymentChannel,
        bank_id: str | None,
        product_group: ProductCommissionGroup,
        card_type: CardType,
    ) -> bool:
        if self.category_id is not None:
            return False
        if self.bank_id is not None and self.bank_id != bank_id:
            return False
        return self._matches_dimensions(
            channel=channel,
            product_group=product_group,
            card_type=card_type,
        )


@dataclass(frozen=True)
class ReferencePrice:
    cost: Decimal | None
    target_profit: Decimal | None
    target_amount: Decimal | None
    commission_percent: Decimal
    price: Decimal | None
    warning: str | None = None


def calculate_reference_price(
    cost: Decimal | None,
    target_type: ProfitTargetType | None,
    target_value: Decimal | None,
    commission_percent: Decimal,
) -> ReferencePrice:
    """Calculate the card reference price before commission."""
    if not (ZERO <= commission_percent <= HUNDRED):
        raise ValueError("Komisyon oranı %0 ile %100 arasında olmalıdır.")
    if cost is None:
        return ReferencePrice(
            cost=None,
            target_profit=None,
            target_amount=None,
            commission_percent=commission_percent,
            price=None,
            warning="Maliyet tanımlı değil; referans fiyat hesaplanamadı.",
        )
    if target_type is None or target_value is None:
        return ReferencePrice(
            cost=cost,
            target_profit=None,
            target_amount=None,
            commission_percent=commission_percent,
            price=None,
            warning="Hedef kâr tanımlı değil; referans fiyat hesaplanamadı.",
        )
    if target_value < ZERO:
        raise ValueError("Hedef kâr negatif olamaz.")
    target_profit = (
        quantize_money(cost * target_value / HUNDRED)
        if target_type is ProfitTargetType.PERCENT
        else quantize_money(target_value)
    )
    target_amount = quantize_money(cost + target_profit)
    if commission_percent == HUNDRED:
        return ReferencePrice(
            cost=cost,
            target_profit=target_profit,
            target_amount=target_amount,
            commission_percent=commission_percent,
            price=None,
            warning="Komisyon oranı %100 olduğu için referans fiyat hesaplanamadı.",
        )
    price = quantize_money(
        target_amount / (HUNDRED - commission_percent) * HUNDRED
    )
    return ReferencePrice(
        cost=cost,
        target_profit=target_profit,
        target_amount=target_amount,
        commission_percent=commission_percent,
        price=price,
    )


def _matching_rates(
    rates: Sequence[CommissionRate],
    *,
    channel: PaymentChannel,
    bank_id: str | None,
    product_group: ProductCommissionGroup,
    total: Decimal,
    installment_count: int | None = None,
) -> list[CommissionRate]:
    tier = amount_tier_for(channel, product_group, total)
    candidates = [
        rate
        for rate in rates
        if rate.channel is channel
        and (
            rate.product_group is product_group
            or (
                rate.product_group is None
                and channel is PaymentChannel.CHIPPIN
            )
        )
        and rate.amount_tier == tier
        and (
            installment_count is None
            or rate.installment_count == installment_count
        )
    ]
    if bank_id is not None:
        bank_specific = [
            rate for rate in candidates if rate.bank_id == bank_id
        ]
        if bank_specific:
            return bank_specific
    return [rate for rate in candidates if rate.bank_id is None]


def matching_commission_rate(
    rates: Sequence[CommissionRate],
    *,
    channel: PaymentChannel,
    bank_id: str | None,
    product_group: ProductCommissionGroup,
    installment_count: int,
    total: Decimal,
) -> CommissionRate | None:
    """Return the rate row that applies: bank-specific first, general second."""
    matches = _matching_rates(
        rates,
        channel=channel,
        bank_id=bank_id,
        product_group=product_group,
        total=total,
        installment_count=installment_count,
    )
    return matches[0] if matches else None


def effective_max_installments(
    rates: Sequence[CommissionRate],
    limits: Sequence[CommissionLimit],
    *,
    channel: PaymentChannel,
    bank_id: str | None,
    product_group: ProductCommissionGroup,
    card_type: CardType,
    total: Decimal,
    category_ids: Sequence[str] = (),
) -> int:
    """Resolve the effective installment cap for one card payment.

    Any matching bank-specific limit replaces the bankless general limits for
    that bank and may raise or lower them (Chippin needs this: a general
    1-installment limit plus a bank/card-specific higher limit). Category caps
    are bank-independent and are always applied on top; a bank-specific limit
    cannot raise them.
    """
    matching_rates = _matching_rates(
        rates,
        channel=channel,
        bank_id=bank_id,
        product_group=product_group,
        total=total,
    )
    if not matching_rates:
        return 0
    caps = [max(rate.installment_count for rate in matching_rates)]

    category_set = {str(category_id) for category_id in category_ids}
    if category_set:
        caps.extend(
            limit.max_installments
            for limit in limits
            if limit.category_id in category_set
            and limit._matches_dimensions(
                channel=channel,
                product_group=product_group,
                card_type=card_type,
            )
        )

    bank_specific: list[CommissionLimit] = []
    bankless: list[CommissionLimit] = []
    for limit in limits:
        if limit.category_id is not None:
            continue
        if not limit._matches_dimensions(
            channel=channel,
            product_group=product_group,
            card_type=card_type,
        ):
            continue
        if limit.bank_id is None:
            bankless.append(limit)
        elif limit.bank_id == bank_id:
            bank_specific.append(limit)

    chosen = bank_specific or bankless
    if chosen:
        caps.append(min(limit.max_installments for limit in chosen))

    return min(caps)


def commission_percent_for(
    rates: Sequence[CommissionRate],
    *,
    channel: PaymentChannel,
    bank_id: str | None,
    product_group: ProductCommissionGroup,
    installment_count: int,
    total: Decimal,
) -> Decimal | None:
    rate = matching_commission_rate(
        rates,
        channel=channel,
        bank_id=bank_id,
        product_group=product_group,
        installment_count=installment_count,
        total=total,
    )
    return rate.commission_percent if rate is not None else None



def period_key_for(moment: date | datetime) -> str:
    return f"{moment.year:04d}-{moment.month:02d}"


def period_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    if not 1 <= month <= 12:
        raise ValueError("Ay 1 ile 12 arasında olmalıdır.")
    last_day = calendar.monthrange(year, month)[1]
    start = datetime(year, month, 1, tzinfo=UTC)
    end = datetime(year, month, last_day, 23, 59, 59, 999999, tzinfo=UTC)
    return start, end


def next_month(year: int, month: int, offset: int = 1) -> tuple[int, int]:
    index = year * 12 + (month - 1) + offset
    return index // 12, index % 12 + 1


def validate_period(
    *,
    period_key: str,
    valid_from: datetime,
    valid_until: datetime,
    status: CommissionPeriodStatus,
) -> None:
    try:
        year_str, month_str = period_key.split("-")
        year, month = int(year_str), int(month_str)
    except (ValueError, AttributeError) as exc:
        raise ValueError("Dönem anahtarı YYYY-MM biçiminde olmalıdır.") from exc
    expected_start, expected_end = period_bounds(year, month)
    if valid_from.date() != expected_start.date():
        raise ValueError("Dönem başlangıcı ayın ilk günü olmalıdır.")
    if valid_until.date() != expected_end.date():
        raise ValueError("Dönem bitişi ayın son günü olmalıdır.")
    if status not in CommissionPeriodStatus:
        raise ValueError("Geçersiz komisyon dönemi durumu.")


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
