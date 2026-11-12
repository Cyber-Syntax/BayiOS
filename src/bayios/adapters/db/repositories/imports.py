from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from bayios.adapters.db.models.imports import DataImportBatch


class SqlAlchemyImportBatchRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_token(self, commit_token: str) -> DataImportBatch | None:
        return self._session.scalar(
            sa.select(DataImportBatch).where(
                DataImportBatch.commit_token == commit_token
            )
        )

    def get_by_checksum(
        self, module: str, source_checksum: str
    ) -> DataImportBatch | None:
        return self._session.scalar(
            sa.select(DataImportBatch)
            .where(
                DataImportBatch.module == module,
                DataImportBatch.source_checksum == source_checksum,
            )
            .order_by(DataImportBatch.started_at.desc())
        )

    def add(self, batch: DataImportBatch) -> None:
        self._session.add(batch)
        self._session.flush()
