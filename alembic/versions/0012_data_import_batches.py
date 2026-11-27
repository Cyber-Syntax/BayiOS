"""data import batches

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_import_batches",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("module", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_type", sa.Text(), nullable=False),
        sa.Column("source_checksum", sa.Text(), nullable=False),
        sa.Column("commit_token", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.Text(), server_default=sa.text("'committed'"), nullable=False
        ),
        sa.Column("row_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "updated_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "skipped_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "error_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("summary", JSONB(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_name", sa.Text(), nullable=True),
        sa.Column("created_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_import_batches")),
        sa.UniqueConstraint(
            "commit_token", name=op.f("uq_data_import_batches_commit_token")
        ),
    )
    op.create_index(
        "ix_data_import_batches_module_checksum",
        "data_import_batches",
        ["module", "source_checksum"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_data_import_batches_module_checksum",
        table_name="data_import_batches",
    )
    op.drop_table("data_import_batches")
