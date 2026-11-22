from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from bayios.adapters.db.models.products import Product
from bayios.application.imports.offers_json import (
    commit_offer_json,
    preview_offer_json,
)
from bayios.application.imports.reservations_json import (
    commit_reservation_json,
    preview_reservation_json,
)
from bayios.application.offers import (
    OfferInput,
    OfferItemInput,
    create_offer,
    set_offer_status,
)
from bayios.application.offers.json_io import export_offers_json
from bayios.application.reservations import NewReservationItem, create_reservation
from bayios.application.reservations.json_io import export_reservations_json
from bayios.domain.offers import OfferStatus, PaymentType
from tests.fakes import FakeUnitOfWork


def _product_uow() -> tuple[FakeUnitOfWork, Product]:
    uow = FakeUnitOfWork()
    product = Product(
        id=uuid.uuid4(),
        external_id="9000",
        name="Buzdolabı",
        name_normalized="buzdolabı",
        regular_price=Decimal("10000.00"),
        cost_price=Decimal("8000.00"),
        physical_stock=5,
    )
    uow.products.add(product)
    return uow, product


def test_offer_json_export_and_import_round_trip() -> None:
    uow, product = _product_uow()
    offer_id = create_offer(
        uow,
        OfferInput(
            customer_name="JSON Müşteri",
            customer_phone="555",
            payment_type=PaymentType.CASH,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product.id, 2),),
            cash_total_override=Decimal("15000.00"),
            card_total_override=Decimal("16000.00"),
            note="JSON notu",
        ),
    )
    set_offer_status(
        uow, offer_id, OfferStatus.PRESENTED.value, note="sunuldu"
    )
    set_offer_status(
        uow, offer_id, OfferStatus.ACCEPTED.value, note="kabul"
    )

    exported = export_offers_json(uow)
    payload = json.loads(exported)
    assert payload["schema_version"] == "1.0"
    item = payload["offers"][0]
    assert item["status"] == "accepted"
    assert item["cash_total"] == "15000.00"
    assert item["items"][0]["product_id"] == "9000"
    assert item["items"][0]["quantity"] == 2

    new_uow, _product = _product_uow()
    preview = preview_offer_json(new_uow, exported)
    assert len(preview.rows) == 1
    assert not preview.rows[0].errors
    result = commit_offer_json(
        new_uow,
        file_name="teklifler.json",
        file_type="json",
        source=exported,
        decisions={},
    )
    assert result.created_count == 1
    imported = next(iter(new_uow.offers.offers.values()))
    assert imported.customer_name == "JSON Müşteri"
    assert imported.cash_total == Decimal("15000.00")
    assert imported.card_total == Decimal("16000.00")
    assert imported.status == "accepted"
    imported_items = new_uow.offers.get_items(imported.id)
    assert len(imported_items) == 1
    assert imported_items[0].quantity == 2


def test_reservation_json_export_and_import_round_trip() -> None:
    uow, product = _product_uow()
    created = create_reservation(
        uow,
        "JSON Rezervasyon",
        (NewReservationItem(product.id, 2),),
        reservation_date=datetime(2026, 11, 10, tzinfo=UTC),
        note="not",
    )
    line = uow.reservations.get_items(created.id)[0]
    line.delivered_quantity = 1
    line.status = "delivery_requested"

    exported = export_reservations_json(uow)
    payload = json.loads(exported)
    assert payload["schema_version"] == "1.0"
    item = payload["reservations"][0]
    assert item["items"][0]["product_id"] == "9000"
    assert item["items"][0]["delivered_quantity"] == 1
    assert item["items"][0]["status"] == "delivery_requested"

    new_uow, _product = _product_uow()
    preview = preview_reservation_json(new_uow, exported)
    assert len(preview.rows) == 1
    assert not preview.rows[0].errors
    result = commit_reservation_json(
        new_uow,
        file_name="rezervasyonlar.json",
        file_type="json",
        source=exported,
        decisions={},
    )
    assert result.created_count == 1
    imported = next(iter(new_uow.reservations.reservations.values()))
    assert imported.customer_name == "JSON Rezervasyon"
    imported_items = new_uow.reservations.get_items(imported.id)
    assert len(imported_items) == 1
    assert imported_items[0].delivered_quantity == 1
    assert imported_items[0].status == "delivery_requested"


def test_offer_json_import_rejects_unknown_product() -> None:
    uow, _product = _product_uow()
    source = json.dumps(
        {
            "schema_version": "1.0",
            "offers": [
                {
                    "offer_number": 1,
                    "customer_name": "Eksik Ürün",
                    "payment_type": "cash",
                    "items": [
                        {
                            "product_name": "Yok",
                            "product_id": "999999",
                            "quantity": 1,
                        }
                    ],
                }
            ],
        }
    ).encode()

    preview = preview_offer_json(uow, source)

    assert preview.rows[0].errors
    result = commit_offer_json(
        uow,
        file_name="teklifler.json",
        file_type="json",
        source=source,
        decisions={},
    )
    assert result.error_count == 1
    assert not uow.offers.offers
