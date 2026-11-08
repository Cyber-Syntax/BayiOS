from sqlalchemy import create_engine, pool

from alembic import context
from bayios.adapters.db.engine import UTC_CONNECT_ARGS
from bayios.adapters.db.models import Base
from bayios.bootstrap import ApplicationSettings

if context.is_offline_mode():
    raise RuntimeError(
        "Offline (--sql) migrations are not supported; run against a live PostgreSQL."
    )


def run_migrations_online() -> None:
    settings = ApplicationSettings()
    engine = create_engine(
        settings.database_url.get_secret_value(),
        poolclass=pool.NullPool,
        connect_args=UTC_CONNECT_ARGS,
    )
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
