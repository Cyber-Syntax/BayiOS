from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from bayios.adapters.db.models.products import Product
from bayios.application.campaigns import (
    CampaignInput,
    CampaignProductInput,
    create_campaign,
)
from bayios.application.offers import (
    OfferInput,
    OfferItemInput,
    create_offer,
    get_offer_detail,
)
from bayios.domain.campaigns import (
    CampaignType,
    DiscountType,
    ProductRelationType,
)
from bayios.domain.offers import PaymentType
from tests.fakes import FakeUnitOfWork

NOW = datetime.now(UTC)


def _uow() -> tuple[FakeUnitOfWork, uuid.UUID, uuid.UUID]:
    uow = FakeUnitOfWork()
    buyer = Product(
        id=uuid.uuid4(),
        name="Buzdolabı",
        name_normalized="buzdolabi",
        regular_price=Decimal("150000.00"),
        physical_stock=1,
    )
    gift = Product(
        id=uuid.uuid4(),
        name="CM 3626 IC",
        name_normalized="cm 3626 ic",
        regular_price=Decimal("4699.00"),
        website_discounted_price=Decimal("3899.00"),
        cost_price=Decimal("3000.00"),
        physical_stock=1,
    )
    uow.products.add(buyer)
    uow.products.add(gift)
    return uow, buyer.id, gift.id


def _gift_campaign(
    uow: FakeUnitOfWork,
    gift_id: uuid.UUID,
    *,
    min_total: Decimal = Decimal(100000),
    optional: bool = False,
    gift_price: Decimal | None = None,
) -> None:
    create_campaign(
        uow,
        CampaignInput(
            name="Çay Makinesi Hediye",
            campaign_type=CampaignType.GENERAL,
            starts_at=NOW - timedelta(days=1),
            ends_at=NOW + timedelta(days=30),
            discount_type=DiscountType.INFO_ONLY,
            gift_description="CM 3626 IC" if optional else None,
            gift_optional=optional,
            min_basket_total=min_total,
            products=(
                CampaignProductInput(
                    gift_id,
                    ProductRelationType.GIFT,
                    gift_price=gift_price,
                ),
            ),
        ),
    )


def _offer_input(
    buyer_id: uuid.UUID, *, gift_present: bool | None = None
) -> OfferInput:
    return OfferInput(
        customer_name="Hediye Testi",
        customer_phone=None,
        payment_type=PaymentType.CASH,
        dealer_discount_percent=Decimal(0),
        dealer_discount_cash_percent=Decimal(0),
        items=(
            OfferItemInput(
                buyer_id, 1, auto_campaign=True, gift_present=gift_present
            ),
        ),
    )


def test_gift_line_is_added_when_basket_minimum_is_met() -> None:
    uow, buyer_id, gift_id = _uow()
    _gift_campaign(uow, gift_id)
    offer_id = create_offer(uow, _offer_input(buyer_id))
    detail = get_offer_detail(uow, offer_id)
    assert detail is not None
    gift_items = [
        item
        for item in detail.items
        if (item.campaign_snapshot or {}).get("is_gift")
    ]
    assert len(gift_items) == 1
    item = gift_items[0]
    assert item.product_id == gift_id
    assert item.quantity == 1
    assert item.unit_price_cash == Decimal("800.00")
    assert item.unit_price_card == Decimal("800.00")
    assert item.line_total_cash == Decimal("800.00")
    assert item.website_price_snapshot == Decimal("3899.00")
    assert item.company_discount_source == "oliz"
    assert item.company_discount_amount == Decimal("800.00")
    assert item.company_share_amount == Decimal("800.00")
    assert item.warning_text == "Hediye ürün"
    assert detail.offer.company_discount_total == Decimal("800.00")
    assert detail.offer.cash_total == Decimal("150800.00")


def test_explicit_gift_price_overrides_oliz_discount() -> None:
    uow, buyer_id, gift_id = _uow()
    _gift_campaign(uow, gift_id, gift_price=Decimal("1000.00"))
    offer_id = create_offer(uow, _offer_input(buyer_id))
    detail = get_offer_detail(uow, offer_id)
    assert detail is not None
    gift = next(
        item
        for item in detail.items
        if (item.campaign_snapshot or {}).get("is_gift")
    )
    assert gift.unit_price_cash == Decimal("1000.00")
    assert gift.line_total_cash == Decimal("1000.00")
    assert gift.company_discount_amount == Decimal("1000.00")


def test_gift_is_not_added_below_basket_minimum() -> None:
    uow, buyer_id, gift_id = _uow()
    _gift_campaign(uow, gift_id)
    uow.products.products[buyer_id].regular_price = Decimal("90000.00")
    offer_id = create_offer(uow, _offer_input(buyer_id))
    detail = get_offer_detail(uow, offer_id)
    assert detail is not None
    assert all(
        not (item.campaign_snapshot or {}).get("is_gift")
        for item in detail.items
    )


def test_optional_gift_can_be_declined() -> None:
    uow, buyer_id, gift_id = _uow()
    _gift_campaign(uow, gift_id, optional=True)
    offer_id = create_offer(uow, _offer_input(buyer_id, gift_present=False))
    detail = get_offer_detail(uow, offer_id)
    assert detail is not None
    assert all(
        not (item.campaign_snapshot or {}).get("is_gift")
        for item in detail.items
    )
