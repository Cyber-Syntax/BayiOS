from __future__ import annotations

from typing import Protocol

from bayios.adapters.db.models.imports import DataImportBatch


class ImportBatchRepository(Protocol):
    """Audit and idempotency persistence for Excel imports."""

    def get_by_token(self, commit_token: str) -> DataImportBatch | None: ...

    def get_by_checksum(
        self, module: str, source_checksum: str
    ) -> DataImportBatch | None: ...

    def add(self, batch: DataImportBatch) -> None: ...
