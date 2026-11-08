from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self

from bayios.application.ports.products import ProductRepository


class UnitOfWork(Protocol):
    """Transaction boundary. Anything not explicitly committed is rolled back on exit.

    Repositories are attached as attributes by the concrete adapter (added per milestone).
    """

    products: ProductRepository

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
