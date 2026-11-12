from __future__ import annotations

import io
import uuid
from decimal import Decimal

from openpyxl import load_workbook

from bayios.adapters.db.models.products import Product
from bayios.application.imports.offers import (
    commit_offer_import,
    preview_offer_import,
)
from bayios.application.offers import (
    OfferInput,
    OfferItemInput,
    build_offer_profit_summary,
    create_offer,
    get_offer_detail,
)
from bayios.application.offers.io import export_offers_xlsx
from bayios.domain.offers import PaymentType
from tests.fakes import FakeUnitOfWork


def _fixture() -> tuple[FakeUnitOfWork, uuid.UUID]:
    uow = FakeUnitOfWork()
    product = Product(
        id=uuid.uuid4(),
        name="Buzdolabı",
        name_normalized="buzdolabı",
        regular_price=Decimal(50000),
        website_discounted_price=Decimal(46000),
        cost_price=Decimal(36000),
        physical_stock=1,
    )
    uow.products.add(product)
    offer_id = create_offer(
        uow,
        OfferInput(
            customer_name="Ayşe",
            customer_phone="555",
            payment_type=PaymentType.CASH,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product.id, 1),),
        ),
    )
    return uow, offer_id


def test_offer_profit_summary_has_commission_and_profit() -> None:
    uow, offer_id = _fixture()
    detail = get_offer_detail(uow, offer_id)
    assert detail is not None
    summary = build_offer_profit_summary(detail)
    assert len(summary.lines) == 1
    line = summary.lines[0]
    assert line.sale_price == Decimal("41400.00")
    assert line.cost == Decimal(36000)
    assert line.total_revenue == Decimal("44800.00")
    assert line.profit == Decimal("8800.00")
    assert summary.total_profit == Decimal("8800.00")


def test_offer_export_has_three_sheets_and_profit_rows() -> None:
    uow, _offer_id = _fixture()
    data = export_offers_xlsx(uow)
    workbook = load_workbook(io.BytesIO(data))
    assert workbook.sheetnames == ["Teklifler", "Teklif Satırları", "Kâr Detayı", "Kullanım"]
    assert workbook["Teklifler"]["A1"].value == "Teklif No"
    assert workbook["Kâr Detayı"]["J1"].value == "Maliyet"
    assert workbook["Kâr Detayı"].max_row == 2


def test_offer_round_trip_updates_draft() -> None:
    uow, offer_id = _fixture()
    data = export_offers_xlsx(uow)
    preview = preview_offer_import(uow, data)
    assert len(preview.rows) == 1
    assert preview.rows[0].decision == "update"
    result = commit_offer_import(
        uow,
        file_name="teklif.xlsx",
        file_type="xlsx",
        source=data,
        decisions={},
        commit_token="offer-roundtrip",
    )
    assert result.updated_count == 1
    assert len(uow.offers.offers) == 1
    assert offer_id in uow.offers.offers
