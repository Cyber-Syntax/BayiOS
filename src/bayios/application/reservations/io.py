from __future__ import annotations

from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.reservations import STATUS_LABELS, list_reservations
from bayios.application.tabular import ColumnSpec, SheetSpec, write_xlsx
from bayios.domain.reservations import ReservationStatus


def export_reservations_xlsx(
    uow: UnitOfWork,
    *,
    status: str | None = None,
    query: str | None = None,
) -> bytes:
    rows, _total = list_reservations(
        uow, status=status, query=query, limit=10_000, offset=0
    )
    with uow:
        items_by_reservation = uow.reservations.get_items_for_reservations(
            [row.id for row in rows]
        )
    reservation_rows: list[dict[str, object]] = []
    item_rows: list[dict[str, object]] = []
    for row in rows:
        reservation_rows.append(
            {
                "reservation_number": row.reservation_number,
                "reservation_key": f"#{row.reservation_number}",
                "customer_name": row.customer_name,
                "reservation_date": row.reservation_date,
                "reminder_due_at": row.reminder_due_at,
                "reminder_status": row.reminder_label,
                "overdue": row.is_overdue,
                "summary": row.summary.label,
                "total_quantity": row.summary.total_quantity,
                "delivered_quantity": row.summary.delivered_quantity,
                "cancelled_quantity": row.summary.cancelled_quantity,
                "open_quantity": row.summary.open_quantity,
            }
        )
        for item in items_by_reservation.get(row.id, ()):
            item_rows.append(
                {
                    "reservation_number": row.reservation_number,
                    "reservation_key": f"#{row.reservation_number}",
                    "product_name": item.product_name_snapshot,
                    "quantity": item.quantity,
                    "delivered_quantity": item.delivered_quantity,
                    "cancelled_quantity": item.cancelled_quantity,
                    "open_quantity": (
                        item.quantity
                        - item.delivered_quantity
                        - item.cancelled_quantity
                    ),
                    "status": STATUS_LABELS.get(
                        ReservationStatus(item.status), item.status
                    ),
                    "service_date": item.service_date,
                    "other_dealer_note": item.other_dealer_note or "",
                    "note": item.note or "",
                }
            )
    reservation_sheet = SheetSpec(
        title="Rezervasyonlar",
        columns=(
            ColumnSpec("Rezervasyon No", "reservation_number", "int", 16),
            ColumnSpec("Rezervasyon Anahtarı", "reservation_key", "text", 18),
            ColumnSpec("Müşteri Adı", "customer_name", "text", 28),
            ColumnSpec("Rezervasyon Tarihi", "reservation_date", "date", 18),
            ColumnSpec("Hatırlatma Tarihi", "reminder_due_at", "date", 18),
            ColumnSpec("Hatırlatma Durumu", "reminder_status", "text", 16),
            ColumnSpec("Gecikmiş", "overdue", "bool", 10),
            ColumnSpec("Durum", "summary", "text", 16),
            ColumnSpec("Toplam Adet", "total_quantity", "int", 12),
            ColumnSpec("Teslim Edilen", "delivered_quantity", "int", 14),
            ColumnSpec("İptal Edilen", "cancelled_quantity", "int", 14),
            ColumnSpec("Açık Adet", "open_quantity", "int", 12),
        ),
        rows=reservation_rows,
        instructions=(
            ("Müşteri Adı", "Zorunlu", "Yeni rezervasyon için zorunlu."),
            ("Rezervasyon Tarihi", "Zorunlu", "GG.AA.YYYY veya ISO tarih."),
            ("Hatırlatma Tarihi", "Opsiyonel", "Boşsa rezervasyon tarihinin 13 ay sonrası."),
            ("Teslim / İptal / Durum", "Salt okunur", "İçe aktarmada kullanılmaz."),
        ),
    )
    item_sheet = SheetSpec(
        title="Rezervasyon Satırları",
        columns=(
            ColumnSpec("Rezervasyon No", "reservation_number", "int", 16),
            ColumnSpec("Rezervasyon Anahtarı", "reservation_key", "text", 18),
            ColumnSpec("Ürün Adı", "product_name", "text", 34),
            ColumnSpec("Miktar", "quantity", "int", 10),
            ColumnSpec("Teslim Edilen", "delivered_quantity", "int", 14),
            ColumnSpec("İptal Edilen", "cancelled_quantity", "int", 14),
            ColumnSpec("Açık", "open_quantity", "int", 10),
            ColumnSpec("Durum", "status", "text", 18),
            ColumnSpec("Servis Tarihi", "service_date", "date", 16),
            ColumnSpec("Diğer Bayi Notu", "other_dealer_note", "text", 28),
            ColumnSpec("Satır Notu", "note", "text", 28),
        ),
        rows=item_rows,
        instructions=(
            ("Ürün Adı", "Zorunlu", "Mevcut ürünlerden biri olmalıdır."),
            ("Miktar", "Zorunlu", "Pozitif tam sayı."),
            ("Teslim / İptal / Durum", "Salt okunur", "İçe aktarmada yok sayılır."),
        ),
    )
    return write_xlsx((reservation_sheet, item_sheet))


def reservation_import_template() -> bytes:
    reservation_sheet = SheetSpec(
        title="Rezervasyonlar",
        columns=(
            ColumnSpec("Rezervasyon No", "reservation_number", "int", 16),
            ColumnSpec("Rezervasyon Anahtarı", "reservation_key", "text", 18),
            ColumnSpec("Müşteri Adı", "customer_name", "text", 28),
            ColumnSpec("Rezervasyon Tarihi", "reservation_date", "date", 18),
            ColumnSpec("Hatırlatma Tarihi", "reminder_due_at", "date", 18),
            ColumnSpec("Not", "note", "text", 30),
        ),
        rows=(),
        instructions=(
            ("Rezervasyon Anahtarı", "Gruplama", "Yeni rezervasyonlarda zorunlu."),
            ("Müşteri Adı", "Zorunlu", "Rezervasyon müşterisi."),
            ("Rezervasyon Tarihi", "Zorunlu", "GG.AA.YYYY veya ISO tarih."),
            ("Hatırlatma Tarihi", "Opsiyonel", "Boşsa 13 ay sonrası."),
        ),
    )
    item_sheet = SheetSpec(
        title="Rezervasyon Satırları",
        columns=(
            ColumnSpec("Rezervasyon No", "reservation_number", "int", 16),
            ColumnSpec("Rezervasyon Anahtarı", "reservation_key", "text", 18),
            ColumnSpec("Ürün Adı", "product_name", "text", 34),
            ColumnSpec("Miktar", "quantity", "int", 10),
            ColumnSpec("Satır Notu", "note", "text", 28),
        ),
        rows=(),
        instructions=(
            ("Ürün Adı", "Zorunlu", "Mevcut ürünlerden biri."),
            ("Miktar", "Zorunlu", "Pozitif tam sayı."),
        ),
    )
    return write_xlsx((reservation_sheet, item_sheet))
