"""initial catalog: products, price history, import batches, stock movements

Revision ID: 0001
Revises:
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
        "product_categories",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_categories")),
        sa.UniqueConstraint("name", name=op.f("uq_product_categories_name")),
    )

    op.create_table(
        "products",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_normalized", sa.Text(), nullable=False),
        sa.Column("regular_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("website_discounted_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("cost_price", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "physical_stock", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column(
            "is_archived", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        _ts("created_at"),
        _ts("updated_at"),
        _ts("last_seen_at", nullable=True, default_now=False),
        _ts("last_price_changed_at", nullable=True, default_now=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["product_categories.id"],
            name=op.f("fk_products_category_id_product_categories"),
        ),
        sa.UniqueConstraint(
            "name_normalized", name=op.f("uq_products_name_normalized")
        ),
        sa.CheckConstraint(
            "char_length(name_normalized) > 0",
            name=op.f("ck_products_name_normalized_not_empty"),
        ),
        sa.CheckConstraint(
            "regular_price >= 0", name=op.f("ck_products_regular_price_non_negative")
        ),
        sa.CheckConstraint(
            "website_discounted_price >= 0",
            name=op.f("ck_products_website_discounted_price_non_negative"),
        ),
        sa.CheckConstraint(
            "cost_price >= 0", name=op.f("ck_products_cost_price_non_negative")
        ),
    )
    op.create_index(op.f("ix_products_category_id"), "products", ["category_id"])

    op.create_table(
        "product_import_batches",
        _uuid_pk(),
        sa.Column(
            "import_number", sa.BigInteger(), sa.Identity(always=True), nullable=False
        ),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_type", sa.Text(), nullable=False),
        sa.Column("source_checksum", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "row_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "created_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "updated_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "error_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("summary", sa.dialects.postgresql.JSONB(), nullable=True),
        _ts("started_at"),
        _ts("completed_at", nullable=True, default_now=False),
        sa.Column("created_by_name", sa.Text(), nullable=True),
        sa.Column("created_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_import_batches")),
        sa.UniqueConstraint(
            "import_number", name=op.f("uq_product_import_batches_import_number")
        ),
        sa.CheckConstraint(
            "file_type IN ('csv', 'xlsx')",
            name=op.f("ck_product_import_batches_file_type_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('previewed', 'committed', 'cancelled')",
            name=op.f("ck_product_import_batches_status_valid"),
        ),
    )

    op.create_table(
        "product_price_history",
        _uuid_pk(),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("field_name", sa.Text(), nullable=False),
        sa.Column("old_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("new_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        _ts("changed_at"),
        sa.Column("changed_by_name", sa.Text(), nullable=True),
        sa.Column("changed_by_device", sa.Text(), nullable=True),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_price_history")),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_price_history_product_id_products"),
        ),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["product_import_batches.id"],
            name=op.f("fk_product_price_history_import_batch_id"),
        ),
        sa.CheckConstraint(
            "field_name IN ('regular_price', 'website_discounted_price', 'cost_price')",
            name=op.f("ck_product_price_history_field_name_valid"),
        ),
        sa.CheckConstraint(
            "source IN ('csv_import', 'manual', 'other')",
            name=op.f("ck_product_price_history_source_valid"),
        ),
    )
    op.create_index(
        op.f("ix_product_price_history_product_id_changed_at"),
        "product_price_history",
        ["product_id", "changed_at"],
    )

    op.create_table(
        "stock_movements",
        _uuid_pk(),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("movement_type", sa.Text(), nullable=False),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("quantity_before", sa.Integer(), nullable=False),
        sa.Column("quantity_after", sa.Integer(), nullable=False),
        sa.Column("reference_type", sa.Text(), nullable=True),
        sa.Column("reference_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.Column("created_by_name", sa.Text(), nullable=True),
        sa.Column("created_by_device", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_movements")),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_stock_movements_product_id_products"),
        ),
        sa.UniqueConstraint(
            "idempotency_key", name=op.f("uq_stock_movements_idempotency_key")
        ),
        sa.CheckConstraint(
            "movement_type IN ('csv_update', 'stock_count_adjustment', 'delivery_out', "
            "'manual_adjustment', 'return_in', 'reversal')",
            name=op.f("ck_stock_movements_movement_type_valid"),
        ),
        sa.CheckConstraint(
            "quantity_after = quantity_before + quantity_delta",
            name=op.f("ck_stock_movements_quantity_balance"),
        ),
    )
    op.create_index(
        op.f("ix_stock_movements_product_id_created_at"),
        "stock_movements",
        ["product_id", "created_at"],
    )
    op.create_index(
        op.f("ix_stock_movements_reference"),
        "stock_movements",
        ["reference_type", "reference_id"],
    )

    # FR-STOCK-13: movements are never edited or deleted; corrections are reversal movements.
    op.execute(
        """
        CREATE FUNCTION forbid_row_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION USING
                MESSAGE = TG_OP || ' is not allowed on append-only table ' || TG_TABLE_NAME,
                ERRCODE = 'integrity_constraint_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER stock_movements_append_only
        BEFORE UPDATE OR DELETE ON stock_movements
        FOR EACH ROW EXECUTE FUNCTION forbid_row_mutation()
        """
    )


def downgrade() -> None:
    op.drop_table("stock_movements")  # also drops its trigger and indexes
    op.execute("DROP FUNCTION forbid_row_mutation()")
    op.drop_table("product_price_history")
    op.drop_table("product_import_batches")
    op.drop_index(op.f("ix_products_category_id"), table_name="products")
    op.drop_table("products")
    op.drop_table("product_categories")
