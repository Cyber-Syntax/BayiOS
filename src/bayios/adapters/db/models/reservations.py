from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from bayios.adapters.db.models.base import Base, uuid_pk

RESERVATION_STATUS_VALUES = (
    "'reserved'",
    "'delivery_requested'",
    "'depot_ready'",
    "'service_assigned'",
    "'delivered'",
    "'cancelled'",
)
RESERVATION_STATUS_SQL = f"({', '.join(RESERVATION_STATUS_VALUES)})"
REMINDER_STATUS_SQL = "('pending', 'snoozed', 'resolved')"


class Reservation(Base):
    """Header of a confirmed sale tracked until delivery.

    It never reserves or reduces physical stock; only a delivered line does.
    """

    __tablename__ = "reservations"
    __table_args__ = (
        sa.UniqueConstraint("reservation_number"),
        sa.CheckConstraint(
            "char_length(trim(customer_name)) > 0", name="customer_name_not_empty"
        ),
        sa.CheckConstraint(
            f"reminder_status IN {REMINDER_STATUS_SQL}", name="reminder_status_valid"
        ),
        sa.Index("ix_reservations_reminder_due_at", "reminder_due_at"),
        sa.Index("ix_reservations_customer_name", "customer_name"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    reservation_number: Mapped[int] = mapped_column(
        sa.BigInteger, sa.Identity(always=True)
    )
    customer_name: Mapped[str] = mapped_column(sa.Text)
    reservation_date: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    reminder_due_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    reminder_status: Mapped[str] = mapped_column(
        sa.Text, server_default=sa.text("'pending'")
    )
    note: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    created_by_name: Mapped[str | None] = mapped_column(sa.Text)
    created_by_device: Mapped[str | None] = mapped_column(sa.Text)


class ReservationItem(Base):
    """Quantity-bearing line; delivery/cancellation progress is tracked per line."""

    __tablename__ = "reservation_items"
    __table_args__ = (
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint(
            "delivered_quantity >= 0", name="delivered_quantity_non_negative"
        ),
        sa.CheckConstraint(
            "cancelled_quantity >= 0", name="cancelled_quantity_non_negative"
        ),
        sa.CheckConstraint(
            "delivered_quantity + cancelled_quantity <= quantity",
            name="closed_quantity_within_quantity",
        ),
        sa.CheckConstraint(f"status IN {RESERVATION_STATUS_SQL}", name="status_valid"),
        sa.Index("ix_reservation_items_reservation_id", "reservation_id"),
        sa.Index("ix_reservation_items_product_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    reservation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("reservations.id", ondelete="CASCADE")
    )
    # Nullable on purpose: a delivered/cancelled line survives a hard product delete
    # through product_name_snapshot. Open lines block the delete in the use-case.
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("products.id", ondelete="SET NULL")
    )
    product_name_snapshot: Mapped[str] = mapped_column(sa.Text)
    quantity: Mapped[int] = mapped_column(sa.Integer)
    delivered_quantity: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("0")
    )
    cancelled_quantity: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("0")
    )
    status: Mapped[str] = mapped_column(
        sa.Text, server_default=sa.text("'reserved'")
    )
    service_date: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    other_dealer_note: Mapped[str | None] = mapped_column(sa.Text)
    note: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class ReservationItemEvent(Base):
    __tablename__ = "reservation_item_events"
    __table_args__ = (
        sa.CheckConstraint(
            f"old_status IS NULL OR old_status IN {RESERVATION_STATUS_SQL}",
            name="old_status_valid",
        ),
        sa.CheckConstraint(
            f"new_status IN {RESERVATION_STATUS_SQL}", name="new_status_valid"
        ),
        sa.Index("ix_reservation_item_events_item_id", "reservation_item_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    reservation_item_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("reservation_items.id", ondelete="CASCADE")
    )
    old_status: Mapped[str | None] = mapped_column(sa.Text)
    new_status: Mapped[str] = mapped_column(sa.Text)
    quantity_delta: Mapped[int | None] = mapped_column(sa.Integer)
    note: Mapped[str | None] = mapped_column(sa.Text)
    event_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    created_by_name: Mapped[str | None] = mapped_column(sa.Text)
    created_by_device: Mapped[str | None] = mapped_column(sa.Text)


class ReservationReminder(Base):
    __tablename__ = "reservation_reminders"
    __table_args__ = (
        sa.Index("ix_reservation_reminders_reservation_id", "reservation_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    reservation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("reservations.id", ondelete="CASCADE")
    )
    previous_due_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    new_due_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    created_by_name: Mapped[str | None] = mapped_column(sa.Text)
    created_by_device: Mapped[str | None] = mapped_column(sa.Text)
