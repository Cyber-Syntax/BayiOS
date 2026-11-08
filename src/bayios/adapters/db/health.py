from __future__ import annotations

import logging
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from bayios.application.ports.health import HealthReport

logger = logging.getLogger(__name__)


class DatabaseHealthProbe:
    """Healthy only if the DB answers AND its Alembic heads equal the code's heads."""

    def __init__(self, engine: Engine, alembic_ini_path: Path) -> None:
        self._engine = engine
        self._alembic_ini_path = alembic_ini_path

    def check(self) -> HealthReport:
        expected = self._expected_revisions()
        try:
            with self._engine.connect() as connection:
                connection.execute(sa.text("SELECT 1"))
                current = tuple(
                    sorted(MigrationContext.configure(connection).get_current_heads())
                )
        except SQLAlchemyError:
            logger.exception("Database health check failed")
            return HealthReport(
                database_ok=False, migrations_ok=False, expected_revisions=expected
            )

        migrations_ok = bool(expected) and set(current) == set(expected)
        return HealthReport(
            database_ok=True,
            migrations_ok=migrations_ok,
            current_revisions=current,
            expected_revisions=expected,
        )

    def _expected_revisions(self) -> tuple[str, ...]:
        try:
            script = ScriptDirectory.from_config(Config(str(self._alembic_ini_path)))
            return tuple(sorted(script.get_heads()))
        except CommandError:
            logger.exception(
                "Cannot read Alembic scripts via %s", self._alembic_ini_path
            )
            return ()
