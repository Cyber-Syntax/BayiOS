from __future__ import annotations

import json
from datetime import UTC, datetime

from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.domain.commissions import CARD_TYPE_LABELS, CHANNEL_LABELS
from bayios.domain.offers import OFFER_STATUS_LABELS, PAYMENT_TYPE_LABELS


def export_offers_json(
    uow: UnitOfWork,
    *,
    status: str | None = None,
    query: str | None = None,
) -> bytes:
    now = datetime.now(UTC)
    with uow:
        offers, _total = uow.offers.list(
            status=status, query=query, limit=10_000, offset=0
        )
        items_by_offer = uow.offers.get_items_for_offers(
            [offer.id for offer in offers]
        )
        product_ids = [
            item.product_id
            for items in items_by_offer.values()
            for item in items
            if item.product_id is not None
        ]
        products = {
            product.id: product
            for product in uow.products.get_by_ids(product_ids)
        }
        campaign_ids_by_version: dict[object, str] = {}
        for version_id in {
            item.campaign_version_id
            for items in items_by_offer.values()
            for item in items
            if item.campaign_version_id is not None
        }:
            version = uow.campaigns.get_version(version_id)
            if version is not None:
                campaign_ids_by_version[version_id] = str(version.campaign_id)

    payload = {
        "schema_version": "1.0",
        "exported_at": now.isoformat(),
        "offers": [
            {
                "offer_number": offer.offer_number,
                "offer_key": f"#{offer.offer_number}",
                "customer_name": offer.customer_name or "",
                "customer_phone": offer.customer_phone or "",
                "created_at": offer.created_at.isoformat(),
                "status": offer.status,
                "status_label": OFFER_STATUS_LABELS.get(
                    offer.status, offer.status
                ),
                "payment_type": offer.payment_type,
                "payment_label": PAYMENT_TYPE_LABELS.get(
                    offer.payment_type, offer.payment_type
                ),
                "channel": offer.channel or "",
                "channel_label": CHANNEL_LABELS.get(
                    offer.channel, offer.channel or ""
                )
                if offer.channel
                else "",
                "bank_name": offer.bank_name_snapshot or "",
                "card_network": offer.card_network or "",
                "installment_count": offer.installment_count,
                "card_type": offer.card_type or "",
                "card_type_label": CARD_TYPE_LABELS.get(
                    offer.card_type, offer.card_type or ""
                )
                if offer.card_type
                else "",
                "dealer_discount_percent": str(offer.dealer_discount_percent),
                "dealer_discount_cash_percent": str(
                    offer.dealer_discount_cash_percent
                ),
                "cash_total": str(offer.cash_total),
                "card_total": str(offer.card_total),
                "selected_total": str(offer.selected_total),
                "cash_total_override": (
                    str(offer.cash_total_override)
                    if offer.cash_total_override is not None
                    else None
                ),
                "card_total_override": (
                    str(offer.card_total_override)
                    if offer.card_total_override is not None
                    else None
                ),
                "note": offer.note or "",
                "items": [
                    {
                        "product_id": (
                            products[item.product_id].external_id
                            if item.product_id in products
                            and products[item.product_id].external_id
                            else (
                                str(item.product_id)
                                if item.product_id is not None
                                else ""
                            )
                        ),
                        "product_name": item.product_name_snapshot,
                        "quantity": item.quantity,
                        "campaign_name": item.campaign_name_snapshot or "",
                        "campaign_id": campaign_ids_by_version.get(
                            item.campaign_version_id, ""
                        ),
                        "is_gift": bool(
                            (item.campaign_snapshot or {}).get("is_gift")
                        ),
                        "gift_present": item.campaign_gift_present,
                        "unit_price_cash": (
                            str(item.unit_price_cash)
                            if item.unit_price_cash is not None
                            else None
                        ),
                        "unit_price_card": (
                            str(item.unit_price_card)
                            if item.unit_price_card is not None
                            else None
                        ),
                        "line_total_cash": (
                            str(item.line_total_cash)
                            if item.line_total_cash is not None
                            else None
                        ),
                        "line_total_card": (
                            str(item.line_total_card)
                            if item.line_total_card is not None
                            else None
                        ),
                    }
                    for item in items_by_offer.get(offer.id, ())
                ],
            }
            for offer in offers
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

