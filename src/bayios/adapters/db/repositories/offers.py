from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session

from bayios.adapters.db.models.offers import Offer, OfferHistory, OfferItem


class SqlAlchemyOfferRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, offer: Offer) -> None:
        self._session.add(offer)
        self._session.flush()

    def add_items(self, items: Sequence[OfferItem]) -> None:
        if not items:
            return
        self._session.add_all(items)
        self._session.flush()

    def get(self, offer_id: uuid.UUID) -> Offer | None:
        return self._session.get(Offer, offer_id)

    def get_for_update(self, offer_id: uuid.UUID) -> Offer | None:
        return self._session.scalar(
            sa.select(Offer).where(Offer.id == offer_id).with_for_update()
        )

    def get_items(self, offer_id: uuid.UUID) -> Sequence[OfferItem]:
        return self._session.scalars(
            sa.select(OfferItem)
            .where(OfferItem.offer_id == offer_id)
            .order_by(OfferItem.position, OfferItem.id)
        ).all()

    def get_items_for_offers(
        self, offer_ids: Sequence[uuid.UUID]
    ) -> Mapping[uuid.UUID, Sequence[OfferItem]]:
        if not offer_ids:
            return {}
        rows = self._session.scalars(
            sa.select(OfferItem)
            .where(OfferItem.offer_id.in_(offer_ids))
            .order_by(OfferItem.offer_id, OfferItem.position, OfferItem.id)
        ).all()
        grouped: dict[uuid.UUID, list[OfferItem]] = {
            offer_id: [] for offer_id in offer_ids
        }
        for row in rows:
            grouped.setdefault(row.offer_id, []).append(row)
        return grouped

    def delete_items(self, offer_id: uuid.UUID) -> None:
        self._session.execute(
            sa.delete(OfferItem).where(OfferItem.offer_id == offer_id)
        )
        self._session.flush()

    def save(self, offer: Offer) -> None:
        self._session.add(offer)
        self._session.flush()

    def list(
        self,
        *,
        status: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Offer], int]:
        stmt = sa.select(Offer)
        count_stmt = sa.select(sa.func.count(Offer.id))
        conditions = []
        if status:
            conditions.append(Offer.status == status)
        if query and query.strip():
            clean = query.strip()
            conditions.append(
                sa.or_(
                    Offer.customer_name.ilike(f"%{clean}%"),
                    Offer.customer_phone.ilike(f"%{clean}%"),
                )
            )
        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)
        total = self._session.scalar(count_stmt) or 0
        rows = self._session.scalars(
            stmt.order_by(Offer.created_at.desc(), Offer.offer_number.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return rows, total

    def add_history(self, history: OfferHistory) -> None:
        self._session.add(history)

    def get_history(self, offer_id: uuid.UUID) -> Sequence[OfferHistory]:
        return self._session.scalars(
            sa.select(OfferHistory)
            .where(OfferHistory.offer_id == offer_id)
            .order_by(OfferHistory.changed_at.desc())
        ).all()

    def find_by_converted_reservation(
        self, reservation_id: uuid.UUID
    ) -> Offer | None:
        return self._session.scalar(
            sa.select(Offer).where(
                Offer.converted_reservation_id == reservation_id
            )
        )
