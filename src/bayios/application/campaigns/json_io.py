from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from bayios.application.errors import NotFoundError
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.domain.campaigns import (
    PRODUCT_RELATION_TYPE_LABELS,
    ProductRelationType,
)

_MONTHS = (
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
)


def export_campaigns_json(
    uow: UnitOfWork,
    *,
    query: str | None = None,
    campaign_type: str | None = None,
    state: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    campaign_id: uuid.UUID | None = None,
) -> bytes:
    return _export(
        uow,
        query=query,
        campaign_type=campaign_type,
        state=state,
        date_from=date_from,
        date_to=date_to,
        campaign_id=campaign_id,
    )


def export_campaign_detail_json(
    uow: UnitOfWork, campaign_id: uuid.UUID
) -> bytes:
    return _export(uow, campaign_id=campaign_id)


def _export(
    uow: UnitOfWork,
    *,
    query: str | None = None,
    campaign_type: str | None = None,
    state: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    campaign_id: uuid.UUID | None = None,
) -> bytes:
    now = datetime.now(UTC)
    with uow:
        if campaign_id is not None:
            campaign = uow.campaigns.get(campaign_id)
            version = uow.campaigns.get_current_version(campaign_id)
            if campaign is None or version is None:
                raise NotFoundError("Kampanya bulunamadı.")
            rows = [(campaign, version)]
        else:
            rows, _total = uow.campaigns.list(
                query=query,
                campaign_type=campaign_type,
                state=state,
                date_from=date_from,
                date_to=date_to,
                as_of=now,
                limit=10_000,
                offset=0,
            )
        links_by_version = uow.campaigns.get_version_products_for_versions(
            [version.id for _campaign, version in rows]
        )
        product_ids = [
            link.product_id
            for links in links_by_version.values()
            for link in links
            if link.product_id is not None
        ]
        products = {
            product.id: product
            for product in uow.products.get_by_ids(product_ids)
        }

    campaigns: list[dict[str, object]] = []
    for campaign, version in rows:
        links = links_by_version.get(version.id, ())
        campaigns.append(
            {
                "id": campaign.external_id or str(campaign.id),
                "name": version.name,
                "category": version.source_category or "",
                "url": campaign.source_url or "",
                "date_text": _date_text(version.starts_at, version.ends_at),
                "start_date": version.starts_at.date().isoformat(),
                "end_date": version.ends_at.date().isoformat(),
                "conditions": list(version.conditions or ()),
                "product_count": (
                    version.source_product_count
                    if version.source_product_count is not None
                    else len(links)
                ),
                "combines_with_others": bool(
                    getattr(version, "combines_with_others", True)
                ),
                "exclusion_group": getattr(version, "exclusion_group", None),
                "min_basket_total": (
                    str(version.min_basket_total)
                    if getattr(version, "min_basket_total", None) is not None
                    else None
                ),
                "products": [
                    {
                        "name": link.product_name_snapshot,
                        "target_type": (
                            "category"
                            if getattr(link, "category_id", None)
                            else "product"
                        ),
                        "product_id": (
                            products[link.product_id].external_id
                            if link.product_id in products
                            and products[link.product_id].external_id
                            else ""
                        ),
                        "category_id": (
                            str(link.category_id)
                            if getattr(link, "category_id", None)
                            else ""
                        ),
                        "relationship": PRODUCT_RELATION_TYPE_LABELS[
                            ProductRelationType(link.relation_type)
                        ],
                        "required_quantity": link.quantity_required,
                        "discount_type": getattr(link, "discount_type", None),
                        "discount_value": (
                            str(link.discount_value)
                            if getattr(link, "discount_value", None) is not None
                            else None
                        ),
                        "base_price_type": getattr(
                            link, "base_price_type", None
                        ),
                        "applies_per_unit": getattr(
                            link, "applies_per_unit", None
                        ),
                    }
                    for link in links
                ],
                "scraped_at": (
                    version.scraped_at.isoformat()
                    if version.scraped_at is not None
                    else None
                ),
            }
        )

    payload = {
        "schema_version": "1.0",
        "scraped_at": now.isoformat(),
        "campaigns": campaigns,
    }
    return json.dumps(
        payload, ensure_ascii=False, indent=2, default=str
    ).encode("utf-8")


def _date_text(starts_at: datetime, ends_at: datetime) -> str:
    start = starts_at.date()
    end = ends_at.date()
    start_month = _MONTHS[start.month - 1]
    end_month = _MONTHS[end.month - 1]
    if start.year == end.year and start.month == end.month:
        return f"{start.day} {start_month} - {end.day} {end_month} {end.year}"
    if start.year == end.year:
        return (
            f"{start.day} {start_month} - {end.day} {end_month} {end.year}"
        )
    return (
        f"{start.day} {start_month} {start.year} - "
        f"{end.day} {end_month} {end.year}"
    )
