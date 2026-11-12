from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from types import TracebackType
from typing import Self

from bayios.adapters.db.models.campaigns import (
    Campaign,
    CampaignVersion,
    CampaignVersionProduct,
    DealerDiscountSetting,
    DealerDiscountSettingHistory,
    DealerPricing,
    DealerPricingHistory,
)
from bayios.adapters.db.models.imports import DataImportBatch
from bayios.adapters.db.models.inventory import (
    StockCountItem,
    StockCountSession,
    StockMovement,
)
from bayios.adapters.db.models.products import (
    Product,
    ProductCategory,
    ProductImportBatch,
    ProductPriceHistory,
)
from bayios.adapters.db.models.reservations import (
    Reservation,
    ReservationItem,
    ReservationItemEvent,
    ReservationReminder,
)
from bayios.application.ports.campaigns import ActiveCampaignLink
from bayios.domain.products import normalize_product_name


class FakeProductRepository:
    def __init__(self) -> None:
        self.products: dict[uuid.UUID, Product] = {}
        self.categories: dict[uuid.UUID, ProductCategory] = {}
        self.price_history: list[ProductPriceHistory] = []
        self.stock_movements: list[StockMovement] = []
        self.import_batches: list[ProductImportBatch] = []

    def search(
        self,
        query: str | None = None,
        category_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
        only_archived: bool = False,
    ) -> tuple[Sequence[Product], int]:
        results = list(self.products.values())
        if only_archived:
            results = [p for p in results if getattr(p, "is_archived", False)]
        elif not include_archived:
            results = [p for p in results if not getattr(p, "is_archived", False)]

        if category_id is not None:
            results = [p for p in results if p.category_id == category_id]

        if query and query.strip():
            normalized = normalize_product_name(query)
            clean = query.strip().lower()
            results = [
                p
                for p in results
                if normalized in p.name_normalized or clean in p.name.lower()
            ]
        results.sort(key=lambda p: p.name)
        total = len(results)
        return results[offset : offset + limit], total

    def get_by_id(self, product_id: uuid.UUID) -> Product | None:
        return self.products.get(product_id)

    def get_by_ids(self, product_ids: Sequence[uuid.UUID]) -> Sequence[Product]:
        target = set(product_ids)
        return [p for p in self.products.values() if p.id in target]

    def set_archived(self, product_ids: Sequence[uuid.UUID], archived: bool = True) -> int:
        count = 0
        for pid in product_ids:
            if pid in self.products:
                self.products[pid].is_archived = archived
                count += 1
        return count

    def delete_products(self, product_ids: Sequence[uuid.UUID]) -> int:
        target = set(product_ids)
        self.price_history = [h for h in self.price_history if h.product_id not in target]
        self.stock_movements = [m for m in self.stock_movements if m.product_id not in target]
        count = 0
        for pid in list(self.products.keys()):
            if pid in target:
                del self.products[pid]
                count += 1
        return count

    def set_category(
        self, product_ids: Sequence[uuid.UUID], category_id: uuid.UUID | None
    ) -> int:
        count = 0
        for product_id in product_ids:
            product = self.products.get(product_id)
            if product is not None:
                product.category_id = category_id
                count += 1
        return count

    def get_by_normalized_name(self, normalized_name: str) -> Product | None:
        for p in self.products.values():
            if p.name_normalized == normalized_name:
                return p
        return None

    def get_by_normalized_names(self, names: Sequence[str]) -> dict[str, Product]:
        target = set(names)
        return {
            p.name_normalized: p
            for p in self.products.values()
            if p.name_normalized in target
        }

    def add(self, product: Product) -> None:
        self.products[product.id] = product

    def get_all(self) -> Sequence[Product]:
        results = list(self.products.values())
        results.sort(key=lambda p: p.name)
        return results

    def list_by_category(
        self,
        category_id: uuid.UUID | None,
        include_archived: bool = False,
    ) -> Sequence[Product]:
        results = [
            product
            for product in self.products.values()
            if (category_id is None or product.category_id == category_id)
            and (include_archived or not product.is_archived)
        ]
        results.sort(key=lambda p: p.name)
        return results

    def search_by_category(
        self,
        category_id: uuid.UUID | None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
    ) -> tuple[Sequence[Product], int]:
        results = [
            product
            for product in self.products.values()
            if (category_id is None or product.category_id == category_id)
            and (include_archived or not product.is_archived)
        ]
        if query and query.strip():
            normalized = normalize_product_name(query)
            clean = query.strip().lower()
            results = [
                product
                for product in results
                if normalized in product.name_normalized or clean in product.name.lower()
            ]
        results.sort(key=lambda p: p.name)
        total = len(results)
        return results[offset : offset + limit], total

    def get_categories(self) -> Sequence[ProductCategory]:
        return sorted(self.categories.values(), key=lambda category: category.name)

    def get_category(self, category_id: uuid.UUID) -> ProductCategory | None:
        return self.categories.get(category_id)

    def get_category_by_name(self, name: str) -> ProductCategory | None:
        for category in self.categories.values():
            if category.name == name:
                return category
        return None

    def add_category(self, category: ProductCategory) -> None:
        self.categories[category.id] = category

    def get_price_history(self, product_id: uuid.UUID) -> Sequence[ProductPriceHistory]:
        return [h for h in self.price_history if h.product_id == product_id]

    def get_stock_movements(self, product_id: uuid.UUID) -> Sequence[StockMovement]:
        return [m for m in self.stock_movements if m.product_id == product_id]

    def add_price_history(self, history: ProductPriceHistory) -> None:
        self.price_history.append(history)

    def add_stock_movement(self, movement: StockMovement) -> None:
        self.stock_movements.append(movement)

    def create_import_batch(self, batch: ProductImportBatch) -> None:
        self.import_batches.append(batch)

    def get_import_batch_by_checksum(self, checksum: str) -> ProductImportBatch | None:
        for b in reversed(self.import_batches):
            if b.source_checksum == checksum:
                return b
        return None


class FakeStockCountRepository:
    def __init__(self, products: FakeProductRepository) -> None:
        self._products = products
        self.sessions: dict[uuid.UUID, StockCountSession] = {}
        self.items: dict[uuid.UUID, list[StockCountItem]] = {}
        self._next_number = 1

    def add_session(self, session: StockCountSession) -> None:
        if getattr(session, "count_number", None) is None:
            session.count_number = self._next_number
            self._next_number += 1
        self.sessions[session.id] = session

    def add_items(self, items: Sequence[StockCountItem]) -> None:
        for item in items:
            self.items.setdefault(item.session_id, []).append(item)

    def get_session(self, session_id: uuid.UUID) -> StockCountSession | None:
        return self.sessions.get(session_id)

    def get_items(self, session_id: uuid.UUID) -> Sequence[StockCountItem]:
        return sorted(
            self.items.get(session_id, []), key=lambda item: item.product_name
        )

    def list_sessions(self, limit: int = 20) -> Sequence[StockCountSession]:
        sessions = sorted(
            self.sessions.values(), key=lambda session: session.started_at, reverse=True
        )
        return sessions[:limit]

    def delete_item(self, item: StockCountItem) -> None:
        bucket = self.items.get(item.session_id, [])
        if item in bucket:
            bucket.remove(item)

    def stock_version(self, category_id: uuid.UUID | None) -> int:
        if category_id is None:
            return len(self._products.stock_movements)
        product_ids = {
            product.id
            for product in self._products.products.values()
            if product.category_id == category_id
        }
        return sum(
            1
            for movement in self._products.stock_movements
            if movement.product_id in product_ids
        )


class FakeReservationRepository:
    def __init__(self, products: FakeProductRepository) -> None:
        self._products = products
        self.reservations: dict[uuid.UUID, Reservation] = {}
        self.items: dict[uuid.UUID, list[ReservationItem]] = {}
        self.events: list[ReservationItemEvent] = []
        self.reminders: list[ReservationReminder] = []
        self._next_number = 1

    def add(self, reservation: Reservation) -> None:
        if getattr(reservation, "reservation_number", None) is None:
            reservation.reservation_number = self._next_number
            self._next_number += 1
        self.reservations[reservation.id] = reservation

    def add_item(self, item: ReservationItem) -> None:
        self.items.setdefault(item.reservation_id, []).append(item)

    def add_items(self, items: Sequence[ReservationItem]) -> None:
        for item in items:
            self.add_item(item)

    def get(self, reservation_id: uuid.UUID) -> Reservation | None:
        return self.reservations.get(reservation_id)

    def get_items(self, reservation_id: uuid.UUID) -> Sequence[ReservationItem]:
        return sorted(
            self.items.get(reservation_id, []),
            key=lambda item: (item.product_name_snapshot, str(item.id)),
        )

    def get_items_for_reservations(
        self, reservation_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, Sequence[ReservationItem]]:
        return {
            reservation_id: self.get_items(reservation_id)
            for reservation_id in reservation_ids
        }

    def get_item(self, item_id: uuid.UUID) -> ReservationItem | None:
        for bucket in self.items.values():
            for item in bucket:
                if item.id == item_id:
                    return item
        return None

    def lock_item(self, item_id: uuid.UUID) -> ReservationItem | None:
        return self.get_item(item_id)

    def lock_product(self, product_id: uuid.UUID) -> Product | None:
        return self._products.get_by_id(product_id)

    def delete_item(self, item: ReservationItem) -> None:
        bucket = self.items.get(item.reservation_id, [])
        if item in bucket:
            bucket.remove(item)
        self.events = [
            event
            for event in self.events
            if event.reservation_item_id != item.id
        ]

    def list(
        self,
        *,
        status: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
        now=None,
    ) -> tuple[Sequence[Reservation], int]:
        from datetime import UTC, datetime

        reference = now or datetime.now(UTC)
        results = sorted(
            self.reservations.values(),
            key=lambda reservation: (
                reservation.reservation_date,
                reservation.reservation_number,
            ),
            reverse=True,
        )

        def line_bucket(reservation: Reservation) -> list[ReservationItem]:
            return self.items.get(reservation.id, [])

        def has_open(reservation: Reservation) -> bool:
            return any(
                item.quantity - item.delivered_quantity - item.cancelled_quantity > 0
                for item in line_bucket(reservation)
            )

        if status == "open":
            results = [reservation for reservation in results if has_open(reservation)]
        elif status == "delivered":
            results = [
                reservation
                for reservation in results
                if not has_open(reservation)
                and any(item.delivered_quantity > 0 for item in line_bucket(reservation))
            ]
        elif status == "cancelled":
            results = [
                reservation
                for reservation in results
                if not has_open(reservation)
                and not any(
                    item.delivered_quantity > 0 for item in line_bucket(reservation)
                )
                and bool(line_bucket(reservation))
            ]
        elif status == "overdue":
            results = [
                reservation
                for reservation in results
                if reservation.reminder_status != "resolved"
                and reservation.reminder_due_at <= reference
            ]

        if query and query.strip():
            clean = query.strip().lower()
            results = [
                reservation
                for reservation in results
                if clean in reservation.customer_name.lower()
            ]
        total = len(results)
        return results[offset : offset + limit], total

    def list_reminders(
        self, *, due_before, limit: int = 50
    ) -> Sequence[Reservation]:
        results = [
            reservation
            for reservation in self.reservations.values()
            if reservation.reminder_status != "resolved"
            and reservation.reminder_due_at <= due_before
        ]
        results.sort(key=lambda reservation: reservation.reminder_due_at)
        return results[:limit]

    def add_event(self, event: ReservationItemEvent) -> None:
        self.events.append(event)

    def get_events(self, reservation_id: uuid.UUID) -> Sequence[ReservationItemEvent]:
        item_ids = {item.id for item in self.items.get(reservation_id, [])}
        return [event for event in self.events if event.reservation_item_id in item_ids]

    def add_reminder(self, reminder: ReservationReminder) -> None:
        self.reminders.append(reminder)

    def get_reminders(
        self, reservation_id: uuid.UUID
    ) -> Sequence[ReservationReminder]:
        return [
            reminder
            for reminder in reversed(self.reminders)
            if reminder.reservation_id == reservation_id
        ]

    def open_quantity_by_product(
        self, product_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        target = set(product_ids)
        totals: dict[uuid.UUID, int] = {}
        for bucket in self.items.values():
            for item in bucket:
                if item.product_id not in target:
                    continue
                open_quantity = (
                    item.quantity - item.delivered_quantity - item.cancelled_quantity
                )
                if open_quantity > 0:
                    totals[item.product_id] = (
                        totals.get(item.product_id, 0) + open_quantity
                    )
        return totals

    def open_product_ids(self, product_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        return set(self.open_quantity_by_product(product_ids))

    def find_stock_movement(self, idempotency_key: str):
        for movement in self._products.stock_movements:
            if movement.idempotency_key == idempotency_key:
                return movement
        return None


class FakeCampaignRepository:
    def __init__(self) -> None:
        self.campaigns: dict[uuid.UUID, Campaign] = {}
        self.versions: dict[uuid.UUID, CampaignVersion] = {}
        self.version_products: dict[uuid.UUID, list[CampaignVersionProduct]] = {}

    def add(self, campaign: Campaign) -> None:
        if getattr(campaign, "id", None) is None:
            campaign.id = uuid.uuid4()
        self.campaigns[campaign.id] = campaign

    def add_version(self, version: CampaignVersion) -> None:
        if getattr(version, "id", None) is None:
            version.id = uuid.uuid4()
        self.versions[version.id] = version
        self.version_products.setdefault(version.id, [])

    def add_version_products(
        self, products: Sequence[CampaignVersionProduct]
    ) -> None:
        for product in products:
            if getattr(product, "id", None) is None:
                product.id = uuid.uuid4()
            self.version_products.setdefault(
                product.campaign_version_id, []
            ).append(product)

    def get(self, campaign_id: uuid.UUID) -> Campaign | None:
        return self.campaigns.get(campaign_id)

    def get_for_update(self, campaign_id: uuid.UUID) -> Campaign | None:
        return self.get(campaign_id)

    def get_version(self, version_id: uuid.UUID) -> CampaignVersion | None:
        return self.versions.get(version_id)

    def get_current_version(
        self, campaign_id: uuid.UUID
    ) -> CampaignVersion | None:
        campaign = self.campaigns.get(campaign_id)
        if campaign is None or campaign.current_version_id is None:
            return None
        return self.versions.get(campaign.current_version_id)

    def get_versions(self, campaign_id: uuid.UUID) -> Sequence[CampaignVersion]:
        return sorted(
            (
                version
                for version in self.versions.values()
                if version.campaign_id == campaign_id
            ),
            key=lambda version: version.version_no,
            reverse=True,
        )

    def get_version_products(
        self, version_id: uuid.UUID
    ) -> Sequence[CampaignVersionProduct]:
        return sorted(
            self.version_products.get(version_id, []),
            key=lambda link: (link.relation_type, link.product_name_snapshot),
        )

    def get_version_products_for_versions(
        self, version_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, Sequence[CampaignVersionProduct]]:
        return {
            version_id: self.get_version_products(version_id)
            for version_id in version_ids
        }

    def set_current_version(
        self, campaign_id: uuid.UUID, version_id: uuid.UUID
    ) -> None:
        campaign = self.campaigns.get(campaign_id)
        if campaign is not None:
            campaign.current_version_id = version_id

    def set_archived(self, campaign_id: uuid.UUID, archived: bool) -> None:
        campaign = self.campaigns.get(campaign_id)
        if campaign is not None:
            campaign.is_archived = archived

    def list(
        self,
        *,
        query: str | None = None,
        campaign_type: str | None = None,
        state: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        as_of: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[tuple[Campaign, CampaignVersion]], int]:
        reference = as_of or datetime.now(UTC)
        rows: list[tuple[Campaign, CampaignVersion]] = []
        for campaign in self.campaigns.values():
            version = self.get_current_version(campaign.id)
            if version is None:
                continue
            if state == "active" and (
                campaign.is_archived or version.ends_at < reference
            ):
                continue
            if state == "history" and not (
                campaign.is_archived or version.ends_at < reference
            ):
                continue
            if campaign_type and version.campaign_type != campaign_type:
                continue
            if query and query.strip():
                clean = query.strip().lower()
                if (
                    clean not in version.name.lower()
                    and clean not in (version.description or "").lower()
                ):
                    continue
            if date_from is not None and version.ends_at < date_from:
                continue
            if date_to is not None and version.starts_at > date_to:
                continue
            rows.append((campaign, version))

        rows.sort(
            key=lambda pair: (
                pair[1].starts_at,
                pair[1].name,
                str(pair[0].id),
            ),
            reverse=True,
        )
        total = len(rows)
        return rows[offset : offset + limit], total

    def active_for_product(
        self, product_id: uuid.UUID, *, as_of: datetime
    ) -> Sequence[ActiveCampaignLink]:
        results: list[ActiveCampaignLink] = []
        for campaign in self.campaigns.values():
            if campaign.is_archived:
                continue
            version = self.get_current_version(campaign.id)
            if version is None:
                continue
            if version.starts_at > as_of or version.ends_at < as_of:
                continue
            for link in self.version_products.get(version.id, []):
                if link.product_id == product_id:
                    results.append(
                        ActiveCampaignLink(
                            campaign=campaign,
                            version=version,
                            link=link,
                        )
                    )
        results.sort(key=lambda item: (item.version.ends_at, item.version.name))
        return results


class FakeDealerPricingRepository:
    def __init__(self) -> None:
        self.pricing: dict[uuid.UUID, DealerPricing] = {}
        self.pricing_history: list[DealerPricingHistory] = []
        self.setting: DealerDiscountSetting | None = None
        self.setting_history: list[DealerDiscountSettingHistory] = []

    def get(self, product_id: uuid.UUID) -> DealerPricing | None:
        return self.pricing.get(product_id)

    def get_many(
        self, product_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, DealerPricing]:
        return {
            product_id: self.pricing[product_id]
            for product_id in product_ids
            if product_id in self.pricing
        }

    def get_for_update(self, product_id: uuid.UUID) -> DealerPricing | None:
        return self.get(product_id)

    def add(self, pricing: DealerPricing) -> None:
        if getattr(pricing, "id", None) is None:
            pricing.id = uuid.uuid4()
        self.pricing[pricing.product_id] = pricing

    def add_history(self, history: DealerPricingHistory) -> None:
        self.pricing_history.append(history)

    def get_history(
        self, product_id: uuid.UUID, limit: int = 50
    ) -> Sequence[DealerPricingHistory]:
        rows = [
            history
            for history in self.pricing_history
            if history.product_id == product_id
        ]
        rows.sort(key=lambda history: history.changed_at, reverse=True)
        return rows[:limit]

    def get_setting(self) -> DealerDiscountSetting | None:
        return self.setting

    def get_setting_for_update(self) -> DealerDiscountSetting | None:
        return self.setting

    def add_setting(self, setting: DealerDiscountSetting) -> None:
        if getattr(setting, "id", None) is None:
            setting.id = uuid.uuid4()
        self.setting = setting

    def add_setting_history(self, history: DealerDiscountSettingHistory) -> None:
        self.setting_history.append(history)

    def get_setting_history(
        self, setting_id: uuid.UUID, limit: int = 50
    ) -> Sequence[DealerDiscountSettingHistory]:
        rows = [
            history
            for history in self.setting_history
            if history.dealer_discount_setting_id == setting_id
        ]
        rows.sort(key=lambda history: history.changed_at, reverse=True)
        return rows[:limit]


class FakeCommissionRepository:
    def __init__(self) -> None:
        self.periods: dict[uuid.UUID, object] = {}
        self.rates: dict[uuid.UUID, list[object]] = {}
        self.limits: dict[uuid.UUID, list[object]] = {}
        self.banks: dict[uuid.UUID, object] = {}
        self.targets: list[object] = []

    def add_period(self, period: object) -> None:
        self.periods[period.id] = period  # type: ignore[attr-defined]
        self.rates.setdefault(period.id, [])  # type: ignore[attr-defined]
        self.limits.setdefault(period.id, [])  # type: ignore[attr-defined]

    def get_period(self, period_id: uuid.UUID) -> object | None:
        return self.periods.get(period_id)

    def get_period_by_key(self, period_key: str) -> object | None:
        return next(
            (
                period
                for period in self.periods.values()
                if period.period_key == period_key  # type: ignore[attr-defined]
            ),
            None,
        )

    def get_active_period(self, as_of) -> object | None:
        for period in self.periods.values():
            if (
                period.status == "active"  # type: ignore[attr-defined]
                and period.valid_from <= as_of <= period.valid_until  # type: ignore[attr-defined]
            ):
                return period
        return None

    def list_periods(self, limit: int = 24) -> list[object]:
        return sorted(
            self.periods.values(),
            key=lambda period: period.valid_from,  # type: ignore[attr-defined]
            reverse=True,
        )[:limit]

    def set_period_status(self, period_id: uuid.UUID, status: str) -> None:
        period = self.periods.get(period_id)
        if period is not None:
            period.status = status  # type: ignore[attr-defined]

    def delete_period(self, period_id: uuid.UUID) -> None:
        self.periods.pop(period_id, None)
        self.rates.pop(period_id, None)
        self.limits.pop(period_id, None)

    def get_rates(self, period_id: uuid.UUID) -> list[object]:
        return list(self.rates.get(period_id, []))

    def get_rate(self, rate_id: uuid.UUID) -> object | None:
        for bucket in self.rates.values():
            for rate in bucket:
                if rate.id == rate_id:  # type: ignore[attr-defined]
                    return rate
        return None

    def add_rate(self, rate: object) -> None:
        self.rates.setdefault(rate.period_id, []).append(rate)  # type: ignore[attr-defined]

    def update_rate(self, rate_id: uuid.UUID, commission_percent: Decimal) -> None:
        rate = self.get_rate(rate_id)
        if rate is not None:
            rate.commission_percent = commission_percent  # type: ignore[attr-defined]

    def delete_rate(self, rate_id: uuid.UUID) -> None:
        for period_id, bucket in self.rates.items():
            self.rates[period_id] = [
                rate for rate in bucket if rate.id != rate_id  # type: ignore[attr-defined]
            ]

    def delete_rates(self, period_id: uuid.UUID) -> None:
        self.rates[period_id] = []

    def get_limits(self, period_id: uuid.UUID) -> list[object]:
        return list(self.limits.get(period_id, []))

    def get_limit(self, limit_id: uuid.UUID) -> object | None:
        for bucket in self.limits.values():
            for limit in bucket:
                if limit.id == limit_id:  # type: ignore[attr-defined]
                    return limit
        return None

    def add_limit(self, limit: object) -> None:
        self.limits.setdefault(limit.period_id, []).append(limit)  # type: ignore[attr-defined]

    def update_limit(self, limit_id: uuid.UUID, max_installments: int) -> None:
        limit = self.get_limit(limit_id)
        if limit is not None:
            limit.max_installments = max_installments  # type: ignore[attr-defined]

    def delete_limit(self, limit_id: uuid.UUID) -> None:
        for period_id, bucket in self.limits.items():
            self.limits[period_id] = [
                limit for limit in bucket if limit.id != limit_id  # type: ignore[attr-defined]
            ]

    def delete_limits(self, period_id: uuid.UUID) -> None:
        self.limits[period_id] = []

    def get_banks(self, active_only: bool = True) -> list[object]:
        banks = sorted(self.banks.values(), key=lambda bank: bank.name)  # type: ignore[attr-defined]
        if active_only:
            banks = [bank for bank in banks if bank.is_active]  # type: ignore[attr-defined]
        return banks

    def add_bank(self, bank: object) -> None:
        self.banks[bank.id] = bank  # type: ignore[attr-defined]

    def get_profit_target(
        self, *, scope_type: str, scope_id: uuid.UUID | None, as_of
    ) -> object | None:
        matches = [
            target
            for target in self.targets
            if target.scope_type == scope_type  # type: ignore[attr-defined]
            and target.scope_id == scope_id  # type: ignore[attr-defined]
            and target.valid_from <= as_of  # type: ignore[attr-defined]
            and (
                target.valid_until is None  # type: ignore[attr-defined]
                or target.valid_until >= as_of  # type: ignore[attr-defined]
            )
        ]
        matches.sort(key=lambda target: target.valid_from, reverse=True)  # type: ignore[attr-defined]
        return matches[0] if matches else None

    def add_profit_target(self, target: object) -> None:
        self.targets.append(target)

    def set_category_group(
        self, category_id: uuid.UUID, commission_group: str
    ) -> None:
        return None


class FakeOfferRepository:
    def __init__(self) -> None:
        self.offers: dict[uuid.UUID, object] = {}
        self.items: dict[uuid.UUID, list[object]] = {}
        self.history: list[object] = []
        self._next_number = 1

    def add(self, offer: object) -> None:
        if getattr(offer, "offer_number", None) is None:
            offer.offer_number = self._next_number  # type: ignore[attr-defined]
            self._next_number += 1
        self.offers[offer.id] = offer  # type: ignore[attr-defined]
        self.items.setdefault(offer.id, [])  # type: ignore[attr-defined]

    def add_items(self, items) -> None:
        for item in items:
            self.items.setdefault(item.offer_id, []).append(item)

    def get(self, offer_id: uuid.UUID):
        return self.offers.get(offer_id)

    def get_for_update(self, offer_id: uuid.UUID):
        return self.get(offer_id)

    def get_items(self, offer_id: uuid.UUID):
        return list(self.items.get(offer_id, []))

    def get_items_for_offers(self, offer_ids):
        return {
            offer_id: list(self.items.get(offer_id, []))
            for offer_id in offer_ids
        }

    def delete_items(self, offer_id: uuid.UUID) -> None:
        self.items[offer_id] = []

    def save(self, offer: object) -> None:
        self.offers[offer.id] = offer  # type: ignore[attr-defined]

    def list(self, *, status=None, query=None, limit=50, offset=0):
        rows = sorted(
            self.offers.values(),
            key=lambda offer: (offer.created_at, offer.offer_number),  # type: ignore[attr-defined]
            reverse=True,
        )
        if status:
            rows = [row for row in rows if row.status == status]  # type: ignore[attr-defined]
        if query and query.strip():
            clean = query.strip().lower()
            rows = [
                row
                for row in rows
                if clean in (row.customer_name or "").lower()  # type: ignore[attr-defined]
                or clean in (row.customer_phone or "").lower()  # type: ignore[attr-defined]
            ]
        total = len(rows)
        return rows[offset : offset + limit], total

    def add_history(self, history: object) -> None:
        self.history.append(history)

    def get_history(self, offer_id: uuid.UUID):
        return [
            row
            for row in reversed(self.history)
            if row.offer_id == offer_id  # type: ignore[attr-defined]
        ]

    def find_by_converted_reservation(self, reservation_id: uuid.UUID):
        for offer in self.offers.values():
            if offer.converted_reservation_id == reservation_id:  # type: ignore[attr-defined]
                return offer
        return None


class FakeImportBatchRepository:
    def __init__(self) -> None:
        self.batches: dict[str, DataImportBatch] = {}

    def get_by_token(self, commit_token: str) -> DataImportBatch | None:
        for batch in self.batches.values():
            if batch.commit_token == commit_token:
                return batch
        return None

    def get_by_checksum(
        self, module: str, source_checksum: str
    ) -> DataImportBatch | None:
        for batch in self.batches.values():
            if (
                batch.module == module
                and batch.source_checksum == source_checksum
            ):
                return batch
        return None

    def add(self, batch: DataImportBatch) -> None:
        self.batches[str(batch.id)] = batch


class FakeUnitOfWork:
    def __init__(self, repo: FakeProductRepository | None = None) -> None:
        self.products = repo or FakeProductRepository()
        self.stock_counts = FakeStockCountRepository(self.products)
        self.reservations = FakeReservationRepository(self.products)
        self.campaigns = FakeCampaignRepository()
        self.dealer_pricing = FakeDealerPricingRepository()
        self.commissions = FakeCommissionRepository()
        self.offers = FakeOfferRepository()
        self.import_batches = FakeImportBatchRepository()
        self.committed = False
        self.rolled_back = False
        self._initial_state: tuple[object, ...] | None = None

    def _state(self) -> tuple[object, ...]:
        products = tuple(
            sorted(
                (
                    str(p.id),
                    p.name,
                    p.name_normalized,
                    getattr(p, "is_archived", None),
                    getattr(p, "physical_stock", None),
                    getattr(p, "regular_price", None),
                    getattr(p, "website_discounted_price", None),
                    getattr(p, "cost_price", None),
                )
                for p in self.products.products.values()
            )
        )
        return (
            products,
            len(self.products.price_history),
            len(self.products.stock_movements),
            len(self.products.import_batches),
            tuple(
                sorted(
                    (str(session.id), session.status, session.stock_version)
                    for session in self.stock_counts.sessions.values()
                )
            ),
            tuple(
                sorted(
                    (
                        str(item.id),
                        str(item.session_id),
                        item.system_quantity,
                        item.counted_quantity,
                        item.difference,
                    )
                    for bucket in self.stock_counts.items.values()
                    for item in bucket
                )
            ),
            tuple(
                sorted(
                    (
                        str(reservation.id),
                        reservation.customer_name,
                        reservation.reminder_status,
                        str(reservation.reminder_due_at),
                    )
                    for reservation in self.reservations.reservations.values()
                )
            ),
            tuple(
                sorted(
                    (
                        str(item.id),
                        str(item.reservation_id),
                        str(item.product_id),
                        item.product_name_snapshot,
                        item.quantity,
                        item.delivered_quantity,
                        item.cancelled_quantity,
                        item.status,
                    )
                    for bucket in self.reservations.items.values()
                    for item in bucket
                )
            ),
            len(self.reservations.events),
            len(self.reservations.reminders),
            tuple(
                sorted(
                    (
                        str(campaign.id),
                        str(campaign.current_version_id),
                        campaign.is_archived,
                    )
                    for campaign in self.campaigns.campaigns.values()
                )
            ),
            tuple(
                sorted(
                    (
                        str(version.id),
                        str(version.campaign_id),
                        version.version_no,
                        version.name,
                        version.campaign_type,
                        str(version.starts_at),
                        str(version.ends_at),
                        version.discount_type,
                        str(version.discount_value),
                        version.gift_optional,
                    )
                    for version in self.campaigns.versions.values()
                )
            ),
            tuple(
                sorted(
                    (
                        str(link.id),
                        str(link.campaign_version_id),
                        str(link.product_id),
                        link.product_name_snapshot,
                        link.relation_type,
                        str(link.quantity_required),
                    )
                    for bucket in self.campaigns.version_products.values()
                    for link in bucket
                )
            ),
            tuple(
                sorted(
                    (
                        str(pricing.id),
                        str(pricing.product_id),
                        str(pricing.cash_floor_price),
                        str(pricing.card_floor_price),
                    )
                    for pricing in self.dealer_pricing.pricing.values()
                )
            ),
            tuple(
                sorted(
                    (
                        str(history.id),
                        str(history.product_id),
                        str(history.old_cash_floor),
                        str(history.new_cash_floor),
                        str(history.old_card_floor),
                        str(history.new_card_floor),
                    )
                    for history in self.dealer_pricing.pricing_history
                )
            ),
            (
                str(self.dealer_pricing.setting.id),
                str(self.dealer_pricing.setting.default_percent),
            )
            if self.dealer_pricing.setting is not None
            else None,
            tuple(
                sorted(
                    (
                        str(history.id),
                        str(history.dealer_discount_setting_id),
                        str(history.old_percent),
                        str(history.new_percent),
                    )
                    for history in self.dealer_pricing.setting_history
                )
            ),
            len(self.commissions.periods),
            len(self.commissions.targets),
            len(self.offers.offers),
            sum(len(bucket) for bucket in self.offers.items.values()),
            len(self.offers.history),
            len(self.import_batches.batches),
        )

    def __enter__(self) -> Self:
        self.committed = False
        self.rolled_back = False
        self._initial_state = self._state()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rollback()
        elif not self.committed and self._initial_state != self._state():
            raise AssertionError(
                "UnitOfWork exited with uncommitted writes; call uow.commit()"
            )

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True
