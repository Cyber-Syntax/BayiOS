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
    convert_offer_to_reservation,
    create_offer,
    get_offer_detail,
    set_offer_status,
    update_offer,
)
from bayios.domain.campaigns import (
    BasePriceType,
    CampaignType,
    DiscountType,
    ProductRelationType,
)
from bayios.domain.offers import OfferStatus, PaymentType
from tests.fakes import FakeUnitOfWork


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
