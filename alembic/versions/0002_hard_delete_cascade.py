"""cascade product history on hard delete

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-08

PRD FR-PROD-21 allows permanently deleting a product together with its price
and stock history. Stock movements stay append-only for normal operations: the
trigger still rejects direct deletes, but allows the cascade that runs when the
owning product row has already been removed.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_product_price_history_product_id_products",
        "product_price_history",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_product_price_history_product_id_products",
        "product_price_history",
        "products",
        ["product_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint(
        "fk_stock_movements_product_id_products",
        "stock_movements",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_stock_movements_product_id_products",
        "stock_movements",
        "products",
        ["product_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION forbid_row_mutation() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE'
               AND TG_TABLE_NAME = 'stock_movements'
               AND NOT EXISTS (
                   SELECT 1 FROM products WHERE id = OLD.product_id
               ) THEN
                RETURN OLD;
            END IF;

            RAISE EXCEPTION USING
                MESSAGE = TG_OP || ' is not allowed on append-only table ' || TG_TABLE_NAME,
                ERRCODE = 'integrity_constraint_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION forbid_row_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION USING
                MESSAGE = TG_OP || ' is not allowed on append-only table ' || TG_TABLE_NAME,
                ERRCODE = 'integrity_constraint_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )

    op.drop_constraint(
        "fk_stock_movements_product_id_products",
        "stock_movements",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_stock_movements_product_id_products",
        "stock_movements",
        "products",
        ["product_id"],
        ["id"],
    )

    op.drop_constraint(
        "fk_product_price_history_product_id_products",
        "product_price_history",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_product_price_history_product_id_products",
        "product_price_history",
        "products",
        ["product_id"],
        ["id"],
    )
