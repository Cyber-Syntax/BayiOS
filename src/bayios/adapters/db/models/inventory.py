from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from bayios.adapters.db.models.base import Base, uuid_pk


class StockMovement(Base):
    """Append-only ledger (enforced by a DB trigger, see migration 0001)."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        sa.UniqueConstraint("idempotency_key"),
        sa.CheckConstraint(
            "movement_type IN ('csv_update', 'stock_count_adjustment', 'delivery_out', "
            "'manual_adjustment', 'return_in', 'reversal')",
            name="movement_type_valid",
        ),
        sa.CheckConstraint(
            "quantity_after = quantity_before + quantity_delta", name="quantity_balance"
        ),
        sa.Index(
            "ix_stock_movements_product_id_created_at", "product_id", "created_at"
        ),
        sa.Index("ix_stock_movements_reference", "reference_type", "reference_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    product_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="CASCADE")
    )
    movement_type: Mapped[str] = mapped_column(sa.Text)
    quantity_delta: Mapped[int] = mapped_column(sa.Integer)
    quantity_before: Mapped[int] = mapped_column(sa.Integer)
    quantity_after: Mapped[int] = mapped_column(sa.Integer)
    reference_type: Mapped[str | None] = mapped_column(sa.Text)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid)
    note: Mapped[str | None] = mapped_column(sa.Text)
    idempotency_key: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    created_by_name: Mapped[str | None] = mapped_column(sa.Text)
    created_by_device: Mapped[str | None] = mapped_column(sa.Text)
