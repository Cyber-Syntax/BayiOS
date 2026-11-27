from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from bayios.adapters.db.models.products import Product, ProductCategory
from bayios.application.campaigns import (
    CampaignInput,
    CampaignProductInput,
    create_campaign,
)
from bayios.application.offers import (
    OfferInput,
    OfferItemInput,
    _prepare_items,
    create_offer,
    get_offer_detail,
)
from bayios.domain.campaigns import (
    BasePriceType,
    CampaignType,
    DiscountType,
    ProductRelationType,
)
from bayios.domain.offers import PaymentType
from tests.fakes import FakeUnitOfWork

NOW = datetime.now(UTC)


def _setup() -> tuple[FakeUnitOfWork, dict[str, uuid.UUID]]:
    uow = FakeUnitOfWork()
    categories = {
        "fridge": ProductCategory(
            id=uuid.uuid4(),
            name="Buzdolabı",
            name_normalized="buzdolabi",
            commission_group="other",
        ),
        "wash": ProductCategory(
            id=uuid.uuid4(),
            name="Çamaşır Makinesi",
            name_normalized="camasir makinesi",
            commission_group="other",
        ),
        "dish": ProductCategory(
            id=uuid.uuid4(),
            name="Bulaşık Makinesi",
            name_normalized="bulasik makinesi",
            commission_group="other",
        ),
        "dryer": ProductCategory(
            id=uuid.uuid4(),
            name="Kurutma Makinesi",
            name_normalized="kurutma makinesi",
            commission_group="other",
        ),
        "klima": ProductCategory(
            id=uuid.uuid4(),
            name="Klima",
            name_normalized="klima",
            commission_group="klima",
        ),
    }
    for category in categories.values():
        uow.products.add_category(category)
    products = {
        "p1": Product(
            id=uuid.uuid4(),
            name="383510 EI",
            name_normalized="383510 ei",
            regular_price=Decimal("89799.00"),
            website_discounted_price=Decimal("86299.00"),
            physical_stock=1,
            category_id=categories["fridge"].id,
        ),
        "p2": Product(
            id=uuid.uuid4(),
            name="12142 A",
            name_normalized="12142 a",
            regular_price=Decimal("47599.00"),
            physical_stock=1,
            category_id=categories["wash"].id,
        ),
        "p3": Product(
            id=uuid.uuid4(),
            name="A 811 i sd",
            name_normalized="a 811 i sd",
            regular_price=Decimal("46499.00"),
            website_discounted_price=Decimal("41499.00"),
            physical_stock=1,
            category_id=categories["dish"].id,
        ),
        "p4": Product(
            id=uuid.uuid4(),
            name="802 KMX",
            name_normalized="802 kmx",
            regular_price=Decimal("35699.00"),
            physical_stock=1,
            category_id=categories["dryer"].id,
        ),
    }
    for product in products.values():
        uow.products.add(product)

    create_campaign(
        uow,
        CampaignInput(
            name="Düğün",
            campaign_type=CampaignType.PRODUCT_DISCOUNT,
            starts_at=NOW - timedelta(days=1),
            ends_at=NOW + timedelta(days=30),
            base_price_type=BasePriceType.REGULAR,
            discount_type=DiscountType.PERCENT,
            discount_value=Decimal(10),
            products=tuple(
                CampaignProductInput(
                    products[key].id, ProductRelationType.RELATED
                )
                for key in ("p1", "p2", "p3")
            ),
        ),
    )
    create_campaign(
        uow,
        CampaignInput(
            name="Kurutma / Klima",
            campaign_type=CampaignType.BUNDLE,
            starts_at=NOW - timedelta(days=1),
            ends_at=NOW + timedelta(days=30),
            base_price_type=BasePriceType.REGULAR,
            discount_type=DiscountType.FIXED_AMOUNT,
            discount_value=Decimal(17850),
            combines_with_others=False,
            products=(
                CampaignProductInput(products["p1"].id, ProductRelationType.QUALIFYING),
                CampaignProductInput(products["p2"].id, ProductRelationType.QUALIFYING),
                CampaignProductInput(products["p3"].id, ProductRelationType.QUALIFYING),
                CampaignProductInput(
                    category_id=categories["dryer"].id,
                    relation_type=ProductRelationType.BENEFIT,
                    discount_type=DiscountType.FIXED_AMOUNT,
                    discount_value=Decimal(17850),
                    base_price_type=BasePriceType.REGULAR,
                    applies_per_unit=False,
                ),
                CampaignProductInput(
                    category_id=categories["klima"].id,
                    relation_type=ProductRelationType.BENEFIT,
                    discount_type=DiscountType.FIXED_AMOUNT,
                    discount_value=Decimal(19200),
                    base_price_type=BasePriceType.REGULAR,
                    applies_per_unit=False,
                ),
            ),
        ),
    )
    return uow, {key: product.id for key, product in products.items()}


def _offer_input(ids: dict[str, uuid.UUID], keys: tuple[str, ...]) -> OfferInput:
    return OfferInput(
        customer_name="POS testi",
        customer_phone=None,
        payment_type=PaymentType.CASH,
        dealer_discount_percent=Decimal(10),
        items=tuple(
            OfferItemInput(ids[key], 1, auto_campaign=True) for key in keys
        ),
    )


def test_basket_without_dryer_matches_pos_total() -> None:
    uow, ids = _setup()
    with uow:
        prepared = _prepare_items(uow, _offer_input(ids, ("p1", "p2", "p3")))
    discounts = {
        item.product.name: item.company.discount_amount
        for item in prepared
        if item.company is not None
    }
    assert discounts == {
        "383510 EI": Decimal("8979.90"),
        "12142 A": Decimal("4759.90"),
        "A 811 i sd": Decimal("5000.00"),
    }
    assert sum(discounts.values()) == Decimal("18739.80")


def test_basket_with_dryer_matches_pos_split() -> None:
    uow, ids = _setup()
    with uow:
        prepared = _prepare_items(
            uow, _offer_input(ids, ("p1", "p2", "p3", "p4"))
        )
    by_name = {
        item.product.name: item
        for item in prepared
    }
    assert by_name["383510 EI"].company.discount_amount == Decimal("8979.90")
    assert by_name["12142 A"].company.discount_amount == Decimal("10200.03")
    assert by_name["A 811 i sd"].company.source.value == "oliz"
    assert by_name["A 811 i sd"].company.discount_amount == Decimal("5000.00")
    assert by_name["802 KMX"].company.discount_amount == Decimal("7649.97")
    assert by_name["12142 A"].campaign_snapshot["is_flat_allocation"] is True
    assert by_name["802 KMX"].campaign_snapshot["is_flat_allocation"] is True
    total = sum(
        item.company.discount_amount
        for item in prepared
        if item.company is not None
    )
    assert total == Decimal("31829.90")


def test_saved_offer_keeps_basket_snapshot() -> None:
    uow, ids = _setup()
    offer_id = create_offer(
        uow, _offer_input(ids, ("p1", "p2", "p3", "p4"))
    )
    detail = get_offer_detail(uow, offer_id)
    assert detail is not None
    assert detail.offer.company_discount_total == Decimal("31829.90")
    assert detail.offer.regular_total == Decimal("219596.00")
    items = {
        item.product_name_snapshot: item for item in detail.items
    }
    assert items["12142 A"].campaign_discount_amount == Decimal("10200.03")
    assert items["802 KMX"].campaign_discount_amount == Decimal("7649.97")
    assert items["383510 EI"].campaign_name_snapshot == "Düğün"
