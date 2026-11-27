from __future__ import annotations

from decimal import Decimal

from bayios.domain.offers.pricing import (
    CompanyDiscountSource,
    CompanyPriceCandidate,
    company_share_for,
    oliz_candidate,
    price_unit,
    profit_line,
    select_company_price,
)


def test_auto_selects_campaign_when_it_beats_oliz() -> None:
    campaign = CompanyPriceCandidate(
        source=CompanyDiscountSource.CAMPAIGN,
        price=Decimal("45000.00"),
        discount_amount=Decimal("5000.00"),
        share_amount=Decimal("5000.00"),
        campaign_id="c1",
        campaign_name="Düğün",
    )

    selected = select_company_price(
        regular_price=Decimal("50000.00"),
        oliz_price=Decimal("46000.00"),
        campaigns=(campaign,),
    )

    assert selected is not None
    assert selected.source is CompanyDiscountSource.CAMPAIGN
    assert selected.price == Decimal("45000.00")


def test_auto_selects_oliz_when_it_beats_campaign() -> None:
    campaign = CompanyPriceCandidate(
        source=CompanyDiscountSource.CAMPAIGN,
        price=Decimal("45000.00"),
        discount_amount=Decimal("5000.00"),
        share_amount=Decimal("5000.00"),
        campaign_id="c1",
        campaign_name="Düğün",
    )

    selected = select_company_price(
        regular_price=Decimal("50000.00"),
        oliz_price=Decimal("40000.00"),
        campaigns=(campaign,),
    )

    assert selected is not None
    assert selected.source is CompanyDiscountSource.OLIZ
    assert selected.discount_amount == Decimal("10000.00")


def test_explicit_campaign_and_none_modes() -> None:
    campaign = CompanyPriceCandidate(
        source=CompanyDiscountSource.CAMPAIGN,
        price=Decimal("45000.00"),
        discount_amount=Decimal("5000.00"),
        share_amount=Decimal("5000.00"),
        campaign_id="c1",
        campaign_name="Düğün",
    )

    explicit = select_company_price(
        regular_price=Decimal("50000.00"),
        oliz_price=Decimal("40000.00"),
        campaigns=(campaign,),
        mode="c1",
    )
    assert explicit is not None
    assert explicit.source is CompanyDiscountSource.CAMPAIGN

    no_campaign = select_company_price(
        regular_price=Decimal("50000.00"),
        oliz_price=Decimal("40000.00"),
        campaigns=(campaign,),
        mode="none",
    )
    assert no_campaign is not None
    assert no_campaign.source is CompanyDiscountSource.OLIZ


def test_price_unit_applies_dealer_discount_once() -> None:
    campaign = CompanyPriceCandidate(
        source=CompanyDiscountSource.CAMPAIGN,
        price=Decimal("36000.00"),
        discount_amount=Decimal("4000.00"),
        share_amount=Decimal("4000.00"),
    )

    pricing = price_unit(
        campaign,
        dealer_discount_percent=Decimal(10),
        dealer_discount_cash_percent=Decimal(10),
    )

    assert pricing.suggested_cash == Decimal("32400.00")
    assert pricing.suggested_card == Decimal("32400.00")
    assert pricing.company_share == Decimal("4000.00")
    assert company_share_for(pricing, Decimal(85)) == Decimal("3400.00")


def test_dealer_discount_does_not_create_company_share() -> None:
    regular = CompanyPriceCandidate(
        source=CompanyDiscountSource.NONE,
        price=Decimal("40000.00"),
        discount_amount=Decimal(0),
        share_amount=Decimal(0),
    )

    pricing = price_unit(
        regular,
        dealer_discount_percent=Decimal(10),
        dealer_discount_cash_percent=Decimal(10),
    )
    line = profit_line(
        sale_price=pricing.unit_cash,
        quantity=1,
        commission_percent=Decimal(5),
        company_share_per_unit=company_share_for(pricing, Decimal(85)),
        cost_price=Decimal("32077.86"),
    )

    assert pricing.unit_cash == Decimal("36000.00")
    assert line.company_share == Decimal("0.00")
    assert line.profit == Decimal("2122.14")


def test_oliz_share_uses_normal_minus_oliz() -> None:
    oliz = oliz_candidate(Decimal("40000.00"), Decimal("36000.00"))
    assert oliz is not None
    assert oliz.share_amount == Decimal("4000.00")


def test_profit_line_totals_quantity() -> None:
    line = profit_line(
        sale_price=Decimal("10000.00"),
        quantity=2,
        commission_percent=Decimal(5),
        company_share_per_unit=Decimal("500.00"),
        cost_price=Decimal("8000.00"),
    )

    assert line.net_after_commission == Decimal("19000.00")
    assert line.company_share == Decimal("1000.00")
    assert line.total_revenue == Decimal("20000.00")
    assert line.profit == Decimal("4000.00")
