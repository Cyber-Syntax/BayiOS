from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session, aliased

from bayios.adapters.db.models.campaigns import (
    Campaign,
    CampaignVersion,
    CampaignVersionProduct,
)
from bayios.application.ports.campaigns import ActiveCampaignLink


class SqlAlchemyCampaignRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, campaign: Campaign) -> None:
        self._session.add(campaign)
        self._session.flush()

    def add_version(self, version: CampaignVersion) -> None:
        self._session.add(version)
        self._session.flush()

    def add_version_products(
        self, products: Sequence[CampaignVersionProduct]
    ) -> None:
        if not products:
            return
        self._session.add_all(products)
        self._session.flush()

    def get(self, campaign_id: uuid.UUID) -> Campaign | None:
        return self._session.get(Campaign, campaign_id)

    def get_for_update(self, campaign_id: uuid.UUID) -> Campaign | None:
        return self._session.scalar(
            sa.select(Campaign).where(Campaign.id == campaign_id).with_for_update()
        )

    def get_version(self, version_id: uuid.UUID) -> CampaignVersion | None:
        return self._session.get(CampaignVersion, version_id)

    def get_current_version(
        self, campaign_id: uuid.UUID
    ) -> CampaignVersion | None:
        return self._session.scalar(
            sa.select(CampaignVersion)
            .join(Campaign, Campaign.current_version_id == CampaignVersion.id)
            .where(Campaign.id == campaign_id)
        )

    def get_versions(self, campaign_id: uuid.UUID) -> Sequence[CampaignVersion]:
        return self._session.scalars(
            sa.select(CampaignVersion)
            .where(CampaignVersion.campaign_id == campaign_id)
            .order_by(CampaignVersion.version_no.desc())
        ).all()

    def get_version_products(
        self, version_id: uuid.UUID
    ) -> Sequence[CampaignVersionProduct]:
        return self._session.scalars(
            sa.select(CampaignVersionProduct)
            .where(CampaignVersionProduct.campaign_version_id == version_id)
            .order_by(
                CampaignVersionProduct.relation_type,
                CampaignVersionProduct.product_name_snapshot,
            )
        ).all()

    def get_version_products_for_versions(
        self, version_ids: Sequence[uuid.UUID]
    ) -> Mapping[uuid.UUID, Sequence[CampaignVersionProduct]]:
        if not version_ids:
            return {}
        rows = self._session.scalars(
            sa.select(CampaignVersionProduct)
            .where(CampaignVersionProduct.campaign_version_id.in_(version_ids))
            .order_by(
                CampaignVersionProduct.campaign_version_id,
                CampaignVersionProduct.relation_type,
                CampaignVersionProduct.product_name_snapshot,
            )
        ).all()
        grouped: dict[uuid.UUID, list[CampaignVersionProduct]] = {
            version_id: [] for version_id in version_ids
        }
        for row in rows:
            grouped.setdefault(row.campaign_version_id, []).append(row)
        return grouped

    def set_current_version(
        self, campaign_id: uuid.UUID, version_id: uuid.UUID
    ) -> None:
        self._session.execute(
            sa.update(Campaign)
            .where(Campaign.id == campaign_id)
            .values(current_version_id=version_id, updated_at=sa.func.now())
        )
        self._session.flush()

    def set_archived(self, campaign_id: uuid.UUID, archived: bool) -> None:
        self._session.execute(
            sa.update(Campaign)
            .where(Campaign.id == campaign_id)
            .values(is_archived=archived, updated_at=sa.func.now())
        )
        self._session.flush()

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
        current = aliased(CampaignVersion)
        stmt = (
            sa.select(Campaign, current)
            .select_from(Campaign)
            .join(current, Campaign.current_version_id == current.id)
        )
        count_stmt = (
            sa.select(sa.func.count(Campaign.id))
            .select_from(Campaign)
            .join(current, Campaign.current_version_id == current.id)
        )

        conditions = []
        now = as_of or datetime.now(UTC)
        if state == "active":
            conditions.append(Campaign.is_archived.is_(False))
            conditions.append(current.ends_at >= now)
        elif state == "history":
            conditions.append(
                sa.or_(
                    Campaign.is_archived.is_(True),
                    current.ends_at < now,
                )
            )

        if campaign_type:
            conditions.append(current.campaign_type == campaign_type)

        if query and query.strip():
            clean = query.strip()
            conditions.append(
                sa.or_(
                    current.name.ilike(f"%{clean}%"),
                    current.description.ilike(f"%{clean}%"),
                )
            )

        if date_from is not None:
            conditions.append(current.ends_at >= date_from)
        if date_to is not None:
            conditions.append(current.starts_at <= date_to)

        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)

        total = self._session.scalar(count_stmt) or 0
        rows = self._session.execute(
            stmt.order_by(
                current.starts_at.desc(), current.name, Campaign.id
            )
            .limit(limit)
            .offset(offset)
        ).all()
        return [(row[0], row[1]) for row in rows], total

    def active_for_product(
        self, product_id: uuid.UUID, *, as_of: datetime
    ) -> Sequence[ActiveCampaignLink]:
        current = aliased(CampaignVersion)
        rows = self._session.execute(
            sa.select(Campaign, current, CampaignVersionProduct)
            .select_from(Campaign)
            .join(current, Campaign.current_version_id == current.id)
            .join(
                CampaignVersionProduct,
                CampaignVersionProduct.campaign_version_id == current.id,
            )
            .where(
                CampaignVersionProduct.product_id == product_id,
                Campaign.is_archived.is_(False),
                current.starts_at <= as_of,
                current.ends_at >= as_of,
            )
            .order_by(current.ends_at, current.name)
        ).all()
        return [
            ActiveCampaignLink(campaign=row[0], version=row[1], link=row[2])
            for row in rows
        ]
