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
from bayios.domain.commissions import CardType, PaymentChannel
from bayios.domain.offers import PaymentType
from tests.fakes import FakeUnitOfWork


def _card_offer_without_bank() -> tuple[FakeUnitOfWork, uuid.UUID]:
    from bayios.adapters.db.models.commissions import (
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
    for installment in range(1, 4):
        uow.commissions.add_rate(
            CommissionRate(
                id=uuid.uuid4(),
                period_id=period.id,
                channel="chippin",
                bank_id=None,
                product_group=None,
                installment_count=installment,
                commission_percent=Decimal(3),
                scope_key=f"chippin|-|-|-|{installment}",
            )
        )
    product = Product(
        id=uuid.uuid4(),
        name="Buzdolabı",
        name_normalized="buzdolabı",
        regular_price=Decimal(10000),
        physical_stock=1,
    )
    uow.products.add(product)
    offer_id = create_offer(
        uow,
        OfferInput(
            customer_name="Ayşe",
            customer_phone=None,
            payment_type=PaymentType.CARD,
            dealer_discount_percent=Decimal(10),
            items=(OfferItemInput(product.id, 1),),
            channel=PaymentChannel.CHIPPIN,
            installment_count=1,
            card_type=CardType.CONSUMER,
        ),
    )
    return uow, offer_id


def test_offer_import_can_create_missing_bank_when_enabled() -> None:
    from bayios.adapters.db.models.offers import Offer

    uow, offer_id = _card_offer_without_bank()
    data = export_offers_xlsx(uow)
    workbook = load_workbook(io.BytesIO(data))
    sheet = workbook["Teklifler"]
    headers = [sheet.cell(row=1, column=index).value for index in range(1, sheet.max_column + 1)]
    bank_column = headers.index("Banka") + 1
    sheet.cell(row=2, column=bank_column, value="AKBANK")
    stream = io.BytesIO()
    workbook.save(stream)
    modified = stream.getvalue()

    without = preview_offer_import(uow, modified)
    assert any("Banka bulunamadı" in error for error in without.rows[0].errors)

    preview = preview_offer_import(uow, modified, auto_create_banks=True)
    assert not preview.rows[0].errors
    assert any("Yeni banka" in warning for warning in preview.rows[0].warnings)

    commit_offer_import(
        uow,
        file_name="teklifler.xlsx",
        file_type="xlsx",
        source=modified,
        decisions={},
        commit_token="offers-new-bank",
        auto_create_banks=True,
    )
    bank = next(iter(uow.commissions.banks.values()))
    assert bank.name == "Akbank"
    offer = uow.offers.get(offer_id)
    assert isinstance(offer, Offer)
    assert offer.bank_id == bank.id



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
    main_sheet = workbook["Teklifler"]
    assert main_sheet.cell(row=1, column=main_sheet.max_column).value == "Ürünler"
    assert "Buzdolabı" in str(main_sheet.cell(row=2, column=main_sheet.max_column).value)
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


def test_offer_import_resolves_product_by_external_id_before_name() -> None:
    uow, _offer_id = _card_offer_without_bank()
    product = next(iter(uow.products.get_all()))
    product.external_id = "9000"
    data = export_offers_xlsx(uow)
    workbook = load_workbook(io.BytesIO(data))
    sheet = workbook["Teklif Satırları"]
    headers = [
        sheet.cell(row=1, column=index).value
        for index in range(1, sheet.max_column + 1)
    ]
    name_column = headers.index("Ürün Adı") + 1
    id_column = headers.index("Ürün ID") + 1
    sheet.cell(row=2, column=name_column, value="Tamamen Farkli Ad")
    stream = io.BytesIO()
    workbook.save(stream)
    modified = stream.getvalue()

    preview = preview_offer_import(uow, modified)
    assert not preview.rows[0].errors, preview.rows[0].errors

    sheet.cell(row=2, column=id_column, value="9999")
    stream = io.BytesIO()
    workbook.save(stream)
    missing = preview_offer_import(uow, stream.getvalue())
    assert any("Ürün ID bulunamadı" in error for error in missing.rows[0].errors)
