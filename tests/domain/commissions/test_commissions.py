from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from bayios.domain.commissions import (
    BUSINESS_MAX_INSTALLMENTS,
    CardType,
    CommissionLimit,
    CommissionPeriodStatus,
    CommissionRate,
    OderoTier,
    PaymentChannel,
    ProductCommissionGroup,
    ProfitTargetType,
    calculate_reference_price,
    commission_percent_for,
    effective_max_installments,
    odero_tier,
    period_bounds,
    period_key_for,
    validate_period,
)


def _rate(
    channel: PaymentChannel,
    installment: int,
    percent: str,
    *,
    group: ProductCommissionGroup = ProductCommissionGroup.OTHER,
    bank: str | None = "ykb",
    tier: OderoTier | None = None,
) -> CommissionRate:
    return CommissionRate(
        channel=channel,
        bank_id=bank,
        product_group=group,
        installment_count=installment,
        commission_percent=Decimal(percent),
        amount_tier=tier,
    )


def test_period_helpers_and_validation() -> None:
    start, end = period_bounds(2026, 11)

    assert period_key_for(datetime(2026, 11, 11, tzinfo=UTC)) == "2026-11"
    assert start == datetime(2026, 11, 1, tzinfo=UTC)
    assert end.day == 30
    validate_period(
        period_key="2026-11",
        valid_from=start,
        valid_until=end,
        status=CommissionPeriodStatus.ACTIVE,
    )
    with pytest.raises(ValueError):
        validate_period(
            period_key="2026-11",
            valid_from=start,
            valid_until=datetime(2026, 11, 29, tzinfo=UTC),
            status=CommissionPeriodStatus.ACTIVE,
        )


def test_rate_validation() -> None:
    assert _rate(PaymentChannel.POS, 2, "4", bank=None).bank_id is None
    with pytest.raises(ValueError):
        _rate(PaymentChannel.CHIPPIN, 1, "3", bank="ykb")
    with pytest.raises(ValueError):
        _rate(PaymentChannel.ODERO, 2, "4", bank="ykb", tier=None)
    with pytest.raises(ValueError):
        _rate(PaymentChannel.POS, 2, "101")
    with pytest.raises(ValueError):
        _rate(PaymentChannel.POS, 0, "4")


def test_odero_tier_uses_basket_total() -> None:
    assert odero_tier(Decimal(19999)) is OderoTier.UNDER_20000
    assert odero_tier(Decimal(20000)) is OderoTier.OVER_20000
    assert odero_tier(Decimal(50000)) is OderoTier.OVER_20000


def test_effective_max_installments_applies_all_caps() -> None:
    pos_rates = [
        _rate(PaymentChannel.POS, installment, "4")
        for installment in range(1, 11)
    ]
    klima_rates = [
        _rate(
            PaymentChannel.POS,
            installment,
            "5",
            group=ProductCommissionGroup.KLIMA,
        )
        for installment in range(1, 11)
    ]
    limits = [
        CommissionLimit(channel=PaymentChannel.POS, max_installments=8),
        CommissionLimit(channel=PaymentChannel.ODERO, max_installments=5),
        CommissionLimit(
            channel=PaymentChannel.ODERO, bank_id="ykb", max_installments=2
        ),
        CommissionLimit(channel=PaymentChannel.CHIPPIN, max_installments=6),
        CommissionLimit(
            product_group=ProductCommissionGroup.KLIMA, max_installments=10
        ),
        CommissionLimit(category_id="tv-cat", max_installments=4),
        CommissionLimit(
            product_group=ProductCommissionGroup.OTHER, max_installments=5
        ),
        CommissionLimit(card_type=CardType.BUSINESS, max_installments=2),
    ]
    total = Decimal(50000)

    assert (
        effective_max_installments(
            pos_rates,
            limits,
            channel=PaymentChannel.POS,
            bank_id="ykb",
            product_group=ProductCommissionGroup.OTHER,
            card_type=CardType.CONSUMER,
            total=total,
        )
        == 5
    )
    assert (
        effective_max_installments(
            pos_rates,
            limits,
            channel=PaymentChannel.POS,
            bank_id="ykb",
            product_group=ProductCommissionGroup.OTHER,
            card_type=CardType.CONSUMER,
            total=total,
            category_ids=("tv-cat",),
        )
        == 4
    )
    assert (
        effective_max_installments(
            klima_rates,
            limits,
            channel=PaymentChannel.POS,
            bank_id="ykb",
            product_group=ProductCommissionGroup.KLIMA,
            card_type=CardType.CONSUMER,
            total=total,
        )
        == 8
    )
    assert (
        effective_max_installments(
            pos_rates,
            limits,
            channel=PaymentChannel.POS,
            bank_id="ykb",
            product_group=ProductCommissionGroup.OTHER,
            card_type=CardType.BUSINESS,
            total=total,
        )
        == BUSINESS_MAX_INSTALLMENTS
    )

    odero_rates = [
        _rate(
            PaymentChannel.ODERO,
            installment,
            "4",
            tier=OderoTier.OVER_20000,
        )
        for installment in range(1, 7)
    ]
    odero_other_rates = [
        _rate(
            PaymentChannel.ODERO,
            installment,
            "4",
            bank="other",
            tier=OderoTier.OVER_20000,
        )
        for installment in range(1, 7)
    ]
    assert (
        effective_max_installments(
            odero_rates,
            limits,
            channel=PaymentChannel.ODERO,
            bank_id="ykb",
            product_group=ProductCommissionGroup.OTHER,
            card_type=CardType.CONSUMER,
            total=Decimal(50000),
        )
        == 2
    )
    assert (
        effective_max_installments(
            odero_other_rates,
            limits,
            channel=PaymentChannel.ODERO,
            bank_id="other",
            product_group=ProductCommissionGroup.OTHER,
            card_type=CardType.CONSUMER,
            total=Decimal(50000),
        )
        == 5
    )


def test_bank_specific_limit_replaces_general_limit() -> None:
    rates = [
        _rate(PaymentChannel.POS, installment, "4", bank=None)
        for installment in range(1, 11)
    ]
    limits = [
        CommissionLimit(channel=PaymentChannel.POS, max_installments=5),
        CommissionLimit(
            channel=PaymentChannel.POS, bank_id="akbank", max_installments=8
        ),
    ]

    assert (
        effective_max_installments(
            rates,
            limits,
            channel=PaymentChannel.POS,
            bank_id="akbank",
            product_group=ProductCommissionGroup.OTHER,
            card_type=CardType.CONSUMER,
            total=Decimal(1000),
        )
        == 8
    )
    assert (
        effective_max_installments(
            rates,
            limits,
            channel=PaymentChannel.POS,
            bank_id="other-bank",
            product_group=ProductCommissionGroup.OTHER,
            card_type=CardType.CONSUMER,
            total=Decimal(1000),
        )
        == 5
    )


def test_category_cap_cannot_be_raised_by_bank_limit() -> None:
    rates = [
        _rate(PaymentChannel.POS, installment, "4", bank=None)
        for installment in range(1, 11)
    ]
    limits = [
        CommissionLimit(
            channel=PaymentChannel.POS, bank_id="akbank", max_installments=8
        ),
        CommissionLimit(category_id="tv-cat", max_installments=4),
    ]

    assert (
        effective_max_installments(
            rates,
            limits,
            channel=PaymentChannel.POS,
            bank_id="akbank",
            product_group=ProductCommissionGroup.OTHER,
            card_type=CardType.CONSUMER,
            total=Decimal(1000),
            category_ids=("tv-cat",),
        )
        == 4
    )




def test_commission_percent_lookup() -> None:
    rates = [
        _rate(PaymentChannel.POS, 2, "4"),
        _rate(PaymentChannel.POS, 3, "4.67"),
        _rate(
            PaymentChannel.ODERO,
            2,
            "5",
            tier=OderoTier.OVER_20000,
        ),
    ]

    assert (
        commission_percent_for(
            rates,
            channel=PaymentChannel.POS,
            bank_id="ykb",
            product_group=ProductCommissionGroup.OTHER,
            installment_count=3,
            total=Decimal(50000),
        )
        == Decimal("4.67")
    )
    assert (
        commission_percent_for(
            rates,
            channel=PaymentChannel.ODERO,
            bank_id="ykb",
            product_group=ProductCommissionGroup.OTHER,
            installment_count=2,
            total=Decimal(20000),
        )
        == Decimal(5)
    )
    assert (
        commission_percent_for(
            rates,
            channel=PaymentChannel.ODERO,
            bank_id="ykb",
            product_group=ProductCommissionGroup.OTHER,
            installment_count=2,
            total=Decimal(19999),
        )
        is None
    )


def test_rate_lookup_falls_back_to_general() -> None:
    rates = [
        _rate(PaymentChannel.POS, installment, "4", bank=None)
        for installment in range(1, 11)
    ] + [_rate(PaymentChannel.POS, 8, "15", bank="akbank")]

    assert (
        commission_percent_for(
            rates,
            channel=PaymentChannel.POS,
            bank_id="akbank",
            product_group=ProductCommissionGroup.OTHER,
            installment_count=2,
            total=Decimal(1000),
        )
        == Decimal(4)
    )
    assert (
        commission_percent_for(
            rates,
            channel=PaymentChannel.POS,
            bank_id="akbank",
            product_group=ProductCommissionGroup.OTHER,
            installment_count=8,
            total=Decimal(1000),
        )
        == Decimal(15)
    )
    assert (
        commission_percent_for(
            rates,
            channel=PaymentChannel.POS,
            bank_id="other-bank",
            product_group=ProductCommissionGroup.OTHER,
            installment_count=8,
            total=Decimal(1000),
        )
        == Decimal(4)
    )


def test_chippin_rate_without_group_applies() -> None:
    rates = [
        CommissionRate(
            channel=PaymentChannel.CHIPPIN,
            bank_id=None,
            product_group=None,
            installment_count=2,
            commission_percent=Decimal(3),
        )
    ]

    assert (
        commission_percent_for(
            rates,
            channel=PaymentChannel.CHIPPIN,
            bank_id=None,
            product_group=ProductCommissionGroup.OTHER,
            installment_count=2,
            total=Decimal(1000),
        )
        == Decimal(3)
    )


def test_reference_price_examples() -> None:
    reference = calculate_reference_price(
        Decimal(30000),
        ProfitTargetType.FIXED_AMOUNT,
        Decimal(1500),
        Decimal(5),
    )
    zero = calculate_reference_price(
        Decimal(30000),
        ProfitTargetType.FIXED_AMOUNT,
        Decimal(1500),
        Decimal(0),
    )
    missing = calculate_reference_price(
        Decimal(30000), None, None, Decimal(5)
    )
    no_cost = calculate_reference_price(
        None, ProfitTargetType.PERCENT, Decimal(10), Decimal(5)
    )

    assert reference.price == Decimal("33157.89")
    assert zero.price == Decimal("31500.00")
    assert missing.price is None
    assert missing.warning is not None
    assert "Hedef kâr" in missing.warning
    assert no_cost.price is None
    assert no_cost.warning is not None
