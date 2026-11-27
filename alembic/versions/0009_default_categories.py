"""seed default product categories and commission groups

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_CATEGORIES = (
    ("Klima", "klima"),
    ("TV", "tv"),
    ("Çamaşır Makinesi", "other"),
    ("Bulaşık Makinesi", "other"),
    ("Buzdolabı", "other"),
    ("Fırın", "other"),
    ("Ocak", "other"),
    ("Davlumbaz", "other"),
    ("Mikrodalga", "other"),
    ("Süpürge", "other"),
)


def upgrade() -> None:
    for name, group in DEFAULT_CATEGORIES:
        op.execute(
            sa.text(
                "INSERT INTO product_categories (id, name, commission_group) "
                "VALUES (gen_random_uuid(), :name, :group) "
                "ON CONFLICT (name) DO UPDATE "
                "SET commission_group = EXCLUDED.commission_group"
            ).bindparams(name=name, group=group)
        )
    op.execute(
        "UPDATE product_categories SET commission_group = 'klima' "
        "WHERE lower(name) LIKE '%klima%'"
    )
    op.execute(
        "UPDATE product_categories SET commission_group = 'tv' "
        "WHERE lower(name) LIKE '%tv%' OR lower(name) LIKE '%televizyon%'"
    )


def downgrade() -> None:
    names = tuple(name for name, _ in DEFAULT_CATEGORIES)
    op.execute(
        sa.text(
            "DELETE FROM product_categories "
            "WHERE name IN :names "
            "AND NOT EXISTS ("
            "SELECT 1 FROM products WHERE products.category_id = product_categories.id"
            ")"
        ).bindparams(sa.bindparam("names", expanding=True, value=list(names)))
    )
