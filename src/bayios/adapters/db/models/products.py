from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bayios.adapters.db.models.base import MONEY, Base, uuid_pk


class ProductCategory(Base):
    __tablename__ = "product_categories"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(sa.Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        sa.UniqueConstraint("name_normalized"),
        sa.CheckConstraint(
            "char_length(name_normalized) > 0", name="name_normalized_not_empty"
        ),
        sa.CheckConstraint("regular_price >= 0", name="regular_price_non_negative"),
        sa.CheckConstraint(
            "website_discounted_price >= 0",
            name="website_discounted_price_non_negative",
        ),
        sa.CheckConstraint("cost_price >= 0", name="cost_price_non_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(sa.Text)
    name_normalized: Mapped[str] = mapped_column(sa.Text)
    regular_price: Mapped[Decimal | None] = mapped_column(MONEY)
    website_discounted_price: Mapped[Decimal | None] = mapped_column(MONEY)
    cost_price: Mapped[Decimal | None] = mapped_column(MONEY)
    # No >= 0 CHECK on purpose: FR-RES-17 allows delivery with insufficient stock (negative stock).
    physical_stock: Mapped[int] = mapped_column(sa.Integer, server_default=sa.text("0"))
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("product_categories.id"), index=True
    )
    is_archived: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    last_price_changed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True)
    )


class ProductImportBatch(Base):
    __tablename__ = "product_import_batches"
    __table_args__ = (
        sa.UniqueConstraint("import_number"),
        sa.CheckConstraint("file_type IN ('csv', 'xlsx')", name="file_type_valid"),
        sa.CheckConstraint(
            "status IN ('previewed', 'committed', 'cancelled')", name="status_valid"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    import_number: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True))
    file_name: Mapped[str] = mapped_column(sa.Text)
    file_type: Mapped[str] = mapped_column(sa.Text)
    # sha256 of the uploaded bytes; used for stale/duplicate-commit checks.
    source_checksum: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[str] = mapped_column(sa.Text)
    row_count: Mapped[int] = mapped_column(sa.Integer, server_default=sa.text("0"))
    created_count: Mapped[int] = mapped_column(sa.Integer, server_default=sa.text("0"))
    updated_count: Mapped[int] = mapped_column(sa.Integer, server_default=sa.text("0"))
    error_count: Mapped[int] = mapped_column(sa.Integer, server_default=sa.text("0"))
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_by_name: Mapped[str | None] = mapped_column(sa.Text)
    created_by_device: Mapped[str | None] = mapped_column(sa.Text)


class ProductPriceHistory(Base):
    __tablename__ = "product_price_history"
    __table_args__ = (
        sa.CheckConstraint(
            "field_name IN ('regular_price', 'website_discounted_price', 'cost_price')",
            name="field_name_valid",
        ),
        sa.CheckConstraint(
            "source IN ('csv_import', 'manual', 'other')", name="source_valid"
        ),
        sa.Index(
            "ix_product_price_history_product_id_changed_at", "product_id", "changed_at"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    product_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("products.id", ondelete="CASCADE")
    )
    field_name: Mapped[str] = mapped_column(sa.Text)
    old_value: Mapped[Decimal | None] = mapped_column(MONEY)
    new_value: Mapped[Decimal | None] = mapped_column(MONEY)
    source: Mapped[str] = mapped_column(sa.Text)
    changed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    changed_by_name: Mapped[str | None] = mapped_column(sa.Text)
    changed_by_device: Mapped[str | None] = mapped_column(sa.Text)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey(
            "product_import_batches.id", name="fk_product_price_history_import_batch_id"
        )
    )
