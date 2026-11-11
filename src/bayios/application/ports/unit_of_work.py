from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self

from bayios.application.ports.campaigns import CampaignRepository
from bayios.application.ports.commissions import CommissionRepository
from bayios.application.ports.dealer_pricing import DealerPricingRepository
from bayios.application.ports.offers import OfferRepository
from bayios.application.ports.products import ProductRepository
from bayios.application.ports.reservations import ReservationRepository
from bayios.application.ports.stock_counts import StockCountRepository


class UnitOfWork(Protocol):
    """Transaction boundary. Anything not explicitly committed is rolled back on exit.

    Repositories are attached as attributes by the concrete adapter (added per milestone).
    """

    products: ProductRepository
    stock_counts: StockCountRepository
    reservations: ReservationRepository
    campaigns: CampaignRepository
    dealer_pricing: DealerPricingRepository
    commissions: CommissionRepository
    offers: OfferRepository

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
