from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from bayios.domain.campaigns import (
    BasePriceType,
    CampaignContract,
    CampaignPaymentCondition,
    CampaignProductLink,
    CampaignType,
    DiscountType,
    PaymentContext,
    ProductRelationType,
)
from bayios.domain.campaigns.resolution import (
    BasketCampaign,
    BasketLine,
    resolve_basket,
)

NOW = datetime(2026, 11, 20, tzinfo=UTC)


def _dugun() -> CampaignContract:
    return CampaignContract(
        name="Düğün",
        campaign_type=CampaignType.PRODUCT_DISCOUNT,
        starts_at=NOW,
        ends_at=NOW,
        base_price_type=BasePriceType.REGULAR,
        discount_type=DiscountType.PERCENT,
        discount_value=Decimal(10),
        products=(
            CampaignProductLink("p1", "383510 EI", ProductRelationType.RELATED),
            CampaignProductLink("p2", "12142 A", ProductRelationType.RELATED),
            CampaignProductLink("p3", "A 811 i sd", ProductRelationType.RELATED),
        ),
    )


def _bundle(*, qualifying: tuple[str, ...] = ("p1", "p2", "p3")) -> CampaignContract:
    return CampaignContract(
        name="Kurutma / Klima",
        campaign_type=CampaignType.BUNDLE,
        starts_at=NOW,
        ends_at=NOW,
        base_price_type=BasePriceType.REGULAR,
        discount_type=DiscountType.FIXED_AMOUNT,
        discount_value=Decimal(17850),
        combines_with_others=False,
        products=tuple(
            CampaignProductLink(product_id, product_id, ProductRelationType.QUALIFYING)
            for product_id in qualifying
        )
        + (
            CampaignProductLink(
                None,
                "Kurutma Makinesi",
                ProductRelationType.BENEFIT,
                category_id="cat-kurutma",
                discount_type=DiscountType.FIXED_AMOUNT,
                discount_value=Decimal(17850),
                base_price_type=BasePriceType.REGULAR,
                applies_per_unit=False,
            ),
            CampaignProductLink(
                None,
                "Klima",
                ProductRelationType.BENEFIT,
                category_id="cat-klima",
                discount_type=DiscountType.FIXED_AMOUNT,
                discount_value=Decimal(19200),
                base_price_type=BasePriceType.REGULAR,
                applies_per_unit=False,
            ),
        ),
    )


def _campaigns(*contracts: CampaignContract) -> list[BasketCampaign]:
    return [
        BasketCampaign(
            campaign_id=f"c{index}",
            version_id=f"v{index}",
            name=contract.name,
            version_no=1,
            contract=contract,
        )
        for index, contract in enumerate(contracts)
    ]


def _base_lines() -> list[BasketLine]:
    return [
        BasketLine("l1", "p1", "cat-fridge", 1, Decimal(89799), Decimal(86299)),
        BasketLine("l2", "p2", "cat-wash", 1, Decimal(47599), None),
        BasketLine("l3", "p3", "cat-dish", 1, Decimal(46499), Decimal(41499)),
    ]


def _total(lines) -> Decimal:
    return sum(
        (benefit.unit_discount for benefit in lines.values()),
        Decimal(0),
    )


def test_wedding_and_oliz_choose_best_per_line() -> None:
    resolution = resolve_basket(_base_lines(), _campaigns(_dugun()))
    assert resolution.lines["l1"].campaign_name == "Düğün"
    assert resolution.lines["l1"].unit_discount == Decimal("8979.90")
    assert resolution.lines["l2"].unit_discount == Decimal("4759.90")
    assert resolution.lines["l3"].source == "oliz"
    assert resolution.lines["l3"].unit_discount == Decimal("5000.00")
    assert _total(resolution.lines) == Decimal("18739.80")


def test_bundle_is_one_time_and_allocated_pro_rata() -> None:
    lines = _base_lines() + [
        BasketLine("l4", "p4", "cat-kurutma", 1, Decimal(35699), None)
    ]
    resolution = resolve_basket(lines, _campaigns(_dugun(), _bundle()))
    assert resolution.lines["l1"].campaign_name == "Düğün"
    assert resolution.lines["l1"].unit_discount == Decimal("8979.90")
    assert resolution.lines["l2"].campaign_name == "Kurutma / Klima"
    assert resolution.lines["l2"].unit_discount == Decimal("10200.03")
    assert resolution.lines["l4"].unit_discount == Decimal("7649.97")
    assert resolution.lines["l3"].source == "oliz"
    assert _total(resolution.lines) == Decimal("31829.90")


def test_bundle_requires_a_benefit_line() -> None:
    resolution = resolve_basket(_base_lines(), _campaigns(_dugun(), _bundle()))
    assert resolution.applied_campaign_ids == ()
    assert resolution.lines["l2"].campaign_name == "Düğün"
    assert _total(resolution.lines) == Decimal("18739.80")


def test_bundle_requires_a_qualifying_line() -> None:
    lines = [BasketLine("l4", "p4", "cat-kurutma", 1, Decimal(35699), None)]
    resolution = resolve_basket(lines, _campaigns(_bundle()))
    assert resolution.applied_campaign_ids == ()
    assert resolution.lines["l4"].unit_discount == Decimal(0)


def test_second_dryer_does_not_double_the_bundle() -> None:
    lines = _base_lines() + [
        BasketLine("l4", "p4", "cat-kurutma", 1, Decimal(35699), None),
        BasketLine("l5", "p5", "cat-kurutma", 1, Decimal(35699), None),
    ]
    resolution = resolve_basket(lines, _campaigns(_bundle()))
    bundle_lines = [
        benefit
        for benefit in resolution.lines.values()
        if benefit.campaign_name == "Kurutma / Klima"
    ]
    assert len(bundle_lines) == 3
    assert sum(
        (benefit.unit_discount for benefit in bundle_lines), Decimal(0)
    ) == Decimal("17850.00")


def test_climate_and_dryer_do_not_add_two_basket_discounts() -> None:
    lines = _base_lines() + [
        BasketLine("l4", "p4", "cat-kurutma", 1, Decimal(35699), None),
        BasketLine("l5", "p5", "cat-klima", 1, Decimal(50000), None),
    ]
    resolution = resolve_basket(lines, _campaigns(_bundle()))
    flat_total = sum(
        (
            benefit.unit_discount
            for benefit in resolution.lines.values()
            if benefit.is_flat_allocation
        ),
        Decimal(0),
    )
    assert flat_total == Decimal("19200.00")
    assert _total(resolution.lines) == Decimal("27700.00")


def test_min_basket_total_blocks_and_allows_campaign() -> None:
    contract = CampaignContract(
        name="Eşik",
        campaign_type=CampaignType.PRODUCT_DISCOUNT,
        starts_at=NOW,
        ends_at=NOW,
        discount_type=DiscountType.PERCENT,
        discount_value=Decimal(10),
        min_basket_total=Decimal(50000),
        products=(CampaignProductLink("p1", "Ürün", ProductRelationType.RELATED),),
    )
    low = [BasketLine("l1", "p1", None, 1, Decimal(40000), None)]
    high = [BasketLine("l1", "p1", None, 1, Decimal(60000), None)]
    assert resolve_basket(low, _campaigns(contract)).lines["l1"].unit_discount == Decimal(0)
    assert resolve_basket(high, _campaigns(contract)).lines["l1"].unit_discount == Decimal("6000.00")


def _conditional_campaign() -> CampaignContract:
    return CampaignContract(
        name="Banka Koşullu",
        campaign_type=CampaignType.PRODUCT_DISCOUNT,
        starts_at=NOW,
        ends_at=NOW,
        discount_type=DiscountType.PERCENT,
        discount_value=Decimal(10),
        payment_conditions=(
            CampaignPaymentCondition(
                channel="pos",
                bank_ids=("b1",),
                card_type="consumer",
                installment_count=8,
            ),
        ),
        products=(
            CampaignProductLink("p1", "Ürün", ProductRelationType.RELATED),
        ),
    )


def test_payment_condition_filters_cash_and_card() -> None:
    lines = [BasketLine("l1", "p1", None, 1, Decimal(10000), None)]
    campaign = _campaigns(_conditional_campaign())
    cash = resolve_basket(
        lines,
        campaign,
        payment=PaymentContext(payment_type="cash"),
    )
    assert cash.lines["l1"].unit_discount == Decimal(0)

    matching = resolve_basket(
        lines,
        campaign,
        payment=PaymentContext(
            payment_type="card",
            channel="pos",
            bank_id="b1",
            card_type="consumer",
            installment_count=8,
        ),
    )
    assert matching.lines["l1"].unit_discount == Decimal("1000.00")

    other_bank = resolve_basket(
        lines,
        campaign,
        payment=PaymentContext(
            payment_type="card",
            channel="pos",
            bank_id="b2",
            card_type="consumer",
            installment_count=8,
        ),
    )
    assert other_bank.lines["l1"].unit_discount == Decimal(0)

    other_installment = resolve_basket(
        lines,
        campaign,
        payment=PaymentContext(
            payment_type="card",
            channel="pos",
            bank_id="b1",
            card_type="consumer",
            installment_count=9,
        ),
    )
    assert other_installment.lines["l1"].unit_discount == Decimal(0)


def test_qualifying_quantity_required_is_enforced() -> None:
    contract = CampaignContract(
        name="Adet Şartlı",
        campaign_type=CampaignType.PRODUCT_DISCOUNT,
        starts_at=NOW,
        ends_at=NOW,
        discount_type=DiscountType.PERCENT,
        discount_value=Decimal(10),
        products=(
            CampaignProductLink(
                "p1",
                "Ürün",
                ProductRelationType.QUALIFYING,
                quantity_required=2,
            ),
            CampaignProductLink("p1", "Ürün", ProductRelationType.RELATED),
        ),
    )
    one = [BasketLine("l1", "p1", None, 1, Decimal(10000), None)]
    two = [BasketLine("l1", "p1", None, 2, Decimal(10000), None)]
    assert resolve_basket(one, _campaigns(contract)).lines["l1"].unit_discount == Decimal(0)
    assert resolve_basket(two, _campaigns(contract)).lines["l1"].unit_discount == Decimal("1000.00")
