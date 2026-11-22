from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from bayios.adapters.db.models.offers import Offer, OfferItem
from bayios.adapters.db.models.products import Product
from bayios.application.campaigns import (
    CampaignInput,
    CampaignProductInput,
    create_campaign,
)
from bayios.application.errors import ValidationError
from bayios.application.offers import (
    OfferDetail,
    OfferInput,
    OfferItemInput,
    build_offer_line_analyses,
    build_offer_profit_summary,
    convert_offer_to_reservation,
    create_offer,
    get_offer_detail,
    preview_offer_comparison,
    preview_offer_line,
    set_offer_status,
    update_offer,
)
from bayios.domain.campaigns import (
    BasePriceType,
    CampaignType,
    DiscountType,
    ProductRelationType,
)
from bayios.domain.commissions import CardType, PaymentChannel
from bayios.domain.offers import OfferStatus, PaymentType
from tests.fakes import FakeUnitOfWork


def test_odero_commission_uses_card_total_not_base_total() -> None:
    from datetime import UTC, datetime

    from bayios.adapters.db.models.commissions import (
        CommissionPeriod,
        CommissionRate,
    )

    uow = FakeUnitOfWork()
    product = Product(
        id=uuid.uuid4(),
        name="Buzdolabı",
        name_normalized="buzdolabi",
        regular_price=Decimal("21000.00"),
        website_discounted_price=Decimal("21000.00"),
        cost_price=Decimal("15000.00"),
        physical_stock=1,
    )
    uow.products.add(product)
    period = CommissionPeriod(
        id=uuid.uuid4(),
        period_key="2026-11",
        valid_from=datetime(2026, 11, 1, tzinfo=UTC),
        valid_until=datetime(2026, 11, 30, 23, 59, tzinfo=UTC),
        status="active",
    )
    uow.commissions.add_period(period)
    for tier, percent in (("under_20000", "4.00"), ("over_20000", "5.00")):
        uow.commissions.add_rate(
            CommissionRate(
                id=uuid.uuid4(),
                period_id=period.id,
                channel="odero",
                bank_id=None,
                product_group="other",
                amount_tier=tier,
                installment_count=1,
                commission_percent=Decimal(percent),
                scope_key=f"odero||other|{tier}|1",
            )
        )

    offer_id = create_offer(
        uow,
        OfferInput(
            customer_name="Kart Müşteri",
            customer_phone=None,
            payment_type=PaymentType.CARD,
            dealer_discount_percent=Decimal(10),
            dealer_discount_cash_percent=Decimal(15),
            channel=PaymentChannel.ODERO,
            installment_count=1,
            card_type=CardType.CONSUMER,
            items=(OfferItemInput(product.id, 1),),
        ),
    )
    detail = get_offer_detail(uow, offer_id)

    assert detail is not None
    assert detail.offer.card_total == Decimal("18900.00")
    assert detail.offer.commission_percent_snapshot == Decimal("4.00")



def test_zero_website_price_does_not_create_phantom_oliz_share() -> None:
    from bayios.application.offers import build_offer_profit_summary

    uow, product_id = _active_card_uow()
    product = uow.products.products[product_id]
    product.website_discounted_price = Decimal("0.00")

    offer_id = create_offer(
        uow,
        OfferInput(
            customer_name="Olizsiz",
            customer_phone=None,
            payment_type=PaymentType.CARD,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product_id, 1),),
            channel=PaymentChannel.POS,
            installment_count=2,
            card_type=CardType.CONSUMER,
        ),
    )
    detail = get_offer_detail(uow, offer_id)
    assert detail is not None
    assert detail.items[0].base_price_used == Decimal("10000.00")
    assert detail.items[0].website_price_snapshot is None
    assert detail.items[0].unit_price_card == Decimal("9000.00")

    summary = build_offer_profit_summary(detail)
    line = summary.lines[0]
    assert line.oliz_share == Decimal("0.00")
    assert line.campaign_share == Decimal("0.00")
    assert line.net_after_commission == Decimal("8550.00")
    assert line.profit == Decimal("550.00")


def test_category_cap_applies_to_card_offer() -> None:
    from bayios.adapters.db.models.commissions import CommissionLimit
    from bayios.adapters.db.models.products import ProductCategory

    uow, product_id = _active_card_uow()
    category = ProductCategory(
        id=uuid.uuid4(), name="TV", name_normalized="tv", commission_group="other"
    )
    uow.products.add_category(category)
    product = uow.products.products[product_id]
    product.category_id = category.id
    period = next(iter(uow.commissions.periods.values()))
    uow.commissions.add_limit(
        CommissionLimit(
            id=uuid.uuid4(),
            period_id=period.id,
            channel=None,
            bank_id=None,
            product_group=None,
            category_id=category.id,
            card_type=None,
            max_installments=2,
            scope_key=f"-|-|-|{category.id}|-",
        )
    )

    with pytest.raises(ValidationError, match="en fazla 2"):
        create_offer(
            uow,
            OfferInput(
                customer_name="Ayşe",
                customer_phone=None,
                payment_type=PaymentType.CARD,
                dealer_discount_percent=Decimal(10),
                items=(OfferItemInput(product_id, 1),),
                channel=PaymentChannel.POS,
                installment_count=3,
                card_type=CardType.CONSUMER,
            ),
        )



def _active_card_uow(
    *,
    bank_id: uuid.UUID | None = None,
) -> tuple[FakeUnitOfWork, uuid.UUID]:
    from bayios.adapters.db.models.commissions import (
        Bank,
        CommissionPeriod,
        CommissionRate,
    )
    from bayios.domain.commissions import period_bounds

    uow = FakeUnitOfWork()
    start, end = period_bounds(2026, 11)
    period = CommissionPeriod(
        id=uuid.uuid4(),
        period_key="2026-11",
        valid_from=start,
        valid_until=end,
        status="active",
    )
    uow.commissions.add_period(period)
    if bank_id is not None:
        uow.commissions.add_bank(
            Bank(
                id=bank_id,
                name="Akbank",
                name_normalized="akbank",
                is_active=True,
            )
        )
    for installment in range(1, 4):
        uow.commissions.add_rate(
            CommissionRate(
                id=uuid.uuid4(),
                period_id=period.id,
                channel="pos",
                bank_id=None,
                product_group="other",
                amount_tier=None,
                installment_count=installment,
                commission_percent=Decimal(5),
                scope_key=f"pos|-|other|-|{installment}",
            )
        )
    product = Product(
        id=uuid.uuid4(),
        name="Buzdolabı",
        name_normalized="buzdolabı",
        regular_price=Decimal("10000.00"),
        cost_price=Decimal("8000.00"),
        physical_stock=1,
    )
    uow.products.add(product)
    return uow, product.id


def test_card_offer_can_be_saved_without_bank() -> None:
    uow, product_id = _active_card_uow()
    offer_id = create_offer(
        uow,
        OfferInput(
            customer_name="Ayşe",
            customer_phone=None,
            payment_type=PaymentType.CARD,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product_id, 1),),
            channel=PaymentChannel.POS,
            installment_count=2,
            card_type=CardType.CONSUMER,
        ),
    )
    offer = uow.offers.get(offer_id)

    assert offer is not None
    assert offer.bank_id is None
    assert offer.bank_name_snapshot is None
    assert offer.commission_source == "general"
    assert offer.commission_percent_snapshot == Decimal(5)


def test_card_offer_snapshots_bank_name() -> None:
    bank_id = uuid.uuid4()
    uow, product_id = _active_card_uow(bank_id=bank_id)
    offer_id = create_offer(
        uow,
        OfferInput(
            customer_name="Ayşe",
            customer_phone=None,
            payment_type=PaymentType.CARD,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product_id, 1),),
            channel=PaymentChannel.POS,
            bank_id=bank_id,
            installment_count=2,
            card_type=CardType.CONSUMER,
        ),
    )
    offer = uow.offers.get(offer_id)

    assert offer is not None
    assert offer.bank_name_snapshot == "Akbank"
    assert offer.commission_source == "general"



def test_create_cash_offer_and_status_history() -> None:
    uow = FakeUnitOfWork()
    product = Product(
        id=uuid.uuid4(),
        name="Buzdolabı",
        name_normalized="buzdolabı",
        regular_price=Decimal("50000.00"),
        website_discounted_price=Decimal("46000.00"),
        cost_price=Decimal("36000.00"),
        physical_stock=1,
    )
    uow.products.add(product)

    offer_id = create_offer(
        uow,
        OfferInput(
            customer_name="Ayşe Yılmaz",
            customer_phone="555",
            payment_type=PaymentType.CASH,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product.id, 1),),
        ),
    )
    detail = get_offer_detail(uow, offer_id)

    assert detail is not None
    assert detail.offer.status == OfferStatus.DRAFT.value
    assert detail.items[0].unit_price_cash == Decimal("41400.00")
    assert detail.offer.selected_total == Decimal("41400.00")

    set_offer_status(uow, offer_id, OfferStatus.PRESENTED.value)
    set_offer_status(uow, offer_id, OfferStatus.ACCEPTED.value)
    reservation_id = convert_offer_to_reservation(uow, offer_id)
    retry_id = convert_offer_to_reservation(uow, offer_id)

    assert retry_id == reservation_id
    detail = get_offer_detail(uow, offer_id)
    assert detail is not None
    assert detail.offer.converted_reservation_id == reservation_id


def test_presented_offer_cannot_be_updated() -> None:
    uow = FakeUnitOfWork()
    product = Product(
        id=uuid.uuid4(),
        name="Fırın",
        name_normalized="fırın",
        regular_price=Decimal("10000.00"),
        physical_stock=1,
    )
    uow.products.add(product)
    data = OfferInput(
        customer_name="Ayşe",
        customer_phone=None,
        payment_type=PaymentType.CASH,
        dealer_discount_percent=Decimal(10),
        items=(OfferItemInput(product.id, 1),),
    )
    offer_id = create_offer(uow, data)
    set_offer_status(uow, offer_id, OfferStatus.PRESENTED.value)

    with pytest.raises(ValidationError, match="taslak"):
        update_offer(uow, offer_id, data)


def test_line_analysis_shows_commission_and_campaign_share() -> None:
    offer = Offer(
        id=uuid.uuid4(),
        payment_type="card",
        installment_count=10,
        commission_percent_snapshot=Decimal(10),
        commission_options_snapshot=[{"installment": 10, "percent": "10"}],
        dealer_share_percent_snapshot=Decimal(85),
    )
    item = OfferItem(
        id=uuid.uuid4(),
        offer_id=offer.id,
        product_name_snapshot="Klima",
        quantity=1,
        regular_price_snapshot=Decimal(49000),
        cost_price_snapshot=Decimal(52000),
        unit_price_card=Decimal(49000),
        dealer_discount_percent=Decimal(10),
        campaign_name_snapshot="Düğün",
        campaign_snapshot={"discount_type": "percent", "discount_value": "10"},
        position=0,
    )

    analysis = build_offer_line_analyses(
        OfferDetail(offer=offer, items=(item,), history=())
    )
    row = analysis[0].installments[0]

    assert row.commission_percent == Decimal(10)
    assert row.net_after_commission == Decimal("44100.00")
    assert row.campaign_share == Decimal("4165.00")
    assert row.total_revenue == Decimal("48265.00")
    assert row.profit == Decimal("-3735.00")


def test_campaign_discount_is_not_dealer_discount_applied_twice() -> None:
    from bayios.application.offers import build_offer_profit_summary

    uow = FakeUnitOfWork()
    product = Product(
        id=uuid.uuid4(),
        name="Klima",
        name_normalized="klima",
        regular_price=Decimal("10000.00"),
        cost_price=Decimal("8000.00"),
        physical_stock=1,
    )
    uow.products.add(product)
    now = datetime.now(UTC)
    create_campaign(
        uow,
        CampaignInput(
            name="Yüzde 20",
            campaign_type=CampaignType.PRODUCT_DISCOUNT,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=30),
            base_price_type=BasePriceType.REGULAR,
            discount_type=DiscountType.PERCENT,
            discount_value=Decimal(20),
            products=(
                CampaignProductInput(product.id, ProductRelationType.BENEFIT),
            ),
        ),
    )

    offer_id = create_offer(
        uow,
        OfferInput(
            customer_name="Kampanya",
            customer_phone=None,
            payment_type=PaymentType.CASH,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product.id, 1, auto_campaign=True),),
        ),
    )
    detail = get_offer_detail(uow, offer_id)
    assert detail is not None
    assert detail.offer.pricing_version == "v2"
    assert detail.offer.regular_total == Decimal("10000.00")
    assert detail.offer.company_discount_total == Decimal("2000.00")
    assert detail.offer.cost_total == Decimal("8000.00")
    item = detail.items[0]
    assert item.company_discount_source == "campaign"
    assert item.company_discount_amount == Decimal("2000.00")
    assert item.company_share_amount == Decimal("2000.00")
    assert item.base_price_used == Decimal("8000.00")
    assert item.unit_price_cash == Decimal("7200.00")
    assert item.campaign_snapshot["campaign_discount_amount"] == "2000.00"

    summary = build_offer_profit_summary(detail)
    line = summary.lines[0]
    assert line.campaign_share == Decimal("1700.00")
    assert line.total_revenue == Decimal("8900.00")
    assert line.profit == Decimal("900.00")


def test_offer_auto_assigns_active_campaign() -> None:
    uow = FakeUnitOfWork()
    product = Product(
        id=uuid.uuid4(),
        name="Klima",
        name_normalized="klima",
        regular_price=Decimal("10000.00"),
        cost_price=Decimal("8000.00"),
        physical_stock=1,
    )
    uow.products.add(product)
    now = datetime.now(UTC)
    create_campaign(
        uow,
        CampaignInput(
            name="Düğün",
            campaign_type=CampaignType.PRODUCT_DISCOUNT,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=30),
            base_price_type=BasePriceType.REGULAR,
            discount_type=DiscountType.PERCENT,
            discount_value=Decimal(10),
            products=(
                CampaignProductInput(
                    product.id, ProductRelationType.BENEFIT
                ),
            ),
        ),
    )

    offer_id = create_offer(
        uow,
        OfferInput(
            customer_name="Ayşe",
            customer_phone=None,
            payment_type=PaymentType.CASH,
            dealer_discount_percent=Decimal(10),
            items=(
                OfferItemInput(
                    product.id, 1, auto_campaign=True
                ),
            ),
        ),
    )
    detail = get_offer_detail(uow, offer_id)

    assert detail is not None
    assert detail.items[0].campaign_snapshot is not None
    assert detail.items[0].campaign_name_snapshot == "Düğün"


def _quick_offer_fixture(stock: int = 5, quantity: int = 2):
    uow = FakeUnitOfWork()
    product = Product(
        id=uuid.uuid4(),
        name="Buzdolabı",
        name_normalized="buzdolabı",
        regular_price=Decimal("50000.00"),
        cost_price=Decimal("36000.00"),
        physical_stock=stock,
    )
    uow.products.add(product)
    offer_id = create_offer(
        uow,
        OfferInput(
            customer_name="Ayşe",
            customer_phone=None,
            payment_type=PaymentType.CASH,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product.id, quantity),),
        ),
    )
    return uow, product, offer_id


def test_reserve_offer_is_quick_and_idempotent() -> None:
    from bayios.application.offers import reserve_offer

    uow, product, offer_id = _quick_offer_fixture()
    reservation_id = reserve_offer(uow, offer_id)
    retry_id = reserve_offer(uow, offer_id)

    assert retry_id == reservation_id
    detail = get_offer_detail(uow, offer_id)
    assert detail is not None
    assert detail.offer.status == OfferStatus.ACCEPTED.value
    assert detail.offer.converted_reservation_id == reservation_id
    reservation = uow.reservations.get(reservation_id)
    assert reservation is not None
    assert len(uow.reservations.get_items(reservation_id)) == 1
    assert product.physical_stock == 5


def test_sell_offer_delivers_all_lines_and_reduces_stock() -> None:
    from bayios.application.offers import sell_offer

    uow, product, offer_id = _quick_offer_fixture(stock=5, quantity=2)
    reservation_id = sell_offer(uow, offer_id)
    retry_id = sell_offer(uow, offer_id)

    assert retry_id == reservation_id
    assert product.physical_stock == 3
    lines = uow.reservations.get_items(reservation_id)
    assert len(lines) == 1
    assert lines[0].delivered_quantity == 2
    assert lines[0].status == "delivered"
    assert len(uow.products.get_stock_movements(product.id)) == 1


def test_sell_offer_requires_reason_when_stock_is_insufficient() -> None:
    from bayios.application.offers import sell_offer

    uow, product, offer_id = _quick_offer_fixture(stock=1, quantity=2)
    with pytest.raises(ValidationError, match="gerekçe"):
        sell_offer(uow, offer_id)

    reservation_id = sell_offer(
        uow, offer_id, low_stock_reason="Müşteriye özel sipariş"
    )
    assert product.physical_stock == -1
    lines = uow.reservations.get_items(reservation_id)
    assert lines[0].delivered_quantity == 2


def _campaign_fixture(regular: Decimal, oliz: Decimal, percent: Decimal):
    uow = FakeUnitOfWork()
    product = Product(
        id=uuid.uuid4(),
        name="Klima",
        name_normalized="klima",
        regular_price=regular,
        website_discounted_price=oliz,
        cost_price=Decimal("30000.00"),
        physical_stock=1,
    )
    uow.products.add(product)
    now = datetime.now(UTC)
    create_campaign(
        uow,
        CampaignInput(
            name="Düğün",
            campaign_type=CampaignType.PRODUCT_DISCOUNT,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=30),
            base_price_type=BasePriceType.REGULAR,
            discount_type=DiscountType.PERCENT,
            discount_value=percent,
            products=(
                CampaignProductInput(product.id, ProductRelationType.BENEFIT),
            ),
        ),
    )
    return uow, product


def test_auto_campaign_chooses_campaign_when_it_beats_oliz() -> None:
    uow, product = _campaign_fixture(
        Decimal("50000.00"), Decimal("46000.00"), Decimal(10)
    )
    offer_id = create_offer(
        uow,
        OfferInput(
            customer_name="Otomatik",
            customer_phone=None,
            payment_type=PaymentType.CASH,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product.id, 1, auto_campaign=True),),
        ),
    )
    detail = get_offer_detail(uow, offer_id)
    assert detail is not None
    item = detail.items[0]
    assert item.company_discount_source == "campaign"
    assert item.base_price_used == Decimal("45000.00")
    assert item.unit_price_cash == Decimal("40500.00")
    assert item.company_share_amount == Decimal("5000.00")


def test_auto_campaign_chooses_oliz_when_it_beats_campaign() -> None:
    uow, product = _campaign_fixture(
        Decimal("50000.00"), Decimal("40000.00"), Decimal(10)
    )
    offer_id = create_offer(
        uow,
        OfferInput(
            customer_name="Otomatik",
            customer_phone=None,
            payment_type=PaymentType.CASH,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product.id, 1, auto_campaign=True),),
        ),
    )
    detail = get_offer_detail(uow, offer_id)
    assert detail is not None
    item = detail.items[0]
    assert item.company_discount_source == "oliz"
    assert item.base_price_used == Decimal("40000.00")
    assert item.unit_price_cash == Decimal("36000.00")
    assert item.website_price_snapshot == Decimal("40000.00")
    assert item.campaign_snapshot is None


def test_preview_offer_line_exposes_auto_campaign_preview() -> None:
    uow, product = _campaign_fixture(
        Decimal("50000.00"), Decimal("46000.00"), Decimal(10)
    )
    preview = preview_offer_line(
        uow,
        product.id,
        dealer_discount_percent=Decimal(10),
        dealer_discount_cash_percent=Decimal(10),
    )

    assert preview is not None
    assert preview.previews["auto"].campaign_name == "Düğün"
    assert preview.previews["auto"].price == Decimal("45000.00")
    assert preview.previews["auto"].discount_amount == Decimal("5000.00")


def test_manual_totals_override_selected_total_and_profit() -> None:
    uow, product_id = _active_card_uow()
    offer_id = create_offer(
        uow,
        OfferInput(
            customer_name="Manuel Toplam",
            customer_phone=None,
            payment_type=PaymentType.CASH,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product_id, 2),),
            cash_total_override=Decimal("15000.00"),
            card_total_override=Decimal("16000.00"),
        ),
    )
    offer = uow.offers.get(offer_id)
    assert offer is not None
    assert offer.cash_total == Decimal("15000.00")
    assert offer.card_total == Decimal("16000.00")
    assert offer.selected_total == Decimal("15000.00")
    assert offer.cash_total_override == Decimal("15000.00")
    assert offer.card_total_override == Decimal("16000.00")

    detail = get_offer_detail(uow, offer_id)
    assert detail is not None
    summary = build_offer_profit_summary(detail)
    assert summary.manual_adjustment == Decimal("0.00")
    assert summary.total_revenue == Decimal("15000.00")
    assert summary.total_profit == Decimal("-1000.00")
    item = uow.offers.get_items(offer_id)[0]
    assert item.unit_price_cash == Decimal("7500.00")
    assert item.unit_price_card == Decimal("8000.00")
    assert item.line_total_cash == Decimal("15000.00")
    assert item.line_total_card == Decimal("16000.00")

    update_offer(
        uow,
        offer_id,
        OfferInput(
            customer_name="Manuel Toplam",
            customer_phone=None,
            payment_type=PaymentType.CASH,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product_id, 2),),
        ),
    )
    refreshed = uow.offers.get(offer_id)
    assert refreshed is not None
    assert refreshed.cash_total_override is None
    assert refreshed.card_total_override is None
    assert refreshed.cash_total == Decimal("18000.00")
    assert refreshed.selected_total == Decimal("18000.00")


def test_manual_totals_reject_negative_values() -> None:
    uow, product_id = _active_card_uow()
    with pytest.raises(ValidationError):
        create_offer(
            uow,
            OfferInput(
                customer_name="Negatif",
                customer_phone=None,
                payment_type=PaymentType.CASH,
                dealer_discount_percent=Decimal(10),
                items=(OfferItemInput(product_id, 1),),
                cash_total_override=Decimal(-1),
            ),
        )


def test_comparison_uses_manual_card_total_for_monthly_payment() -> None:
    uow, product_id = _active_card_uow()
    comparison = preview_offer_comparison(
        uow,
        OfferInput(
            customer_name="Kart",
            customer_phone=None,
            payment_type=PaymentType.CARD,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product_id, 1),),
            channel=PaymentChannel.POS,
            installment_count=2,
            card_type=CardType.CONSUMER,
            card_total_override=Decimal("12000.00"),
        ),
    )

    assert comparison.card_total == Decimal("12000.00")
    option = next(
        row for row in comparison.options if row.installment_count == 2
    )
    assert option.card_total == Decimal("12000.00")
    assert option.monthly_payment == Decimal("6000.00")


def test_manual_totals_are_split_across_multiple_lines() -> None:
    uow = FakeUnitOfWork()
    first = Product(
        id=uuid.uuid4(),
        name="07325 A",
        name_normalized="07325 a",
        regular_price=Decimal("38099.00"),
        cost_price=Decimal("30000.00"),
        physical_stock=1,
    )
    second = Product(
        id=uuid.uuid4(),
        name="09325 A",
        name_normalized="09325 a",
        regular_price=Decimal("42199.00"),
        cost_price=Decimal("34000.00"),
        physical_stock=1,
    )
    uow.products.add(first)
    uow.products.add(second)
    offer_id = create_offer(
        uow,
        OfferInput(
            customer_name="Paket",
            customer_phone=None,
            payment_type=PaymentType.CASH,
            dealer_discount_percent=Decimal(10),
            items=(
                OfferItemInput(first.id, 1),
                OfferItemInput(second.id, 1),
            ),
            cash_total_override=Decimal("59000.00"),
            card_total_override=Decimal("61000.00"),
        ),
    )
    items = uow.offers.get_items(offer_id)
    assert [item.unit_price_cash for item in items] == [
        Decimal("27993.74"),
        Decimal("31006.26"),
    ]
    assert [item.unit_price_card for item in items] == [
        Decimal("28942.68"),
        Decimal("32057.32"),
    ]
    assert sum((item.line_total_cash for item in items), Decimal(0)) == Decimal(
        "59000.00"
    )
    assert sum((item.line_total_card for item in items), Decimal(0)) == Decimal(
        "61000.00"
    )
    detail = get_offer_detail(uow, offer_id)
    assert detail is not None
    assert build_offer_profit_summary(detail).manual_adjustment == Decimal("0.00")
