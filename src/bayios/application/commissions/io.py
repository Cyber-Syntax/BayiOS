from __future__ import annotations

import uuid

from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.application.tabular import ColumnSpec, SheetSpec, write_xlsx
from bayios.domain.commissions import (
    CARD_TYPE_LABELS,
    CHANNEL_LABELS,
    ODERO_TIER_LABELS,
    PRODUCT_GROUP_LABELS,
    CardType,
    OderoTier,
    PaymentChannel,
    ProductCommissionGroup,
)


def export_commission_rates_xlsx(
    uow: UnitOfWork, *, period_id: uuid.UUID | None = None
) -> bytes:
    with uow:
        periods = (
            [uow.commissions.get_period(period_id)]
            if period_id is not None
            else list(uow.commissions.list_periods())
        )
        periods = [period for period in periods if period is not None]
        bank_names = {
            str(bank.id): bank.name for bank in uow.commissions.get_banks(active_only=False)
        }
        rows = [
            {
                "period": period.period_key,
                "channel": CHANNEL_LABELS.get(PaymentChannel(rate.channel), rate.channel),
                "bank": bank_names.get(str(rate.bank_id), ""),
                "product_group": PRODUCT_GROUP_LABELS.get(
                    ProductCommissionGroup(rate.product_group), ""
                )
                if rate.product_group
                else "",
                "amount_tier": ODERO_TIER_LABELS.get(
                    OderoTier(rate.amount_tier), ""
                )
                if rate.amount_tier
                else "",
                "installment_count": rate.installment_count,
                "commission_percent": rate.commission_percent,
            }
            for period in periods
            for rate in uow.commissions.get_rates(period.id)
        ]
    sheet = SheetSpec(
        title="Komisyon Oranları",
        columns=(
            ColumnSpec("Dönem", "period", "text", 12),
            ColumnSpec("Kanal", "channel", "text", 18),
            ColumnSpec("Banka", "bank", "text", 20),
            ColumnSpec("Ürün Grubu", "product_group", "text", 14),
            ColumnSpec("Ödero Bandı", "amount_tier", "text", 22),
            ColumnSpec("Taksit", "installment_count", "int", 10),
            ColumnSpec("Oran %", "commission_percent", "percent", 12),
        ),
        rows=rows,
        instructions=(
            ("Dönem", "Zorunlu", "YYYY-MM."),
            ("Kanal", "Zorunlu", "POS, Ödero veya Chippin."),
            ("Banka", "POS/Ödero zorunlu", "Chippin'de boş."),
            ("Ürün Grubu", "POS/Ödero zorunlu", "Klima, TV veya Diğer."),
            ("Taksit", "Zorunlu", "Pozitif tam sayı."),
            ("Oran %", "Zorunlu", "0-100."),
        ),
    )
    return write_xlsx((sheet,))


def export_commission_limits_xlsx(
    uow: UnitOfWork, *, period_id: uuid.UUID | None = None
) -> bytes:
    with uow:
        periods = (
            [uow.commissions.get_period(period_id)]
            if period_id is not None
            else list(uow.commissions.list_periods())
        )
        periods = [period for period in periods if period is not None]
        bank_names = {
            str(bank.id): bank.name for bank in uow.commissions.get_banks(active_only=False)
        }
        rows = [
            {
                "period": period.period_key,
                "channel": CHANNEL_LABELS.get(PaymentChannel(limit.channel), "")
                if limit.channel
                else "",
                "bank": bank_names.get(str(limit.bank_id), ""),
                "product_group": PRODUCT_GROUP_LABELS.get(
                    ProductCommissionGroup(limit.product_group), ""
                )
                if limit.product_group
                else "",
                "card_type": CARD_TYPE_LABELS.get(
                    CardType(limit.card_type), ""
                )
                if limit.card_type
                else "",
                "max_installments": limit.max_installments,
            }
            for period in periods
            for limit in uow.commissions.get_limits(period.id)
        ]
    sheet = SheetSpec(
        title="Taksit Limitleri",
        columns=(
            ColumnSpec("Dönem", "period", "text", 12),
            ColumnSpec("Kanal", "channel", "text", 18),
            ColumnSpec("Banka", "bank", "text", 20),
            ColumnSpec("Ürün Grubu", "product_group", "text", 14),
            ColumnSpec("Kart Tipi", "card_type", "text", 12),
            ColumnSpec("Max Taksit", "max_installments", "int", 12),
        ),
        rows=rows,
        instructions=(
            ("Dönem", "Zorunlu", "YYYY-MM."),
            ("Kanal", "Opsiyonel", "POS, Ödero veya Chippin."),
            ("Banka", "Opsiyonel", "Chippin'de boş."),
            ("Ürün Grubu", "Opsiyonel", "Klima, TV veya Diğer."),
            ("Kart Tipi", "Opsiyonel", "Bireysel veya Business."),
            ("Max Taksit", "Zorunlu", "Pozitif tam sayı."),
        ),
    )
    return write_xlsx((sheet,))


def commission_rates_template() -> bytes:
    sheet = SheetSpec(
        title="Komisyon Oranları",
        columns=(
            ColumnSpec("Dönem", "period", "text", 12),
            ColumnSpec("Kanal", "channel", "text", 18),
            ColumnSpec("Banka", "bank", "text", 20),
            ColumnSpec("Ürün Grubu", "product_group", "text", 14),
            ColumnSpec("Ödero Bandı", "amount_tier", "text", 22),
            ColumnSpec("Taksit", "installment_count", "int", 10),
            ColumnSpec("Oran %", "commission_percent", "percent", 12),
        ),
        rows=(),
        instructions=(
            ("Dönem", "Zorunlu", "YYYY-MM; yoksa taslak dönem oluşturulur."),
            ("Kanal", "Zorunlu", "POS, Ödero veya Chippin."),
            ("Banka", "POS/Ödero zorunlu", "Chippin'de boş."),
            ("Ürün Grubu", "POS/Ödero zorunlu", "Klima, TV veya Diğer."),
            ("Taksit", "Zorunlu", "Pozitif tam sayı."),
            ("Oran %", "Zorunlu", "0-100."),
        ),
    )
    return write_xlsx((sheet,))


def commission_limits_template() -> bytes:
    sheet = SheetSpec(
        title="Taksit Limitleri",
        columns=(
            ColumnSpec("Dönem", "period", "text", 12),
            ColumnSpec("Kanal", "channel", "text", 18),
            ColumnSpec("Banka", "bank", "text", 20),
            ColumnSpec("Ürün Grubu", "product_group", "text", 14),
            ColumnSpec("Kart Tipi", "card_type", "text", 12),
            ColumnSpec("Max Taksit", "max_installments", "int", 12),
        ),
        rows=(),
        instructions=(
            ("Dönem", "Zorunlu", "YYYY-MM; yoksa taslak dönem oluşturulur."),
            ("Kanal", "Opsiyonel", "POS, Ödero veya Chippin."),
            ("Banka", "Opsiyonel", "Chippin'de boş."),
            ("Ürün Grubu", "Opsiyonel", "Klima, TV veya Diğer."),
            ("Kart Tipi", "Opsiyonel", "Bireysel veya Business."),
            ("Max Taksit", "Zorunlu", "Pozitif tam sayı."),
        ),
    )
    return write_xlsx((sheet,))
