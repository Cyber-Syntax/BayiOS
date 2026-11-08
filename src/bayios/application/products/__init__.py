from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from bayios.adapters.db.models.inventory import StockMovement
from bayios.adapters.db.models.products import Product, ProductPriceHistory
from bayios.application.ports.unit_of_work import UnitOfWork


@dataclass(frozen=True)
class ProductDetail:
    product: Product
    price_history: Sequence[ProductPriceHistory]
    stock_movements: Sequence[StockMovement]
    sellable_stock: int
    open_reservation: int
    supply_need: int


def search_products(
    uow: UnitOfWork, query: str | None = None, limit: int = 50, offset: int = 0
) -> tuple[Sequence[Product], int]:
    with uow:
        return uow.products.search(query=query, limit=limit, offset=offset)


def get_product_detail(uow: UnitOfWork, product_id: uuid.UUID) -> ProductDetail | None:
    with uow:
        product = uow.products.get_by_id(product_id)
        if product is None:
            return None
        price_history = uow.products.get_price_history(product_id)
        stock_movements = uow.products.get_stock_movements(product_id)

        # In M1 open_reservation is 0
        open_reservation = 0
        sellable_stock = max(0, product.physical_stock - open_reservation)
        supply_need = max(0, open_reservation - product.physical_stock)

        return ProductDetail(
            product=product,
            price_history=price_history,
            stock_movements=stock_movements,
            sellable_stock=sellable_stock,
            open_reservation=open_reservation,
            supply_need=supply_need,
        )


def export_products_csv(uow: UnitOfWork) -> bytes:
    with uow:
        products = uow.products.get_all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "product_name",
            "regular_price",
            "website_discounted_price",
            "quantity",
            "cost_price",
        ]
    )
    for p in products:
        writer.writerow(
            [
                p.name,
                format(p.regular_price, "f") if p.regular_price is not None else "",
                format(p.website_discounted_price, "f")
                if p.website_discounted_price is not None
                else "",
                p.physical_stock,
                format(p.cost_price, "f") if p.cost_price is not None else "",
            ]
        )
    return output.getvalue().encode("utf-8-sig")


def export_products_xlsx(uow: UnitOfWork) -> bytes:
    from openpyxl import Workbook

    with uow:
        products = uow.products.get_all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Ürünler"
    ws.append(
        [
            "product_name",
            "regular_price",
            "website_discounted_price",
            "quantity",
            "cost_price",
        ]
    )
    for p in products:
        ws.append(
            [
                p.name,
                float(p.regular_price) if p.regular_price is not None else None,
                float(p.website_discounted_price)
                if p.website_discounted_price is not None
                else None,
                p.physical_stock,
                float(p.cost_price) if p.cost_price is not None else None,
            ]
        )
    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()
