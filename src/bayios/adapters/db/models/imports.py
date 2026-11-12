from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bayios.adapters.db.models.base import Base, uuid_pk


class DataImportBatch(Base):
    """Audit and idempotency record for non-product Excel imports."""

    __tablename__ = "data_import_batches"
    __table_args__ = (
        sa.UniqueConstraint(
            "commit_token", name="uq_data_import_batches_commit_token"
        ),
        sa.Index(
            "ix_data_import_batches_module_checksum",
            "module",
            "source_checksum",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    module: Mapped[str] = mapped_column(sa.Text)
    file_name: Mapped[str] = mapped_column(sa.Text)
    file_type: Mapped[str] = mapped_column(sa.Text)
    source_checksum: Mapped[str] = mapped_column(sa.Text)
    commit_token: Mapped[str | None] = mapped_column(sa.Text)
    status: Mapped[str] = mapped_column(
        sa.Text, server_default=sa.text("'committed'")
    )
    row_count: Mapped[int] = mapped_column(sa.Integer, server_default=sa.text("0"))
    created_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("0")
    )
    updated_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("0")
    )
    skipped_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("0")
    )
    error_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("0")
    )
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_by_name: Mapped[str | None] = mapped_column(sa.Text)
    created_by_device: Mapped[str | None] = mapped_column(sa.Text)
