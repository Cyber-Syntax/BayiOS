from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class HealthReport:
    database_ok: bool
    migrations_ok: bool
    current_revisions: tuple[str, ...] = ()
    expected_revisions: tuple[str, ...] = ()

    @property
    def healthy(self) -> bool:
        return self.database_ok and self.migrations_ok


class HealthProbe(Protocol):
    def check(self) -> HealthReport: ...
