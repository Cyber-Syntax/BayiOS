from __future__ import annotations

import uuid

from bayios.application.inventory import get_stock_overview, list_categories
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.tabular import ColumnSpec, SheetSpec, write_xlsx


def export_stock_xlsx(
    uow: UnitOfWork,
    *,
    category_id: uuid.UUID | None = None,
    query: str | None = None,
) -> bytes:
    categories = {category.id: category.name for category in list_categories(uow)}
    rows, _total = get_stock_overview(
        uow, category_id=category_id, query=query, limit=10_000, offset=0
    )
    sheet = SheetSpec(
        title="Stok",
        columns=(
            ColumnSpec("Ürün Adı", "product_name", "text", 34),
            ColumnSpec("Kategori", "category", "text", 22),
            ColumnSpec("Fiziksel Stok", "physical", "int", 14),
            ColumnSpec("Açık Rezervasyon", "open_reservation", "int", 16),
            ColumnSpec("Kullanılabilir", "available", "int", 14),
            ColumnSpec("Durum", "status", "text", 14),
        ),
        rows=tuple(
            {
                "product_name": row.product.name,
                "category": categories.get(row.product.category_id, ""),
                "physical": row.summary.physical,
                "open_reservation": row.summary.open_reservation,
                "available": row.summary.physical - row.summary.open_reservation,
                "status": (
                    "Stokta"
                    if row.summary.physical > 0
                    else "Stok yok"
                ),
            }
            for row in rows
        ),
        instructions=(
            ("Fiziksel Stok", "Salt okunur", "Güncelleme için ürün içe aktarma veya sayım kullanılır."),
            ("Kullanılabilir", "Salt okunur", "Fiziksel stok - açık rezervasyon."),
        ),
    )
    return write_xlsx((sheet,))
