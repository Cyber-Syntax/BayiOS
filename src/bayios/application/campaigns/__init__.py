from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal

from bayios.adapters.db.models.campaigns import (
    Campaign,
    CampaignVersion,
    CampaignVersionProduct,
    DealerPricing,
)
from bayios.adapters.db.models.products import Product
from bayios.application.errors import NotFoundError, ValidationError
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.domain.campaigns import (
    BASE_PRICE_TYPE_LABELS,
    CAMPAIGN_STATE_LABELS,
    CAMPAIGN_TYPE_LABELS,
    DISCOUNT_TYPE_LABELS,
    PRODUCT_RELATION_TYPE_LABELS,
    BasePriceType,
    CampaignContract,
    CampaignPaymentCondition,
    CampaignPriceInput,
    CampaignProductLink,
    CampaignScenario,
    CampaignState,
    CampaignType,
    DiscountType,
    ProductRelationType,
    campaign_scenarios,
    classify_campaign,
    is_same_contract,
    next_version_no,
)
from bayios.domain.commissions import (
    CARD_TYPE_LABELS,
    CHANNEL_LABELS,
    CardType,
    PaymentChannel,
)
from bayios.domain.dealer_pricing import (
    DEFAULT_DEALER_DISCOUNT_PERCENT,
    validate_dealer_percent,
)
from bayios.domain.products import ActorContext


@dataclass(frozen=True)
class CampaignProductInput:
    product_id: uuid.UUID | None = None
    relation_type: ProductRelationType = ProductRelationType.RELATED
    quantity_required: int | None = None
    category_id: uuid.UUID | None = None
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = None
    base_price_type: BasePriceType | None = None
    applies_per_unit: bool | None = None
    gift_price: Decimal | None = None


@dataclass(frozen=True)
class CampaignInput:
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
    combines_with_others: bool = True
    exclusion_group: str | None = None
    min_basket_total: Decimal | None = None
    payment_conditions: tuple[CampaignPaymentCondition, ...] = ()
    external_id: str | None = None
    source_url: str | None = None
    conditions: tuple[str, ...] = ()
    source_category: str | None = None
    source_product_count: int | None = None
    scraped_at: datetime | None = None
    products: tuple[CampaignProductInput, ...] = ()


@dataclass(frozen=True)
class CampaignProductView:
    product_id: uuid.UUID | None
    product_name: str
    relation_type: str
    relation_label: str
    quantity_required: int | None
    category_id: uuid.UUID | None = None
    target_type: str = "product"
    discount_type: str | None = None
    discount_type_label: str | None = None
    discount_value: Decimal | None = None
    base_price_type: str | None = None
    applies_per_unit: bool | None = None
    gift_price: Decimal | None = None


@dataclass(frozen=True)
class CampaignVersionView:
    id: uuid.UUID
    version_no: int
    name: str
    description: str | None
    campaign_type: str
    campaign_type_label: str
    starts_at: datetime
    ends_at: datetime
    state: str
    state_label: str
    base_price_type: str
    base_price_type_label: str
    discount_type: str
    discount_type_label: str
    discount_value: Decimal | None
    gift_description: str | None
    gift_optional: bool
    gift_yes_base_price_type: str | None
    gift_no_base_price_type: str | None
    employee_note: str | None
    combines_with_others: bool
    exclusion_group: str | None
    min_basket_total: Decimal | None
    payment_conditions: tuple[dict[str, object], ...]
    conditions: tuple[str, ...]
    source_category: str | None
    source_product_count: int | None
    scraped_at: datetime | None
    created_at: datetime | None
    created_by_name: str | None
    products: tuple[CampaignProductView, ...]


@dataclass(frozen=True)
class CampaignListItem:
    id: uuid.UUID
    name: str
    description: str | None
    campaign_type: str
    campaign_type_label: str
    starts_at: datetime
    ends_at: datetime
    state: str
    state_label: str
    is_archived: bool
    discount_type: str
    discount_type_label: str
    discount_value: Decimal | None
    gift_description: str | None
    product_count: int


@dataclass(frozen=True)
class CampaignDetail:
    id: uuid.UUID
    external_id: str | None
    source_url: str | None
    is_archived: bool
    state: str
    state_label: str
    current_version: CampaignVersionView
    versions: tuple[CampaignVersionView, ...]
    selected_product_id: uuid.UUID | None
    selected_product_name: str | None
    dealer_percent: Decimal
    price_input: CampaignPriceInput | None
    scenarios: tuple[CampaignScenario, ...]


@dataclass(frozen=True)
class ProductCampaignView:
    campaign_id: uuid.UUID
    campaign_name: str
    version_no: int
    starts_at: datetime
    ends_at: datetime
    state: str
    state_label: str
    relation_label: str
    discount_type: str
    discount_type_label: str
    discount_value: Decimal | None
    gift_description: str | None
    scenarios: tuple[CampaignScenario, ...]


def create_campaign(
    uow: UnitOfWork,
    data: CampaignInput,
    actor: ActorContext | None = None,
) -> uuid.UUID:
    actor = actor or ActorContext()
    now = datetime.now(UTC)
    with uow:
        campaign = create_campaign_in_uow(uow, data, actor=actor, now=now)
        uow.commit()
        return campaign.id


def create_campaign_in_uow(
    uow: UnitOfWork,
    data: CampaignInput,
    *,
    actor: ActorContext,
    now: datetime,
) -> Campaign:
    """Create a campaign inside an active unit of work; the caller commits."""
    contract = _build_contract(uow, data)
    campaign = Campaign(
        id=uuid.uuid4(),
        external_id=data.external_id,
        source_url=data.source_url,
        is_archived=False,
        created_at=now,
        updated_at=now,
        created_by_name=actor.worker_name,
        created_by_device=actor.device_name,
    )
    uow.campaigns.add(campaign)
    version = _version_row(
        contract,
        campaign.id,
        1,
        actor,
        now,
        scraped_at=data.scraped_at,
    )
    uow.campaigns.add_version(version)
    uow.campaigns.add_version_products(_link_rows(contract, version.id))
    uow.campaigns.set_current_version(campaign.id, version.id)
    return campaign


def update_campaign(
    uow: UnitOfWork,
    campaign_id: uuid.UUID,
    data: CampaignInput,
    actor: ActorContext | None = None,
) -> uuid.UUID:
    actor = actor or ActorContext()
    now = datetime.now(UTC)
    with uow:
        campaign, _changed = update_campaign_in_uow(
            uow, campaign_id, data, actor=actor, now=now
        )
        uow.commit()
        return campaign.id


def update_campaign_in_uow(
    uow: UnitOfWork,
    campaign_id: uuid.UUID,
    data: CampaignInput,
    *,
    actor: ActorContext,
    now: datetime,
) -> tuple[Campaign, bool]:
    """Update a campaign in an active unit of work; returns (campaign, changed)."""
    campaign = uow.campaigns.get_for_update(campaign_id)
    if campaign is None:
        raise NotFoundError("Kampanya bulunamadı.")
    current = uow.campaigns.get_current_version(campaign_id)
    if current is None:
        raise NotFoundError("Kampanya sürümü bulunamadı.")
    if data.external_id is not None:
        campaign.external_id = data.external_id
    if data.source_url is not None:
        campaign.source_url = data.source_url

    effective_data = data
    if not data.conditions and current.conditions:
        effective_data = replace(
            effective_data, conditions=tuple(current.conditions)
        )
    if data.source_category is None:
        effective_data = replace(
            effective_data, source_category=current.source_category
        )
    if data.source_product_count is None:
        effective_data = replace(
            effective_data,
            source_product_count=current.source_product_count,
        )
    if data.scraped_at is None:
        effective_data = replace(
            effective_data, scraped_at=current.scraped_at
        )

    contract = _build_contract(uow, effective_data)
    current_links = uow.campaigns.get_version_products(current.id)
    current_contract = _contract_from_row(current, current_links)
    if is_same_contract(current_contract, contract):
        return campaign, False

    version = _version_row(
        contract,
        campaign.id,
        next_version_no(current.version_no),
        actor,
        now,
        scraped_at=effective_data.scraped_at,
    )
    uow.campaigns.add_version(version)
    uow.campaigns.add_version_products(_link_rows(contract, version.id))
    uow.campaigns.set_current_version(campaign.id, version.id)
    return campaign, True


def archive_campaign(
    uow: UnitOfWork,
    campaign_id: uuid.UUID,
    *,
    archived: bool = True,
) -> uuid.UUID:
    with uow:
        campaign = uow.campaigns.get_for_update(campaign_id)
        if campaign is None:
            raise NotFoundError("Kampanya bulunamadı.")
        uow.campaigns.set_archived(campaign.id, archived)
        uow.commit()
        return campaign.id


def list_campaigns(
    uow: UnitOfWork,
    *,
    query: str | None = None,
    campaign_type: CampaignType | str | None = None,
    state: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    now: datetime | None = None,
) -> tuple[tuple[CampaignListItem, ...], int]:
    reference = now or datetime.now(UTC)
    type_value = (
        campaign_type.value
        if isinstance(campaign_type, CampaignType)
        else campaign_type
    )
    with uow:
        rows, total = uow.campaigns.list(
            query=query,
            campaign_type=type_value,
            state=state,
            date_from=_ensure_utc(date_from) if date_from else None,
            date_to=_ensure_utc(date_to) if date_to else None,
            as_of=reference,
            limit=limit,
            offset=offset,
        )
        links_by_version = uow.campaigns.get_version_products_for_versions(
            [version.id for _, version in rows]
        )
        items = tuple(
            _list_item(
                campaign,
                version,
                links_by_version.get(version.id, ()),
                reference,
            )
            for campaign, version in rows
        )
        return items, total


def get_campaign_detail(
    uow: UnitOfWork,
    campaign_id: uuid.UUID,
    *,
    product_id: uuid.UUID | None = None,
    dealer_percent: Decimal | None = None,
    now: datetime | None = None,
) -> CampaignDetail | None:
    reference = now or datetime.now(UTC)
    with uow:
        campaign = uow.campaigns.get(campaign_id)
        if campaign is None:
            return None
        current = uow.campaigns.get_current_version(campaign_id)
        if current is None:
            return None

        versions = uow.campaigns.get_versions(campaign_id)
        links_by_version = uow.campaigns.get_version_products_for_versions(
            [version.id for version in versions]
        )
        current_links = links_by_version.get(current.id, ())
        percent = _effective_dealer_percent(uow, dealer_percent)
        selected_id = product_id or _first_product_id(current_links)
        selected_product = (
            uow.products.get_by_id(selected_id) if selected_id else None
        )
        pricing = (
            uow.dealer_pricing.get(selected_id) if selected_id else None
        )
        price_input = _price_input(selected_product, pricing)
        scenarios: tuple[CampaignScenario, ...] = ()
        contract = _contract_from_row(current, current_links)
        if price_input is not None and not contract.explicit_benefit_links:
            try:
                scenarios = campaign_scenarios(
                    contract,
                    price_input,
                    percent,
                )
            except ValueError as exc:
                raise ValidationError(
                    f"Kampanya senaryosu hesaplanamadı: {exc}"
                ) from exc

        state = _state(campaign, current, reference)
        return CampaignDetail(
            id=campaign.id,
            external_id=campaign.external_id,
            source_url=campaign.source_url,
            is_archived=campaign.is_archived,
            state=state.value,
            state_label=CAMPAIGN_STATE_LABELS[state],
            current_version=_version_view(
                campaign, current, current_links, reference
            ),
            versions=tuple(
                _version_view(
                    campaign,
                    version,
                    links_by_version.get(version.id, ()),
                    reference,
                )
                for version in versions
            ),
            selected_product_id=selected_id,
            selected_product_name=(
                selected_product.name if selected_product is not None else None
            ),
            dealer_percent=percent,
            price_input=price_input,
            scenarios=scenarios,
        )


def list_active_campaigns_for_product(
    uow: UnitOfWork,
    product_id: uuid.UUID,
    *,
    dealer_percent: Decimal | None = None,
    now: datetime | None = None,
) -> tuple[ProductCampaignView, ...]:
    reference = now or datetime.now(UTC)
    with uow:
        product = uow.products.get_by_id(product_id)
        if product is None:
            return ()
        pricing = uow.dealer_pricing.get(product_id)
        percent = _effective_dealer_percent(uow, dealer_percent)
        category_id = getattr(product, "category_id", None)
        rows = uow.campaigns.active_for_basket(
            [product_id],
            [category_id] if category_id is not None else [],
            as_of=reference,
        )
        if not rows:
            return ()

        version_ids = [version.id for _campaign, version in rows]
        links_by_version = uow.campaigns.get_version_products_for_versions(
            version_ids
        )
        price_input = _price_input(product, pricing)

        views: list[ProductCampaignView] = []
        for campaign, version in rows:
            version_links = links_by_version.get(version.id, ())
            matching_links = [
                link
                for link in version_links
                if link.product_id == product_id
                or (
                    category_id is not None
                    and getattr(link, "category_id", None) == category_id
                )
            ]
            if not matching_links:
                matching_links = list(version_links)
            contract = _contract_from_row(version, version_links)
            scenarios: tuple[CampaignScenario, ...] = ()
            if not contract.explicit_benefit_links:
                try:
                    scenarios = campaign_scenarios(
                        contract, price_input, percent
                    )
                except ValueError as exc:
                    raise ValidationError(
                        f"Kampanya senaryosu hesaplanamadı: {exc}"
                    ) from exc
            state = _state(campaign, version, reference)
            relation_labels = ", ".join(
                sorted(
                    {
                        PRODUCT_RELATION_TYPE_LABELS[
                            ProductRelationType(link.relation_type)
                        ]
                        for link in matching_links
                    }
                )
            )
            views.append(
                ProductCampaignView(
                    campaign_id=campaign.id,
                    campaign_name=version.name,
                    version_no=version.version_no,
                    starts_at=version.starts_at,
                    ends_at=version.ends_at,
                    state=state.value,
                    state_label=CAMPAIGN_STATE_LABELS[state],
                    relation_label=relation_labels,
                    discount_type=version.discount_type,
                    discount_type_label=DISCOUNT_TYPE_LABELS[
                        DiscountType(version.discount_type)
                    ],
                    discount_value=version.discount_value,
                    gift_description=version.gift_description,
                    scenarios=tuple(scenarios),
                )
            )

        views.sort(key=lambda view: (view.ends_at, view.campaign_name))
        return tuple(views)


def _build_contract(uow: UnitOfWork, data: CampaignInput) -> CampaignContract:
    product_ids = [
        item.product_id for item in data.products if item.product_id is not None
    ]
    category_ids = [
        item.category_id for item in data.products if item.category_id is not None
    ]
    products = (
        {product.id: product for product in uow.products.get_by_ids(product_ids)}
        if product_ids
        else {}
    )
    categories = (
        {
            category.id: category
            for category in uow.products.get_categories()
            if category.id in set(category_ids)
        }
        if category_ids
        else {}
    )
    missing_products = [
        product_id for product_id in product_ids if product_id not in products
    ]
    if missing_products:
        raise ValidationError("Seçilen ürünlerden bazıları bulunamadı.")
    missing_categories = [
        category_id
        for category_id in category_ids
        if category_id not in categories
    ]
    if missing_categories:
        raise ValidationError("Seçilen kategorilerden bazıları bulunamadı.")

    links = tuple(
        CampaignProductLink(
            product_id=(
                str(item.product_id) if item.product_id is not None else None
            ),
            category_id=(
                str(item.category_id) if item.category_id is not None else None
            ),
            product_name=(
                products[item.product_id].name
                if item.product_id is not None
                else categories[item.category_id].name
            ),
            relation_type=item.relation_type,
            quantity_required=item.quantity_required,
            discount_type=item.discount_type,
            discount_value=item.discount_value,
            base_price_type=item.base_price_type,
            applies_per_unit=item.applies_per_unit,
            gift_price=item.gift_price,
        )
        for item in data.products
        if item.product_id is not None or item.category_id is not None
    )
    try:
        return CampaignContract(
            name=data.name.strip(),
            campaign_type=data.campaign_type,
            starts_at=_ensure_utc(data.starts_at),
            ends_at=_ensure_utc(data.ends_at),
            base_price_type=data.base_price_type,
            description=_clean_text(data.description),
            discount_type=data.discount_type,
            discount_value=data.discount_value,
            gift_description=_clean_text(data.gift_description),
            gift_optional=data.gift_optional,
            gift_yes_base_price_type=data.gift_yes_base_price_type,
            gift_no_base_price_type=data.gift_no_base_price_type,
            employee_note=_clean_text(data.employee_note),
            combines_with_others=data.combines_with_others,
            exclusion_group=_clean_text(data.exclusion_group),
            min_basket_total=data.min_basket_total,
            payment_conditions=data.payment_conditions,
            conditions=tuple(
                condition.strip()
                for condition in data.conditions
                if condition and condition.strip()
            ),
            source_category=_clean_text(data.source_category),
            source_product_count=data.source_product_count,
            products=links,
        )
    except ValueError as exc:
        raise ValidationError(f"Kampanya bilgileri geçersiz: {exc}") from exc


def _version_row(
    contract: CampaignContract,
    campaign_id: uuid.UUID,
    version_no: int,
    actor: ActorContext,
    now: datetime,
    *,
    scraped_at: datetime | None = None,
) -> CampaignVersion:
    return CampaignVersion(
        id=uuid.uuid4(),
        campaign_id=campaign_id,
        version_no=version_no,
        name=contract.name,
        description=contract.description,
        campaign_type=contract.campaign_type.value,
        starts_at=contract.starts_at,
        ends_at=contract.ends_at,
        base_price_type=contract.base_price_type.value,
        discount_type=contract.discount_type.value,
        discount_value=contract.discount_value,
        gift_description=contract.gift_description,
        gift_optional=contract.gift_optional,
        gift_yes_base_price_type=(
            contract.gift_yes_base_price_type.value
            if contract.gift_yes_base_price_type is not None
            else None
        ),
        gift_no_base_price_type=(
            contract.gift_no_base_price_type.value
            if contract.gift_no_base_price_type is not None
            else None
        ),
        employee_note=contract.employee_note,
        combines_with_others=contract.combines_with_others,
        exclusion_group=contract.exclusion_group,
        min_basket_total=contract.min_basket_total,
        payment_conditions=(
            [
                {
                    "channel": condition.channel,
                    "bank_ids": list(condition.bank_ids),
                    "card_type": condition.card_type,
                    "card_network": condition.card_network,
                    "installment_count": condition.installment_count,
                }
                for condition in contract.payment_conditions
            ]
            or None
        ),
        conditions=list(contract.conditions) if contract.conditions else None,
        source_category=contract.source_category,
        source_product_count=contract.source_product_count,
        scraped_at=scraped_at,
        created_at=now,
        created_by_name=actor.worker_name,
        created_by_device=actor.device_name,
    )


def _link_rows(
    contract: CampaignContract, version_id: uuid.UUID
) -> tuple[CampaignVersionProduct, ...]:
    return tuple(
        CampaignVersionProduct(
            id=uuid.uuid4(),
            campaign_version_id=version_id,
            product_id=uuid.UUID(link.product_id) if link.product_id else None,
            category_id=(
                uuid.UUID(link.category_id) if link.category_id else None
            ),
            product_name_snapshot=link.product_name,
            relation_type=link.relation_type.value,
            quantity_required=link.quantity_required,
            discount_type=(
                link.discount_type.value if link.discount_type else None
            ),
            discount_value=link.discount_value,
            base_price_type=(
                link.base_price_type.value if link.base_price_type else None
            ),
            applies_per_unit=link.applies_per_unit,
            gift_price=link.gift_price,
        )
        for link in contract.products
    )


def _contract_from_row(
    version: CampaignVersion,
    links: Sequence[CampaignVersionProduct],
) -> CampaignContract:
    return CampaignContract(
        name=version.name,
        campaign_type=CampaignType(version.campaign_type),
        starts_at=version.starts_at,
        ends_at=version.ends_at,
        base_price_type=BasePriceType(version.base_price_type),
        description=version.description,
        discount_type=DiscountType(version.discount_type),
        discount_value=version.discount_value,
        gift_description=version.gift_description,
        gift_optional=version.gift_optional,
        gift_yes_base_price_type=(
            BasePriceType(version.gift_yes_base_price_type)
            if version.gift_yes_base_price_type
            else None
        ),
        gift_no_base_price_type=(
            BasePriceType(version.gift_no_base_price_type)
            if version.gift_no_base_price_type
            else None
        ),
        employee_note=version.employee_note,
        combines_with_others=(
            True
            if getattr(version, "combines_with_others", True) is None
            else bool(version.combines_with_others)
        ),
        exclusion_group=getattr(version, "exclusion_group", None),
        min_basket_total=getattr(version, "min_basket_total", None),
        payment_conditions=tuple(
            CampaignPaymentCondition(
                channel=_clean_text(condition.get("channel")),
                bank_ids=tuple(
                    str(bank_id)
                    for bank_id in (condition.get("bank_ids") or ())
                ),
                card_type=_clean_text(condition.get("card_type")),
                card_network=_clean_text(condition.get("card_network")),
                installment_count=(
                    int(condition["installment_count"])
                    if condition.get("installment_count") is not None
                    else None
                ),
            )
            for condition in (
                getattr(version, "payment_conditions", None) or ()
            )
            if isinstance(condition, dict)
        ),
        conditions=tuple(version.conditions or ()),
        source_category=version.source_category,
        source_product_count=version.source_product_count,
        products=tuple(
            CampaignProductLink(
                product_id=str(link.product_id) if link.product_id else None,
                category_id=(
                    str(link.category_id)
                    if getattr(link, "category_id", None)
                    else None
                ),
                product_name=link.product_name_snapshot,
                relation_type=ProductRelationType(link.relation_type),
                quantity_required=link.quantity_required,
                discount_type=(
                    DiscountType(link.discount_type)
                    if getattr(link, "discount_type", None)
                    else None
                ),
                discount_value=getattr(link, "discount_value", None),
                base_price_type=(
                    BasePriceType(link.base_price_type)
                    if getattr(link, "base_price_type", None)
                    else None
                ),
                applies_per_unit=getattr(link, "applies_per_unit", None),
                gift_price=getattr(link, "gift_price", None),
            )
            for link in links
        ),
    )


def _version_view(
    campaign: Campaign,
    version: CampaignVersion,
    links: Sequence[CampaignVersionProduct],
    reference: datetime,
) -> CampaignVersionView:
    state = _state(campaign, version, reference)
    campaign_type = CampaignType(version.campaign_type)
    base_price_type = BasePriceType(version.base_price_type)
    discount_type = DiscountType(version.discount_type)
    return CampaignVersionView(
        id=version.id,
        version_no=version.version_no,
        name=version.name,
        description=version.description,
        campaign_type=campaign_type.value,
        campaign_type_label=CAMPAIGN_TYPE_LABELS[campaign_type],
        starts_at=version.starts_at,
        ends_at=version.ends_at,
        state=state.value,
        state_label=CAMPAIGN_STATE_LABELS[state],
        base_price_type=base_price_type.value,
        base_price_type_label=BASE_PRICE_TYPE_LABELS[base_price_type],
        discount_type=discount_type.value,
        discount_type_label=DISCOUNT_TYPE_LABELS[discount_type],
        discount_value=version.discount_value,
        gift_description=version.gift_description,
        gift_optional=version.gift_optional,
        gift_yes_base_price_type=version.gift_yes_base_price_type,
        gift_no_base_price_type=version.gift_no_base_price_type,
        employee_note=version.employee_note,
        combines_with_others=(
            True
            if getattr(version, "combines_with_others", True) is None
            else bool(version.combines_with_others)
        ),
        exclusion_group=getattr(version, "exclusion_group", None),
        min_basket_total=getattr(version, "min_basket_total", None),
        payment_conditions=tuple(
            {
                "channel": condition.get("channel"),
                "channel_label": _channel_label(condition.get("channel")),
                "bank_ids": tuple(condition.get("bank_ids") or ()),
                "bank_count": len(condition.get("bank_ids") or ()),
                "card_type": condition.get("card_type"),
                "card_type_label": _card_type_label(
                    condition.get("card_type")
                ),
                "card_network": condition.get("card_network"),
                "installment_count": condition.get("installment_count"),
            }
            for condition in (
                getattr(version, "payment_conditions", None) or ()
            )
            if isinstance(condition, dict)
        ),
        conditions=tuple(version.conditions or ()),
        source_category=version.source_category,
        source_product_count=version.source_product_count,
        scraped_at=version.scraped_at,
        created_at=version.created_at,
        created_by_name=version.created_by_name,
        products=tuple(_product_view(link) for link in links),
    )


def _list_item(
    campaign: Campaign,
    version: CampaignVersion,
    links: Sequence[CampaignVersionProduct],
    reference: datetime,
) -> CampaignListItem:
    state = _state(campaign, version, reference)
    campaign_type = CampaignType(version.campaign_type)
    discount_type = DiscountType(version.discount_type)
    return CampaignListItem(
        id=campaign.id,
        name=version.name,
        description=version.description,
        campaign_type=campaign_type.value,
        campaign_type_label=CAMPAIGN_TYPE_LABELS[campaign_type],
        starts_at=version.starts_at,
        ends_at=version.ends_at,
        state=state.value,
        state_label=CAMPAIGN_STATE_LABELS[state],
        is_archived=campaign.is_archived,
        discount_type=discount_type.value,
        discount_type_label=DISCOUNT_TYPE_LABELS[discount_type],
        discount_value=version.discount_value,
        gift_description=version.gift_description,
        product_count=sum(
            1 for link in links if link.product_id is not None
        ),
    )


def _product_view(link: CampaignVersionProduct) -> CampaignProductView:
    relation = ProductRelationType(link.relation_type)
    discount_type = (
        DiscountType(link.discount_type)
        if getattr(link, "discount_type", None)
        else None
    )
    category_id = getattr(link, "category_id", None)
    return CampaignProductView(
        product_id=link.product_id,
        product_name=link.product_name_snapshot,
        relation_type=relation.value,
        relation_label=PRODUCT_RELATION_TYPE_LABELS[relation],
        quantity_required=link.quantity_required,
        category_id=category_id,
        target_type="category" if category_id else "product",
        discount_type=discount_type.value if discount_type else None,
        discount_type_label=(
            DISCOUNT_TYPE_LABELS[discount_type] if discount_type else None
        ),
        discount_value=getattr(link, "discount_value", None),
        base_price_type=getattr(link, "base_price_type", None),
        applies_per_unit=getattr(link, "applies_per_unit", None),
        gift_price=getattr(link, "gift_price", None),
    )


def _state(
    campaign: Campaign, version: CampaignVersion, reference: datetime
) -> CampaignState:
    return classify_campaign(
        starts_at=version.starts_at,
        ends_at=version.ends_at,
        archived=campaign.is_archived,
        as_of=reference,
    )


def _price_input(
    product: Product | None,
    pricing: DealerPricing | None,
) -> CampaignPriceInput | None:
    if product is None:
        return None
    return CampaignPriceInput(
        regular_price=product.regular_price,
        website_discounted_price=product.website_discounted_price,
        cash_floor_price=(
            pricing.cash_floor_price if pricing is not None else None
        ),
        card_floor_price=(
            pricing.card_floor_price if pricing is not None else None
        ),
    )


def _first_product_id(
    links: Sequence[CampaignVersionProduct],
) -> uuid.UUID | None:
    for link in links:
        if link.product_id is not None:
            return link.product_id
    return None


def _effective_dealer_percent(
    uow: UnitOfWork, override: Decimal | None
) -> Decimal:
    if override is not None:
        try:
            return validate_dealer_percent(override)
        except ValueError as exc:
            raise ValidationError(
                "Bayi indirimi oranı %0 ile %100 arasında olmalıdır."
            ) from exc
    setting = uow.dealer_pricing.get_setting()
    if setting is None:
        return DEFAULT_DEALER_DISCOUNT_PERCENT
    return setting.default_percent


def _channel_label(value: object) -> str | None:
    if not value:
        return None
    try:
        return CHANNEL_LABELS[PaymentChannel(str(value))]
    except ValueError:
        return str(value)


def _card_type_label(value: object) -> str | None:
    if not value:
        return None
    try:
        return CARD_TYPE_LABELS[CardType(str(value))]
    except ValueError:
        return str(value)


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _ensure_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)
