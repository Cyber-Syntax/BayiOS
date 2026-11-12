from __future__ import annotations

from bayios.application.offers import (
    OfferDetail,
    build_offer_line_analyses,
    build_offer_profit_summary,
)
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.tabular import ColumnSpec, SheetSpec, write_xlsx
from bayios.domain.commissions import CARD_TYPE_LABELS, CHANNEL_LABELS
from bayios.domain.offers import OFFER_STATUS_LABELS, PAYMENT_TYPE_LABELS


def export_offers_xlsx(
    uow: UnitOfWork,
    *,
    status: str | None = None,
    query: str | None = None,
) -> bytes:
    with uow:
        offers, _total = uow.offers.list(
            status=status, query=query, limit=10_000, offset=0
        )
        items_by_offer = uow.offers.get_items_for_offers(
            [offer.id for offer in offers]
        )
        bank_names = {
            bank.id: bank.name for bank in uow.commissions.get_banks(active_only=False)
        }

    offer_rows: list[dict[str, object]] = []
    item_rows: list[dict[str, object]] = []
    profit_rows: list[dict[str, object]] = []
    for offer in offers:
        items = tuple(items_by_offer.get(offer.id, ()))
        detail = OfferDetail(offer=offer, items=items, history=())
        analyses = build_offer_line_analyses(detail)
        summary = build_offer_profit_summary(detail)
        offer_rows.append(
            {
                "offer_number": offer.offer_number,
                "offer_key": f"#{offer.offer_number}",
                "customer_name": offer.customer_name or "",
                "customer_phone": offer.customer_phone or "",
                "created_at": offer.created_at,
                "status": OFFER_STATUS_LABELS.get(
                    offer.status, offer.status
                ),
                "payment_type": PAYMENT_TYPE_LABELS.get(
                    offer.payment_type, offer.payment_type
                ),
                "channel": CHANNEL_LABELS.get(offer.channel, offer.channel or ""),
                "bank": bank_names.get(offer.bank_id, ""),
                "installment_count": offer.installment_count,
                "card_type": CARD_TYPE_LABELS.get(
                    offer.card_type, offer.card_type or ""
                ),
                "dealer_discount_percent": offer.dealer_discount_percent,
                "commission_period": offer.commission_period_key_snapshot or "",
                "commission_percent": offer.commission_percent_snapshot,
                "cash_total": offer.cash_total,
                "card_total": offer.card_total,
                "selected_total": offer.selected_total,
                "note": offer.note or "",
                "reservation_number": "",
                "created_by": offer.created_by_name or "",
            }
        )
        for analysis in analyses:
            item = analysis.item
            item_rows.append(
                {
                    "offer_number": offer.offer_number,
                    "offer_key": f"#{offer.offer_number}",
                    "position": item.position,
                    "product_name": item.product_name_snapshot,
                    "quantity": item.quantity,
                    "regular_price": item.regular_price_snapshot,
                    "website_price": item.website_price_snapshot,
                    "cost_price": item.cost_price_snapshot,
                    "campaign": item.campaign_name_snapshot or "",
                    "gift_present": item.campaign_gift_present,
                    "base_price": item.base_price_used,
                    "suggested_cash": item.suggested_cash_price,
                    "suggested_card": item.suggested_card_price,
                    "unit_cash": item.unit_price_cash,
                    "unit_card": item.unit_price_card,
                    "line_total_cash": item.line_total_cash,
                    "line_total_card": item.line_total_card,
                    "warning": item.warning_text or "",
                }
            )
        for line in summary.lines:
            profit_rows.append(
                {
                    "offer_number": offer.offer_number,
                    "offer_key": f"#{offer.offer_number}",
                    "product_name": line.item.product_name_snapshot,
                    "installment_count": line.installment_count,
                    "commission_percent": line.commission_percent,
                    "net_after_commission": line.net_after_commission,
                    "campaign_share": line.campaign_share,
                    "oliz_share": line.oliz_share,
                    "total_revenue": line.total_revenue,
                    "cost": line.cost,
                    "profit": line.profit,
                    "margin_percent": line.margin_percent,
                }
            )

    offer_sheet = SheetSpec(
        title="Teklifler",
        columns=(
            ColumnSpec("Teklif No", "offer_number", "int", 12),
            ColumnSpec("Teklif Anahtarı", "offer_key", "text", 16),
            ColumnSpec("Müşteri Adı", "customer_name", "text", 28),
            ColumnSpec("Telefon", "customer_phone", "text", 16),
            ColumnSpec("Oluşturma Tarihi", "created_at", "datetime", 18),
            ColumnSpec("Durum", "status", "text", 14),
            ColumnSpec("Ödeme Türü", "payment_type", "text", 12),
            ColumnSpec("Kanal", "channel", "text", 18),
            ColumnSpec("Banka", "bank", "text", 18),
            ColumnSpec("Taksit", "installment_count", "int", 10),
            ColumnSpec("Kart Tipi", "card_type", "text", 12),
            ColumnSpec("Bayi İndirimi %", "dealer_discount_percent", "percent", 16),
            ColumnSpec("Komisyon Dönemi", "commission_period", "text", 16),
            ColumnSpec("Komisyon %", "commission_percent", "percent", 12),
            ColumnSpec("Nakit Toplam", "cash_total", "money", 16),
            ColumnSpec("Kart Toplam", "card_total", "money", 16),
            ColumnSpec("Seçili Toplam", "selected_total", "money", 16),
            ColumnSpec("Not", "note", "text", 30),
            ColumnSpec("Rezervasyon No", "reservation_number", "text", 16),
            ColumnSpec("Oluşturan", "created_by", "text", 18),
        ),
        rows=offer_rows,
        instructions=(
            ("Teklif No", "Opsiyonel", "Doluysa yalnızca taslak teklif güncellenir."),
            ("Teklif Anahtarı", "Gruplama", "Yeni tekliflerde satırları gruplamak için kullanılır."),
            ("Ödeme Türü", "Zorunlu", "Nakit veya Kart."),
            ("Kanal / Banka / Taksit / Kart Tipi", "Kartta zorunlu", "POS/Ödero'da banka zorunlu; Chippin'de boş."),
            ("Komisyon / Kâr", "Salt okunur", "Sunucuda yeniden hesaplanır."),
        ),
    )
    item_sheet = SheetSpec(
        title="Teklif Satırları",
        columns=(
            ColumnSpec("Teklif No", "offer_number", "int", 12),
            ColumnSpec("Teklif Anahtarı", "offer_key", "text", 16),
            ColumnSpec("Sıra", "position", "int", 8),
            ColumnSpec("Ürün Adı", "product_name", "text", 34),
            ColumnSpec("Adet", "quantity", "int", 10),
            ColumnSpec("Normal Fiyat", "regular_price", "money", 16),
            ColumnSpec("Oliz Fiyatı", "website_price", "money", 16),
            ColumnSpec("Maliyet", "cost_price", "money", 16),
            ColumnSpec("Kampanya", "campaign", "text", 26),
            ColumnSpec("Hediye Durumu", "gift_present", "bool", 14),
            ColumnSpec("Fiyat Tabanı", "base_price", "money", 16),
            ColumnSpec("Önerilen Nakit", "suggested_cash", "money", 16),
            ColumnSpec("Önerilen Kart", "suggested_card", "money", 16),
            ColumnSpec("Birim Nakit", "unit_cash", "money", 14),
            ColumnSpec("Birim Kart", "unit_card", "money", 14),
            ColumnSpec("Satır Toplam Nakit", "line_total_cash", "money", 18),
            ColumnSpec("Satır Toplam Kart", "line_total_card", "money", 18),
            ColumnSpec("Uyarı", "warning", "text", 30),
        ),
        rows=item_rows,
        instructions=(
            ("Ürün Adı", "Zorunlu", "Mevcut ürünlerden biri olmalıdır."),
            ("Adet", "Zorunlu", "Pozitif tam sayı."),
            ("Kampanya", "Opsiyonel", "Aktif kampanya adı."),
            ("Hediye Durumu", "Opsiyonel", "Evet/Hayır."),
            ("Birim Nakit / Kart", "Opsiyonel", "Boşsa sunucu önerilen fiyatı kullanır."),
        ),
    )
    profit_sheet = SheetSpec(
        title="Kâr Detayı",
        columns=(
            ColumnSpec("Teklif No", "offer_number", "int", 12),
            ColumnSpec("Teklif Anahtarı", "offer_key", "text", 16),
            ColumnSpec("Ürün Adı", "product_name", "text", 34),
            ColumnSpec("Taksit", "installment_count", "int", 10),
            ColumnSpec("Komisyon %", "commission_percent", "percent", 12),
            ColumnSpec("Komisyon Sonrası", "net_after_commission", "money", 18),
            ColumnSpec("Kampanya Hakedişi", "campaign_share", "money", 18),
            ColumnSpec("Oliz Hakedişi", "oliz_share", "money", 16),
            ColumnSpec("Toplam Gelir", "total_revenue", "money", 16),
            ColumnSpec("Maliyet", "cost", "money", 14),
            ColumnSpec("Kâr/Zarar", "profit", "money", 14),
            ColumnSpec("Kâr Marjı %", "margin_percent", "percent", 14),
        ),
        rows=profit_rows,
        instructions=(
            ("Kâr Detayı", "Salt okunur", "Bu sayfa içe aktarmada yok sayılır."),
        ),
    )
    return write_xlsx((offer_sheet, item_sheet, profit_sheet))


def offer_import_template() -> bytes:
    offer_sheet = SheetSpec(
        title="Teklifler",
        columns=(
            ColumnSpec("Teklif No", "offer_number", "int", 12),
            ColumnSpec("Teklif Anahtarı", "offer_key", "text", 16),
            ColumnSpec("Müşteri Adı", "customer_name", "text", 28),
            ColumnSpec("Telefon", "customer_phone", "text", 16),
            ColumnSpec("Ödeme Türü", "payment_type", "text", 12),
            ColumnSpec("Kanal", "channel", "text", 18),
            ColumnSpec("Banka", "bank", "text", 18),
            ColumnSpec("Taksit", "installment_count", "int", 10),
            ColumnSpec("Kart Tipi", "card_type", "text", 12),
            ColumnSpec("Bayi İndirimi %", "dealer_discount_percent", "percent", 16),
            ColumnSpec("Not", "note", "text", 30),
            ColumnSpec("Ürün Adı", "product_name", "text", 34),
            ColumnSpec("Adet", "quantity", "int", 10),
            ColumnSpec("Kampanya", "campaign", "text", 26),
            ColumnSpec("Hediye Durumu", "gift_present", "bool", 14),
            ColumnSpec("Nakit Birim Fiyat", "unit_price_cash", "money", 16),
            ColumnSpec("Kart Birim Fiyat", "unit_price_card", "money", 16),
        ),
        rows=(),
        instructions=(
            ("Teklif Anahtarı", "Gruplama", "Yeni tekliflerde satırları gruplamak için zorunlu."),
            ("Müşteri Adı", "Zorunlu", "Teklif müşterisi."),
            ("Ödeme Türü", "Zorunlu", "Nakit veya Kart."),
            ("Ürün Adı", "Zorunlu", "Mevcut ürünlerden biri."),
            ("Adet", "Zorunlu", "Pozitif tam sayı."),
            ("Kampanya", "Opsiyonel", "Aktif kampanya adı."),
            ("Hediye Durumu", "Opsiyonel", "Evet/Hayır."),
            ("Kâr / Komisyon", "Salt okunur", "Sunucuda yeniden hesaplanır."),
        ),
    )
    return write_xlsx((offer_sheet,))
