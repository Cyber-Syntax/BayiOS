from __future__ import annotations

import json
from datetime import UTC, datetime

from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.reservations import STATUS_LABELS, list_reservations
from bayios.domain.reservations import ReservationStatus


def export_reservations_json(
    uow: UnitOfWork,
    *,
    status: str | None = None,
    query: str | None = None,
) -> bytes:
    now = datetime.now(UTC)
    rows, _total = list_reservations(
        uow, status=status, query=query, limit=10_000, offset=0
    )
    with uow:
        items_by_reservation = uow.reservations.get_items_for_reservations(
            [row.id for row in rows]
        )
        product_ids = [
            item.product_id
            for items in items_by_reservation.values()
            for item in items
            if item.product_id is not None
        ]
        products = {
            product.id: product
            for product in uow.products.get_by_ids(product_ids)
        }

    payload = {
        "schema_version": "1.0",
        "exported_at": now.isoformat(),
        "reservations": [
            {
                "reservation_number": row.reservation_number,
                "reservation_key": f"#{row.reservation_number}",
                "customer_name": row.customer_name,
                "reservation_date": row.reservation_date.isoformat(),
                "reminder_due_at": row.reminder_due_at.isoformat(),
                "reminder_status": row.reminder_status,
                "reminder_label": row.reminder_label,
                "is_overdue": row.is_overdue,
                "summary": row.summary.label,
                "products_summary": row.products_summary,
                "open_quantity": row.summary.open_quantity,
                "total_quantity": row.summary.total_quantity,
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
                        "delivered_quantity": item.delivered_quantity,
                        "cancelled_quantity": item.cancelled_quantity,
                        "open_quantity": (
                            item.quantity
                            - item.delivered_quantity
                            - item.cancelled_quantity
                        ),
                        "status": item.status,
                        "status_label": STATUS_LABELS.get(
                            ReservationStatus(item.status), item.status
                        ),
                        "service_date": (
                            item.service_date.isoformat()
                            if item.service_date is not None
                            else None
                        ),
                        "other_dealer_note": item.other_dealer_note or "",
                        "note": item.note or "",
                    }
                    for item in items_by_reservation.get(row.id, ())
                ],
            }
            for row in rows
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
