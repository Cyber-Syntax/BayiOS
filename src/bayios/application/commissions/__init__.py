from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from bayios.adapters.db.models.commissions import (
    Bank,
    CommissionLimit,
    CommissionPeriod,
    CommissionRate,
    ProfitTarget,
)
from bayios.application.errors import NotFoundError, ValidationError
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.domain.commissions import (
    ODERO_TIER_LABELS,
    CardType,
    CommissionPeriodStatus,
    OderoTier,
    PaymentChannel,
    ProductCommissionGroup,
    commission_percent_for,
    effective_max_installments,
    odero_tier,
    period_bounds,
    validate_period,
)
from bayios.domain.commissions import (
    CommissionLimit as DomainLimit,
)
from bayios.domain.commissions import (
    CommissionRate as DomainRate,
)
from bayios.domain.products import ActorContext


@dataclass(frozen=True)
class CommissionPeriodDetail:
    period: CommissionPeriod
    rates: tuple[CommissionRate, ...]
    limits: tuple[CommissionLimit, ...]
    banks: tuple[Bank, ...]


@dataclass(frozen=True)
class CommissionResolution:
    period: CommissionPeriod
    commission_percent: Decimal
    max_installments: int
    options: tuple[tuple[int, Decimal], ...] = ()


@dataclass(frozen=True)
class CommissionRateInput:
    channel: PaymentChannel
    bank_id: uuid.UUID | None
    product_group: ProductCommissionGroup | None
    installment_count: int
    commission_percent: Decimal
    amount_tier: OderoTier | None = None


def list_commission_periods(uow: UnitOfWork) -> Sequence[CommissionPeriod]:
    with uow:
        return uow.commissions.list_periods()


def list_banks(uow: UnitOfWork) -> Sequence[Bank]:
    with uow:
        return uow.commissions.get_banks()


def get_commission_period_detail(
    uow: UnitOfWork, period_id: uuid.UUID
) -> CommissionPeriodDetail | None:
    with uow:
        period = uow.commissions.get_period(period_id)
        if period is None:
            return None
        return CommissionPeriodDetail(
            period=period,
            rates=tuple(uow.commissions.get_rates(period_id)),
            limits=tuple(uow.commissions.get_limits(period_id)),
            banks=tuple(uow.commissions.get_banks()),
        )


def create_commission_period(
    uow: UnitOfWork,
    year: int,
    month: int,
    *,
    copy_from_id: uuid.UUID | None = None,
    actor: ActorContext | None = None,
) -> CommissionPeriod:
    actor = actor or ActorContext()
    start, end = period_bounds(year, month)
    key = f"{year:04d}-{month:02d}"
    with uow:
        if uow.commissions.get_period_by_key(key) is not None:
            raise ValidationError(f"{key} dönemi zaten mevcut.")
        source = None
        if copy_from_id is not None:
            source = uow.commissions.get_period(copy_from_id)
            if source is None:
                raise NotFoundError("Kopyalanacak komisyon dönemi bulunamadı.")
        period = CommissionPeriod(
            id=uuid.uuid4(),
            period_key=key,
            valid_from=start,
            valid_until=end,
            status=CommissionPeriodStatus.DRAFT.value,
            copied_from_id=copy_from_id,
            created_at=datetime.now(UTC),
            created_by_name=actor.worker_name,
            created_by_device=actor.device_name,
        )
        try:
            validate_period(
                period_key=key,
                valid_from=start,
                valid_until=end,
                status=CommissionPeriodStatus.DRAFT,
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        uow.commissions.add_period(period)
        if source is not None:
            _copy_period(uow, source, period)
        uow.commit()
        return period


def activate_commission_period(
    uow: UnitOfWork, period_id: uuid.UUID
) -> CommissionPeriod:
    with uow:
        period = uow.commissions.get_period(period_id)
        if period is None:
            raise NotFoundError("Komisyon dönemi bulunamadı.")
        if period.status == "archived":
            raise ValidationError("Arşivlenmiş dönem aktifleştirilemez.")
        uow.commissions.set_period_status(period_id, "active")
        uow.commit()
        return period


def deactivate_commission_period(
    uow: UnitOfWork, period_id: uuid.UUID
) -> CommissionPeriod:
    with uow:
        period = uow.commissions.get_period(period_id)
        if period is None:
            raise NotFoundError("Komisyon dönemi bulunamadı.")
        if period.status == "archived":
            raise ValidationError("Arşivlenmiş dönem pasifleştirilemez.")
        uow.commissions.set_period_status(period_id, "inactive")
        uow.commit()
        return period


def delete_commission_period(uow: UnitOfWork, period_id: uuid.UUID) -> None:
    with uow:
        period = uow.commissions.get_period(period_id)
        if period is None:
            raise NotFoundError("Komisyon dönemi bulunamadı.")
        uow.commissions.delete_period(period_id)
        uow.commit()


def update_commission_rates(
    uow: UnitOfWork,
    period_id: uuid.UUID,
    rates: Sequence[CommissionRateInput],
) -> None:
    with uow:
        period = uow.commissions.get_period(period_id)
        if period is None:
            raise NotFoundError("Komisyon dönemi bulunamadı.")
        if period.status == "archived":
            raise ValidationError("Arşivlenmiş dönem düzenlenemez.")
        uow.commissions.delete_rates(period_id)
        seen: set[str] = set()
        for item in rates:
            try:
                domain_rate = DomainRate(
                    channel=item.channel,
                    bank_id=str(item.bank_id) if item.bank_id else None,
                    product_group=item.product_group,
                    installment_count=item.installment_count,
                    commission_percent=item.commission_percent,
                    amount_tier=item.amount_tier,
                )
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            if domain_rate.scope_key in seen:
                raise ValidationError("Aynı komisyon satırı birden fazla kez girilemez.")
            seen.add(domain_rate.scope_key)
            uow.commissions.add_rate(
                CommissionRate(
                    id=uuid.uuid4(),
                    period_id=period_id,
                    channel=domain_rate.channel.value,
                    bank_id=item.bank_id,
                    product_group=(
                        domain_rate.product_group.value
                        if domain_rate.product_group
                        else None
                    ),
                    amount_tier=(
                        domain_rate.amount_tier.value
                        if domain_rate.amount_tier
                        else None
                    ),
                    installment_count=domain_rate.installment_count,
                    commission_percent=domain_rate.commission_percent,
                    scope_key=domain_rate.scope_key,
                )
            )
        uow.commit()


def update_commission_limits(
    uow: UnitOfWork,
    period_id: uuid.UUID,
    limits: Sequence[object],
) -> None:
    with uow:
        period = uow.commissions.get_period(period_id)
        if period is None:
            raise NotFoundError("Komisyon dönemi bulunamadı.")
        if period.status == "archived":
            raise ValidationError("Arşivlenmiş dönem düzenlenemez.")
        uow.commissions.delete_limits(period_id)
        for limit in limits:
            uow.commissions.add_limit(limit)
        uow.commit()


def resolve_commission(
    uow: UnitOfWork,
    *,
    channel: PaymentChannel,
    bank_id: uuid.UUID | None,
    product_group: ProductCommissionGroup,
    card_type: CardType,
    installment_count: int,
    total: Decimal,
    as_of: datetime | None = None,
) -> CommissionResolution:
    with uow:
        period = uow.commissions.get_active_period(as_of or datetime.now(UTC))
        if period is None:
            raise ValidationError("Aktif komisyon dönemi tanımlı değil.")
        rates = _domain_rates(uow.commissions.get_rates(period.id))
        limits = _domain_limits(uow.commissions.get_limits(period.id))
        maximum = effective_max_installments(
            rates,
            limits,
            channel=channel,
            bank_id=str(bank_id) if bank_id else None,
            product_group=product_group,
            card_type=card_type,
            total=total,
        )
        if maximum == 0:
            tier = (
                odero_tier(total)
                if channel is PaymentChannel.ODERO
                else None
            )
            tier_text = (
                f" ({ODERO_TIER_LABELS[tier]})" if tier is not None else ""
            )
            raise ValidationError(
                "Seçilen kanal, banka ve ürün grubu"
                f"{tier_text} için komisyon oranı tanımlı değil. "
                "Komisyonlar ekranından ilgili banda oran ekleyin."
            )
        if installment_count > maximum:
            raise ValidationError(
                f"Seçilen taksit bu ödeme için geçersiz; en fazla {maximum} taksit olabilir."
            )
        percent = commission_percent_for(
            rates,
            channel=channel,
            bank_id=str(bank_id) if bank_id else None,
            product_group=product_group,
            installment_count=installment_count,
            total=total,
        )
        if percent is None:
            raise ValidationError(
                "Seçilen kanal, banka, ürün grubu ve taksit için komisyon tanımlı değil."
            )
        options = tuple(
            (installment, option_percent)
            for installment in range(1, maximum + 1)
            if (
                option_percent := commission_percent_for(
                    rates,
                    channel=channel,
                    bank_id=str(bank_id) if bank_id else None,
                    product_group=product_group,
                    installment_count=installment,
                    total=total,
                )
            )
            is not None
        )
        return CommissionResolution(
            period=period,
            commission_percent=percent,
            max_installments=maximum,
            options=options,
        )


def get_profit_target(
    uow: UnitOfWork,
    *,
    product_id: uuid.UUID | None,
    as_of: datetime | None = None,
) -> ProfitTarget | None:
    reference = as_of or datetime.now(UTC)
    with uow:
        if product_id is not None:
            target = uow.commissions.get_profit_target(
                scope_type="product", scope_id=product_id, as_of=reference
            )
            if target is not None:
                return target
        return uow.commissions.get_profit_target(
            scope_type="global", scope_id=None, as_of=reference
        )


def set_category_commission_group(
    uow: UnitOfWork, category_id: uuid.UUID, commission_group: str
) -> None:
    with uow:
        if commission_group not in {"klima", "tv", "other"}:
            raise ValidationError("Geçersiz komisyon grubu.")
        uow.commissions.set_category_group(category_id, commission_group)
        uow.commit()


def add_commission_rate(
    uow: UnitOfWork,
    period_id: uuid.UUID,
    item: CommissionRateInput,
) -> None:
    with uow:
        period = uow.commissions.get_period(period_id)
        if period is None:
            raise NotFoundError("Komisyon dönemi bulunamadı.")
        if period.status == "archived":
            raise ValidationError("Arşivlenmiş döneme oran eklenemez.")
        try:
            domain_rate = DomainRate(
                channel=item.channel,
                bank_id=str(item.bank_id) if item.bank_id else None,
                product_group=item.product_group,
                installment_count=item.installment_count,
                commission_percent=item.commission_percent,
                amount_tier=item.amount_tier,
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        existing_scope_keys = {
            rate.scope_key for rate in uow.commissions.get_rates(period_id)
        }
        if domain_rate.scope_key in existing_scope_keys:
            raise ValidationError(
                "Bu komisyon oranı bu dönem için zaten tanımlı. "
                "Mevcut satırı düzenleyin."
            )
        uow.commissions.add_rate(
            CommissionRate(
                id=uuid.uuid4(),
                period_id=period_id,
                channel=domain_rate.channel.value,
                bank_id=item.bank_id,
                product_group=(
                    domain_rate.product_group.value
                    if domain_rate.product_group
                    else None
                ),
                amount_tier=(
                    domain_rate.amount_tier.value
                    if domain_rate.amount_tier
                    else None
                ),
                installment_count=domain_rate.installment_count,
                commission_percent=domain_rate.commission_percent,
                scope_key=domain_rate.scope_key,
            )
        )
        try:
            uow.commit()
        except IntegrityError as exc:
            raise ValidationError(
                "Bu komisyon oranı bu dönem için zaten tanımlı."
            ) from exc


def add_commission_limit(
    uow: UnitOfWork,
    period_id: uuid.UUID,
    limit: DomainLimit,
) -> None:
    with uow:
        period = uow.commissions.get_period(period_id)
        if period is None:
            raise NotFoundError("Komisyon dönemi bulunamadı.")
        if period.status == "archived":
            raise ValidationError("Arşivlenmiş döneme limit eklenemez.")
        existing_scope_keys = {
            existing.scope_key
            for existing in uow.commissions.get_limits(period_id)
        }
        if limit.scope_key in existing_scope_keys:
            raise ValidationError(
                "Bu taksit limiti bu dönem için zaten tanımlı. "
                "Mevcut satırı düzenleyin."
            )
        uow.commissions.add_limit(
            CommissionLimit(
                id=uuid.uuid4(),
                period_id=period_id,
                channel=limit.channel.value if limit.channel else None,
                bank_id=uuid.UUID(limit.bank_id) if limit.bank_id else None,
                product_group=(
                    limit.product_group.value if limit.product_group else None
                ),
                card_type=limit.card_type.value if limit.card_type else None,
                max_installments=limit.max_installments,
                scope_key=limit.scope_key,
            )
        )
        try:
            uow.commit()
        except IntegrityError as exc:
            raise ValidationError(
                "Bu taksit limiti bu dönem için zaten tanımlı."
            ) from exc


def update_commission_rate(
    uow: UnitOfWork,
    period_id: uuid.UUID,
    rate_id: uuid.UUID,
    commission_percent: Decimal,
) -> None:
    if not (Decimal(0) <= commission_percent <= Decimal(100)):
        raise ValidationError("Komisyon oranı %0 ile %100 arasında olmalıdır.")
    with uow:
        period = uow.commissions.get_period(period_id)
        if period is None:
            raise NotFoundError("Komisyon dönemi bulunamadı.")
        if period.status == "archived":
            raise ValidationError("Arşivlenmiş dönem düzenlenemez.")
        rate = uow.commissions.get_rate(rate_id)
        if rate is None or rate.period_id != period_id:
            raise NotFoundError("Komisyon oranı bulunamadı.")
        uow.commissions.update_rate(rate_id, commission_percent)
        uow.commit()


def delete_commission_rate(
    uow: UnitOfWork,
    period_id: uuid.UUID,
    rate_id: uuid.UUID,
) -> None:
    with uow:
        period = uow.commissions.get_period(period_id)
        if period is None:
            raise NotFoundError("Komisyon dönemi bulunamadı.")
        rate = uow.commissions.get_rate(rate_id)
        if rate is None or rate.period_id != period_id:
            raise NotFoundError("Komisyon oranı bulunamadı.")
        uow.commissions.delete_rate(rate_id)
        uow.commit()


def update_commission_limit(
    uow: UnitOfWork,
    period_id: uuid.UUID,
    limit_id: uuid.UUID,
    max_installments: int,
) -> None:
    if max_installments <= 0:
        raise ValidationError("Taksit limiti sıfırdan büyük olmalıdır.")
    with uow:
        period = uow.commissions.get_period(period_id)
        if period is None:
            raise NotFoundError("Komisyon dönemi bulunamadı.")
        if period.status == "archived":
            raise ValidationError("Arşivlenmiş dönem düzenlenemez.")
        limit = uow.commissions.get_limit(limit_id)
        if limit is None or limit.period_id != period_id:
            raise NotFoundError("Taksit limiti bulunamadı.")
        uow.commissions.update_limit(limit_id, max_installments)
        uow.commit()


def delete_commission_limit(
    uow: UnitOfWork,
    period_id: uuid.UUID,
    limit_id: uuid.UUID,
) -> None:
    with uow:
        period = uow.commissions.get_period(period_id)
        if period is None:
            raise NotFoundError("Komisyon dönemi bulunamadı.")
        limit = uow.commissions.get_limit(limit_id)
        if limit is None or limit.period_id != period_id:
            raise NotFoundError("Taksit limiti bulunamadı.")
        uow.commissions.delete_limit(limit_id)
        uow.commit()


def _copy_period(
    uow: UnitOfWork,
    source: CommissionPeriod,
    target: CommissionPeriod,
) -> None:
    for rate in uow.commissions.get_rates(source.id):
        uow.commissions.add_rate(
            CommissionRate(
                id=uuid.uuid4(),
                period_id=target.id,
                channel=rate.channel,
                bank_id=rate.bank_id,
                product_group=rate.product_group,
                amount_tier=rate.amount_tier,
                installment_count=rate.installment_count,
                commission_percent=rate.commission_percent,
                scope_key=rate.scope_key,
            )
        )
    for limit in uow.commissions.get_limits(source.id):
        uow.commissions.add_limit(
            CommissionLimit(
                id=uuid.uuid4(),
                period_id=target.id,
                channel=limit.channel,
                bank_id=limit.bank_id,
                product_group=limit.product_group,
                card_type=limit.card_type,
                max_installments=limit.max_installments,
                scope_key=limit.scope_key,
            )
        )


def _domain_rates(rows: Sequence[CommissionRate]) -> list[DomainRate]:
    return [
        DomainRate(
            channel=PaymentChannel(row.channel),
            bank_id=str(row.bank_id) if row.bank_id else None,
            product_group=(
                ProductCommissionGroup(row.product_group)
                if row.product_group
                else None
            ),
            installment_count=row.installment_count,
            commission_percent=row.commission_percent,
            amount_tier=OderoTier(row.amount_tier) if row.amount_tier else None,
        )
        for row in rows
    ]


def _domain_limits(rows: Sequence[CommissionLimit]) -> list[DomainLimit]:
    return [
        DomainLimit(
            max_installments=row.max_installments,
            channel=PaymentChannel(row.channel) if row.channel else None,
            bank_id=str(row.bank_id) if row.bank_id else None,
            product_group=(
                ProductCommissionGroup(row.product_group)
                if row.product_group
                else None
            ),
            card_type=CardType(row.card_type) if row.card_type else None,
        )
        for row in rows
    ]
