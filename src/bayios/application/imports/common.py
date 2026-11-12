from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from bayios.adapters.db.models.imports import DataImportBatch
from bayios.application.ports.unit_of_work import UnitOfWork
from bayios.domain.products import ActorContext


@dataclass(frozen=True)
class PreviewRow:
    key: str
    row_number: int
    decision: str
    summary: str
    values: Mapping[str, object]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def is_problematic(self) -> bool:
        return bool(self.errors or self.warnings or self.decision == "error")


@dataclass(frozen=True)
class ImportPreview:
    module: str
    title: str
    entity_label: str
    columns: tuple[tuple[str, str], ...]
    rows: tuple[PreviewRow, ...]
    decision_options: tuple[tuple[str, str], ...]
    unknown_headers: tuple[str, ...] = ()

    @property
    def created_count(self) -> int:
        return sum(1 for row in self.rows if row.decision == "create")

    @property
    def updated_count(self) -> int:
        return sum(1 for row in self.rows if row.decision == "update")

    @property
    def skipped_count(self) -> int:
        return sum(1 for row in self.rows if row.decision == "skip")

    @property
    def error_count(self) -> int:
        return sum(1 for row in self.rows if row.errors or row.decision == "error")


@dataclass(frozen=True)
class ImportResult:
    batch_id: uuid.UUID | None
    created_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    total_count: int


def source_checksum(source: bytes) -> str:
    return hashlib.sha256(source).hexdigest()


def replay_result(
    uow: UnitOfWork, module: str, commit_token: str | None
) -> ImportResult | None:
    if not commit_token:
        return None
    batch = uow.import_batches.get_by_token(commit_token)
    if batch is None or batch.module != module:
        return None
    return _result_from_batch(batch)


def record_batch(
    uow: UnitOfWork,
    *,
    module: str,
    file_name: str,
    file_type: str,
    source: bytes,
    commit_token: str | None,
    created_count: int,
    updated_count: int,
    skipped_count: int,
    error_count: int,
    total_count: int,
    summary: Mapping[str, Any] | None = None,
    actor: ActorContext | None = None,
    now: datetime | None = None,
) -> ImportResult:
    actor = actor or ActorContext()
    moment = now or datetime.now(UTC)
    batch = DataImportBatch(
        id=uuid.uuid4(),
        module=module,
        file_name=file_name,
        file_type=file_type,
        source_checksum=source_checksum(source),
        commit_token=commit_token,
        status="committed",
        row_count=total_count,
        created_count=created_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        error_count=error_count,
        summary=dict(summary) if summary is not None else None,
        started_at=moment,
        completed_at=moment,
        created_by_name=actor.worker_name,
        created_by_device=actor.device_name,
    )
    uow.import_batches.add(batch)
    return ImportResult(
        batch_id=batch.id,
        created_count=created_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        error_count=error_count,
        total_count=total_count,
    )


def result_from_counts(
    *,
    created_count: int,
    updated_count: int,
    skipped_count: int,
    error_count: int,
    total_count: int,
    batch_id: uuid.UUID | None = None,
) -> ImportResult:
    return ImportResult(
        batch_id=batch_id,
        created_count=created_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        error_count=error_count,
        total_count=total_count,
    )


def _result_from_batch(batch: DataImportBatch) -> ImportResult:
    return ImportResult(
        batch_id=batch.id,
        created_count=batch.created_count,
        updated_count=batch.updated_count,
        skipped_count=batch.skipped_count,
        error_count=batch.error_count,
        total_count=batch.row_count,
    )
