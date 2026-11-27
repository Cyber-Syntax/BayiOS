"""merge duplicate case variants of default categories

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MERGES = (
    ("Klima", ("klima",), "klima"),
    ("TV", ("tv", "televizyon"), "tv"),
    ("Çamaşır Makinesi", ("çamaşır makinesi", "çamaşır"), "other"),
    ("Bulaşık Makinesi", ("bulaşık makinesi", "bulaşık"), "other"),
    ("Buzdolabı", ("buzdolabı", "buz dolabı"), "other"),
)


def upgrade() -> None:
    bind = op.get_bind()
    for canonical_name, aliases, group in MERGES:
        names = [canonical_name.lower(), *aliases]
        rows = bind.execute(
            sa.text(
                "SELECT id, name FROM product_categories "
                "WHERE lower(name) IN :names"
            ).bindparams(
                sa.bindparam("names", expanding=True, value=names)
            )
        ).all()
        if not rows:
            continue
        canonical = next(
            (row for row in rows if row.name == canonical_name), rows[0]
        )
        duplicate_ids = [row.id for row in rows if row.id != canonical[0]]
        if duplicate_ids:
            bind.execute(
                sa.text(
                    "UPDATE products SET category_id = :canonical_id "
                    "WHERE category_id IN :duplicate_ids"
                ).bindparams(
                    sa.bindparam("canonical_id", value=canonical[0]),
                    sa.bindparam(
                        "duplicate_ids", expanding=True, value=duplicate_ids
                    ),
                )
            )
            bind.execute(
                sa.text(
                    "DELETE FROM product_categories WHERE id IN :duplicate_ids"
                ).bindparams(
                    sa.bindparam(
                        "duplicate_ids", expanding=True, value=duplicate_ids
                    )
                )
            )
        bind.execute(
            sa.text(
                "UPDATE product_categories "
                "SET name = :name, commission_group = :group "
                "WHERE id = :id"
            ).bindparams(
                name=canonical_name,
                group=group,
                id=canonical[0],
            )
        )


def downgrade() -> None:
    # Data merge is irreversible; no automatic split of merged categories.
    pass
