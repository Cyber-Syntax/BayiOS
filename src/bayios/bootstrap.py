from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session, sessionmaker

from bayios.adapters.db.engine import UTC_CONNECT_ARGS
from bayios.adapters.db.health import DatabaseHealthProbe
from bayios.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from bayios.application.ports.health import HealthProbe
from bayios.application.ports.unit_of_work import UnitOfWork


class ApplicationSettings(BaseSettings):
    """Environment-backed settings. DATABASE_URL is mandatory; there is no SQLite fallback."""

    model_config = SettingsConfigDict(
        env_prefix="BAYIOS_",
        env_file=".env",
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )

    database_url: SecretStr = Field(validation_alias="DATABASE_URL")
    host: str = "127.0.0.1"
    port: int = Field(8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["console", "json"] = "console"
    alembic_ini_path: Path = Path("alembic.ini")

    @field_validator("database_url")
    @classmethod
    def _require_postgres_psycopg(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
        except ArgumentError as exc:
            raise ValueError("DATABASE_URL is not a valid SQLAlchemy URL") from exc
        if url.drivername != "postgresql+psycopg":
            raise ValueError(
                "DATABASE_URL must use the 'postgresql+psycopg://' scheme (PostgreSQL only)"
            )
        return value


@dataclass(frozen=True)
class Container:
    settings: ApplicationSettings
    engine: Engine
    session_factory: sessionmaker[Session]

    def unit_of_work(self) -> UnitOfWork:
        return SqlAlchemyUnitOfWork(self.session_factory)

    def health_probe(self) -> HealthProbe:
        return DatabaseHealthProbe(self.engine, self.settings.alembic_ini_path)

    def dispose(self) -> None:
        self.engine.dispose()


def build_container(settings: ApplicationSettings) -> Container:
    engine = create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=10,
        connect_args=UTC_CONNECT_ARGS,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return Container(settings=settings, engine=engine, session_factory=session_factory)
