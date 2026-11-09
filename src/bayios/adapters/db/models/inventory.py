from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
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


class StockCountSession(Base):
    __tablename__ = "stock_count_sessions"
    __table_args__ = (
        sa.UniqueConstraint("count_number"),
        sa.CheckConstraint(
            "status IN ('open', 'review', 'completed', 'cancelled')",
            name="status_valid",
        ),
        sa.Index("ix_stock_count_sessions_category_id", "category_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    count_number: Mapped[int] = mapped_column(
        sa.BigInteger, sa.Identity(always=True)
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("product_categories.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(sa.Text, server_default=sa.text("'open'"))
    # Number of stock movements for the category when the snapshot was taken.
    stock_version: Mapped[int] = mapped_column(sa.Integer, server_default=sa.text("0"))
    note: Mapped[str | None] = mapped_column(sa.Text)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_by_name: Mapped[str | None] = mapped_column(sa.Text)
    created_by_device: Mapped[str | None] = mapped_column(sa.Text)
    completed_by_name: Mapped[str | None] = mapped_column(sa.Text)
    completed_by_device: Mapped[str | None] = mapped_column(sa.Text)


class StockCountItem(Base):
    __tablename__ = "stock_count_items"
    __table_args__ = (
        sa.UniqueConstraint("session_id", "product_id"),
        sa.CheckConstraint(
            "counted_quantity IS NULL OR counted_quantity >= 0",
            name="counted_quantity_non_negative",
        ),
        sa.CheckConstraint(
            "difference IS NULL OR counted_quantity IS NOT NULL",
            name="difference_requires_counted_quantity",
        ),
        sa.Index("ix_stock_count_items_session_id", "session_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("stock_count_sessions.id", ondelete="CASCADE")
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="CASCADE")
    )
    product_name: Mapped[str] = mapped_column(sa.Text)
    system_quantity: Mapped[int] = mapped_column(sa.Integer)
    counted_quantity: Mapped[int | None] = mapped_column(sa.Integer)
    difference: Mapped[int | None] = mapped_column(sa.Integer)
    applied_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
