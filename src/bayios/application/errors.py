from __future__ import annotations


class ApplicationError(Exception):
    """Base class for expected application/domain failures."""


class ValidationError(ApplicationError):
    """Input or state violates a business rule."""


class NotFoundError(ApplicationError):
    """Requested aggregate does not exist."""


class ConflictError(ApplicationError):
    """Concurrent change or stale snapshot prevents the operation."""


class ProductAlreadyExistsError(ValidationError):
    """A product with the same normalized name is already in the catalog."""


class ProductHasOpenReservationsError(ApplicationError):
    """Product cannot be hard deleted while a reservation line is still open."""
