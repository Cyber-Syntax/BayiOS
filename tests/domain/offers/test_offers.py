from __future__ import annotations

from decimal import Decimal

import pytest

from bayios.domain.commissions import ProfitTargetType
from bayios.domain.offers import (
    OfferPriceLayers,
    OfferStatus,
    PaymentType,
    ensure_status_transition,
    quote_offer_item,
    summarize_offer,
)


def test_base_price_prefers_campaign_then_website_then_regular() -> None:
    assert OfferPriceLayers(regular_price=Decimal(50000)).base_price == Decimal(50000)
    assert (
        OfferPriceLayers(
            regular_price=Decimal(50000), website_price=Decimal(46000)
        ).base_price
        == Decimal(46000)
    )
    assert (
        OfferPriceLayers(
            regular_price=Decimal(50000),
            website_price=Decimal(46000),
            campaign_price=Decimal(45000),
        ).base_price
        == Decimal(45000)
    )


def test_wedding_example_bay_discount_and_manual_prices() -> None:
    layers = OfferPriceLayers(
        cost_price=Decimal(36000),
        regular_price=Decimal(50000),
        website_price=Decimal(46000),
        campaign_price=Decimal(45000),
        campaign_name="Düğün %10",
    )

    quote = quote_offer_item(
        layers,
        quantity=1,
        dealer_discount_percent=Decimal(10),
        commission_percent=Decimal(5),
        target_type=ProfitTargetType.FIXED_AMOUNT,
        target_value=Decimal(1500),
        cash_floor=Decimal(36000),
        card_floor=Decimal(39000),
        unit_price_cash=Decimal(36000),
        unit_price_card=Decimal(40000),
    )

    assert quote.base_price == Decimal(45000)
    assert quote.suggested_cash_price == Decimal("40500.00")
    assert quote.unit_price_cash == Decimal("36000.00")
    assert quote.unit_price_card == Decimal("40000.00")
    assert "Kampanya seçildiği için Oliz fiyatı uygulanmadı." in quote.warnings


def test_floor_and_reference_warnings_do_not_block() -> None:
    quote = quote_offer_item(
        OfferPriceLayers(
            cost_price=Decimal(36000),
            regular_price=Decimal(50000),
        ),
        quantity=2,
        dealer_discount_percent=Decimal(10),
        commission_percent=Decimal(5),
        target_type=ProfitTargetType.FIXED_AMOUNT,
        target_value=Decimal(5000),
        cash_floor=Decimal(36000),
        card_floor=Decimal(39000),
        unit_price_cash=Decimal(30000),
        unit_price_card=Decimal(30000),
    )

    assert quote.line_total_cash == Decimal("60000.00")
    assert quote.line_total_card == Decimal("60000.00")
    assert any("tabanının altında" in warning for warning in quote.warnings)
    assert any("referansının altında" in warning for warning in quote.warnings)


def test_offer_totals_select_payment_type() -> None:
    quote_cash = quote_offer_item(
        OfferPriceLayers(regular_price=Decimal(100)),
        quantity=2,
        dealer_discount_percent=Decimal(0),
        commission_percent=Decimal(0),
        target_type=ProfitTargetType.FIXED_AMOUNT,
        target_value=Decimal(0),
    )
    quote_card = quote_offer_item(
        OfferPriceLayers(regular_price=Decimal(200)),
        quantity=1,
        dealer_discount_percent=Decimal(0),
        commission_percent=Decimal(0),
        target_type=ProfitTargetType.FIXED_AMOUNT,
        target_value=Decimal(0),
    )

    totals = summarize_offer((quote_cash, quote_card), PaymentType.CARD)
    assert totals.cash_total == Decimal("400.00")
    assert totals.card_total == Decimal("400.00")
    assert totals.selected_total == Decimal("400.00")


def test_status_transitions() -> None:
    ensure_status_transition(OfferStatus.DRAFT, OfferStatus.PRESENTED)
    ensure_status_transition(OfferStatus.PRESENTED, OfferStatus.ACCEPTED)
    with pytest.raises(ValueError):
        ensure_status_transition(OfferStatus.ACCEPTED, OfferStatus.DRAFT)
    with pytest.raises(ValueError):
        ensure_status_transition(OfferStatus.DRAFT, OfferStatus.ACCEPTED)


def test_missing_base_price_returns_warning() -> None:
    quote = quote_offer_item(
        OfferPriceLayers(),
        quantity=1,
        dealer_discount_percent=Decimal(10),
        commission_percent=Decimal(5),
        target_type=None,
        target_value=None,
    )

    assert quote.base_price is None
    assert quote.unit_price_cash is None
    assert quote.warnings
