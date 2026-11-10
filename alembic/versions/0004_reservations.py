"""reservations, reservation items, item events and reminders

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = "('reserved', 'delivery_requested', 'depot_ready', 'service_assigned', 'delivered', 'cancelled')"


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
    )


def _ts(name: str, *, nullable: bool = False, default_now: bool = True) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.func.now() if default_now else None,
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "reservations",
        _uuid_pk(),
        sa.Column(
            "reservation_number",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("customer_name", sa.Text(), nullable=False),
        _ts("reservation_date"),
        _ts("reminder_due_at", default_now=False),
        sa.Column(
            "reminder_status", sa.Text(), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.Column("created_by_name", sa.Text(), nullable=True),
        sa.Column("created_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reservations")),
        sa.UniqueConstraint(
            "reservation_number", name=op.f("uq_reservations_reservation_number")
        ),
        sa.CheckConstraint(
            "char_length(trim(customer_name)) > 0",
            name=op.f("ck_reservations_customer_name_not_empty"),
        ),
        sa.CheckConstraint(
            "reminder_status IN ('pending', 'snoozed', 'resolved')",
            name=op.f("ck_reservations_reminder_status_valid"),
        ),
    )
    op.create_index(
        op.f("ix_reservations_reminder_due_at"), "reservations", ["reminder_due_at"]
    )
    op.create_index(
        op.f("ix_reservations_customer_name"), "reservations", ["customer_name"]
    )

    op.create_table(
        "reservation_items",
        _uuid_pk(),
        sa.Column("reservation_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("product_name_snapshot", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "delivered_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "cancelled_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "status", sa.Text(), server_default=sa.text("'reserved'"), nullable=False
        ),
        _ts("service_date", nullable=True, default_now=False),
        sa.Column("other_dealer_note", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reservation_items")),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["reservations.id"],
            name=op.f("fk_reservation_items_reservation_id_reservations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_reservation_items_product_id_products"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "quantity > 0", name=op.f("ck_reservation_items_quantity_positive")
        ),
        sa.CheckConstraint(
            "delivered_quantity >= 0",
            name=op.f("ck_reservation_items_delivered_quantity_non_negative"),
        ),
        sa.CheckConstraint(
            "cancelled_quantity >= 0",
            name=op.f("ck_reservation_items_cancelled_quantity_non_negative"),
        ),
        sa.CheckConstraint(
            "delivered_quantity + cancelled_quantity <= quantity",
            name=op.f("ck_reservation_items_closed_quantity_within_quantity"),
        ),
        sa.CheckConstraint(
            f"status IN {STATUSES}", name=op.f("ck_reservation_items_status_valid")
        ),
    )
    op.create_index(
        op.f("ix_reservation_items_reservation_id"),
        "reservation_items",
        ["reservation_id"],
    )
    op.create_index(
        op.f("ix_reservation_items_product_id"), "reservation_items", ["product_id"]
    )

    op.create_table(
        "reservation_item_events",
        _uuid_pk(),
        sa.Column("reservation_item_id", sa.Uuid(), nullable=False),
        sa.Column("old_status", sa.Text(), nullable=True),
        sa.Column("new_status", sa.Text(), nullable=False),
        sa.Column("quantity_delta", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("event_at"),
        sa.Column("created_by_name", sa.Text(), nullable=True),
        sa.Column("created_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reservation_item_events")),
        sa.ForeignKeyConstraint(
            ["reservation_item_id"],
            ["reservation_items.id"],
            name=op.f("fk_reservation_item_events_reservation_item_id_reservation_items"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"old_status IS NULL OR old_status IN {STATUSES}",
            name=op.f("ck_reservation_item_events_old_status_valid"),
        ),
        sa.CheckConstraint(
            f"new_status IN {STATUSES}",
            name=op.f("ck_reservation_item_events_new_status_valid"),
        ),
    )
    op.create_index(
        op.f("ix_reservation_item_events_item_id"),
        "reservation_item_events",
        ["reservation_item_id"],
    )

    op.create_table(
        "reservation_reminders",
        _uuid_pk(),
        sa.Column("reservation_id", sa.Uuid(), nullable=False),
        _ts("previous_due_at", default_now=False),
        _ts("new_due_at", default_now=False),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.Column("created_by_name", sa.Text(), nullable=True),
        sa.Column("created_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reservation_reminders")),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["reservations.id"],
            name=op.f("fk_reservation_reminders_reservation_id_reservations"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_reservation_reminders_reservation_id"),
        "reservation_reminders",
        ["reservation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_reservation_reminders_reservation_id"),
        table_name="reservation_reminders",
    )
    op.drop_table("reservation_reminders")
    op.drop_index(
        op.f("ix_reservation_item_events_item_id"),
        table_name="reservation_item_events",
    )
    op.drop_table("reservation_item_events")
    op.drop_index(
        op.f("ix_reservation_items_product_id"), table_name="reservation_items"
    )
    op.drop_index(
        op.f("ix_reservation_items_reservation_id"), table_name="reservation_items"
    )
    op.drop_table("reservation_items")
    op.drop_index(op.f("ix_reservations_customer_name"), table_name="reservations")
    op.drop_index(
        op.f("ix_reservations_reminder_due_at"), table_name="reservations"
    )
    op.drop_table("reservations")
