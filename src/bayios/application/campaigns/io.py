from __future__ import annotations

import uuid
from datetime import UTC, datetime

from bayios.application.errors import NotFoundError
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.tabular import ColumnSpec, SheetSpec, write_xlsx
from bayios.domain.campaigns import (
    BASE_PRICE_TYPE_LABELS,
    CAMPAIGN_STATE_LABELS,
    CAMPAIGN_TYPE_LABELS,
    DISCOUNT_TYPE_LABELS,
    PRODUCT_RELATION_TYPE_LABELS,
    BasePriceType,
    CampaignType,
    DiscountType,
    ProductRelationType,
    classify_campaign,
)


def export_campaigns_xlsx(
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

    campaign_rows: list[dict[str, object]] = []
    product_rows: list[dict[str, object]] = []
    for campaign, version in rows:
        state_value = classify_campaign(
            starts_at=version.starts_at,
            ends_at=version.ends_at,
            archived=campaign.is_archived,
            as_of=now,
        )
        campaign_rows.append(
            {
                "campaign_id": str(campaign.id),
                "name": version.name,
                "description": version.description or "",
                "campaign_type": CAMPAIGN_TYPE_LABELS[
                    CampaignType(version.campaign_type)
                ],
                "starts_at": version.starts_at.date(),
                "ends_at": version.ends_at.date(),
                "base_price_type": BASE_PRICE_TYPE_LABELS[
                    BasePriceType(version.base_price_type)
                ],
                "discount_type": DISCOUNT_TYPE_LABELS[
                    DiscountType(version.discount_type)
                ],
                "discount_value": version.discount_value,
                "gift_description": version.gift_description or "",
                "gift_optional": version.gift_optional,
                "gift_yes_base_price_type": (
                    BASE_PRICE_TYPE_LABELS[
                        BasePriceType(version.gift_yes_base_price_type)
                    ]
                    if version.gift_yes_base_price_type
                    else ""
                ),
                "gift_no_base_price_type": (
                    BASE_PRICE_TYPE_LABELS[
                        BasePriceType(version.gift_no_base_price_type)
                    ]
                    if version.gift_no_base_price_type
                    else ""
                ),
                "employee_note": version.employee_note or "",
                "state": CAMPAIGN_STATE_LABELS[state_value],
                "version_no": version.version_no,
                "archived": campaign.is_archived,
            }
        )
        for link in links_by_version.get(version.id, ()):
            product_rows.append(
                {
                    "campaign_id": str(campaign.id),
                    "campaign_name": version.name,
                    "starts_at": version.starts_at.date(),
                    "ends_at": version.ends_at.date(),
                    "product_name": link.product_name_snapshot,
                    "relation_type": PRODUCT_RELATION_TYPE_LABELS[
                        ProductRelationType(link.relation_type)
                    ],
                    "quantity_required": link.quantity_required,
                }
            )

    campaign_sheet = SheetSpec(
        title="Kampanyalar",
        columns=(
            ColumnSpec("Kampanya ID", "campaign_id", "text", 38),
            ColumnSpec("Kampanya Adı", "name", "text", 32),
            ColumnSpec("Açıklama", "description", "text", 40),
            ColumnSpec("Kampanya Tipi", "campaign_type", "text", 16),
            ColumnSpec("Başlangıç Tarihi", "starts_at", "date", 16),
            ColumnSpec("Bitiş Tarihi", "ends_at", "date", 16),
            ColumnSpec("Fiyat Tabanı", "base_price_type", "text", 20),
            ColumnSpec("İndirim Türü", "discount_type", "text", 16),
            ColumnSpec("İndirim Değeri", "discount_value", "money", 16),
            ColumnSpec("Hediye Açıklaması", "gift_description", "text", 28),
            ColumnSpec("Hediye İsteğe Bağlı", "gift_optional", "bool", 18),
            ColumnSpec("Hediye Varsa Taban", "gift_yes_base_price_type", "text", 20),
            ColumnSpec("Hediye Yoksa Taban", "gift_no_base_price_type", "text", 20),
            ColumnSpec("Çalışan Notu", "employee_note", "text", 32),
            ColumnSpec("Durum", "state", "text", 14),
            ColumnSpec("Sürüm No", "version_no", "int", 10),
            ColumnSpec("Arşivde", "archived", "bool", 10),
        ),
        rows=campaign_rows,
        instructions=(
            ("Kampanya Adı", "Zorunlu", "Kampanya kimliği."),
            ("Başlangıç Tarihi", "Zorunlu", "GG.AA.YYYY veya ISO tarih."),
            ("Bitiş Tarihi", "Zorunlu", "Başlangıçtan önce olamaz."),
            ("Kampanya Tipi", "Opsiyonel", "Genel, Ürün indirimi, Birlikte alım, Hediye, Kupon, Özel."),
            ("İndirim Türü", "Opsiyonel", "Yüzde, Sabit tutar, Özel fiyat, Hediye, Sadece bilgi."),
            ("Ürün İlişkisi", "Kampanya Ürünleri", "Şart ürünü, Fayda ürünü, Hediye ürünü, İlgili ürün."),
            ("Kampanya ID", "Salt okunur", "Doluysa güncelleme bu kimlikle eşleşir."),
            ("Durum / Sürüm No / Arşivde", "Salt okunur", "İçe aktarmada kullanılmaz."),
        ),
    )
    product_sheet = SheetSpec(
        title="Kampanya Ürünleri",
        columns=(
            ColumnSpec("Kampanya ID", "campaign_id", "text", 38),
            ColumnSpec("Kampanya Adı", "campaign_name", "text", 32),
            ColumnSpec("Başlangıç Tarihi", "starts_at", "date", 16),
            ColumnSpec("Bitiş Tarihi", "ends_at", "date", 16),
            ColumnSpec("Ürün Adı", "product_name", "text", 34),
            ColumnSpec("İlişki Türü", "relation_type", "text", 20),
            ColumnSpec("Gerekli Adet", "quantity_required", "int", 14),
        ),
        rows=product_rows,
        instructions=(
            ("Ürün Adı", "Zorunlu", "Mevcut ürünlerden biri olmalıdır."),
            ("İlişki Türü", "Zorunlu", "Şart ürünü, Fayda ürünü, Hediye ürünü, İlgili ürün."),
            ("Gerekli Adet", "Opsiyonel", "Pozitif tam sayı."),
        ),
    )
    return write_xlsx((campaign_sheet, product_sheet))


def campaign_import_template() -> bytes:
    campaign_sheet = SheetSpec(
        title="Kampanyalar",
        columns=(
            ColumnSpec("Kampanya ID", "campaign_id", "text", 38),
            ColumnSpec("Kampanya Adı", "name", "text", 32),
            ColumnSpec("Açıklama", "description", "text", 40),
            ColumnSpec("Kampanya Tipi", "campaign_type", "text", 16),
            ColumnSpec("Başlangıç Tarihi", "starts_at", "date", 16),
            ColumnSpec("Bitiş Tarihi", "ends_at", "date", 16),
            ColumnSpec("Fiyat Tabanı", "base_price_type", "text", 20),
            ColumnSpec("İndirim Türü", "discount_type", "text", 16),
            ColumnSpec("İndirim Değeri", "discount_value", "money", 16),
            ColumnSpec("Hediye Açıklaması", "gift_description", "text", 28),
            ColumnSpec("Hediye İsteğe Bağlı", "gift_optional", "bool", 18),
            ColumnSpec("Hediye Varsa Taban", "gift_yes_base_price_type", "text", 20),
            ColumnSpec("Hediye Yoksa Taban", "gift_no_base_price_type", "text", 20),
            ColumnSpec("Çalışan Notu", "employee_note", "text", 32),
        ),
        rows=(),
        instructions=(
            ("Kampanya Adı", "Zorunlu", "Kampanya kimliği."),
            ("Başlangıç Tarihi", "Zorunlu", "GG.AA.YYYY veya ISO tarih."),
            ("Bitiş Tarihi", "Zorunlu", "Başlangıçtan önce olamaz."),
            ("Kampanya Tipi", "Opsiyonel", "Genel, Ürün indirimi, Birlikte alım, Hediye, Kupon, Özel."),
            ("İndirim Türü", "Opsiyonel", "Yüzde, Sabit tutar, Özel fiyat, Hediye, Sadece bilgi."),
        ),
    )
    product_sheet = SheetSpec(
        title="Kampanya Ürünleri",
        columns=(
            ColumnSpec("Kampanya ID", "campaign_id", "text", 38),
            ColumnSpec("Kampanya Adı", "campaign_name", "text", 32),
            ColumnSpec("Başlangıç Tarihi", "starts_at", "date", 16),
            ColumnSpec("Bitiş Tarihi", "ends_at", "date", 16),
            ColumnSpec("Ürün Adı", "product_name", "text", 34),
            ColumnSpec("İlişki Türü", "relation_type", "text", 20),
            ColumnSpec("Gerekli Adet", "quantity_required", "int", 14),
        ),
        rows=(),
        instructions=(
            ("Ürün Adı", "Zorunlu", "Mevcut ürünlerden biri olmalıdır."),
            ("İlişki Türü", "Zorunlu", "Şart ürünü, Fayda ürünü, Hediye ürünü, İlgili ürün."),
            ("Gerekli Adet", "Opsiyonel", "Pozitif tam sayı."),
        ),
    )
    return write_xlsx((campaign_sheet, product_sheet))


def export_campaign_products_xlsx(
    uow: UnitOfWork, campaign_id: uuid.UUID
) -> bytes:
    """Export only the product relations of one campaign for bulk editing."""
    with uow:
        campaign = uow.campaigns.get(campaign_id)
        version = uow.campaigns.get_current_version(campaign_id)
        if campaign is None or version is None:
            raise NotFoundError("Kampanya bulunamadı.")
        links = uow.campaigns.get_version_products(version.id)

    rows = tuple(
        {
            "product_name": link.product_name_snapshot,
            "relation_type": PRODUCT_RELATION_TYPE_LABELS[
                ProductRelationType(link.relation_type)
            ],
            "quantity_required": link.quantity_required,
        }
        for link in links
    )
    sheet = SheetSpec(
        title="Kampanya Ürünleri",
        columns=(
            ColumnSpec("Ürün Adı", "product_name", "text", 38),
            ColumnSpec("İlişki Türü", "relation_type", "text", 22),
            ColumnSpec("Gerekli Adet", "quantity_required", "int", 14),
        ),
        rows=rows,
        instructions=(
            ("Ürün Adı", "Zorunlu", "Mevcut ürünlerden biri olmalıdır."),
            ("İlişki Türü", "Zorunlu", "Şart ürünü, Fayda ürünü, Hediye ürünü, İlgili ürün."),
            ("Gerekli Adet", "Opsiyonel", "Pozitif tam sayı."),
            ("Toplu giriş", "Bilgi", "Yeni ürün satırlarını ekleyip aynı dosyayı detaydan içe aktarabilirsiniz."),
        ),
    )
    return write_xlsx((sheet,), include_instructions=True)
