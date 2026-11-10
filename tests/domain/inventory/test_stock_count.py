from datetime import UTC, datetime

import pytest

from bayios.domain.inventory import (
    CountSession,
    MovementType,
    StockSummary,
    complete_count_session,
)


def test_stock_summary_reports_physical_and_open_reservation() -> None:
    summary = StockSummary(physical=2, open_reservation=5)

    assert summary.physical == 2
    assert summary.open_reservation == 5


def test_stock_movement_types_distinguish_csv_delivery_and_count() -> None:
    assert MovementType.CSV_UPDATE.value == "csv_update"
    assert MovementType.DELIVERY_OUT.value == "delivery_out"
    assert MovementType.STOCK_COUNT_ADJUSTMENT.value == "stock_count_adjustment"


def test_count_session_snapshots_quantity_and_completes_adjustment_once() -> None:
    opened_at = datetime(2026, 1, 1, tzinfo=UTC)
    completed_at = datetime(2026, 1, 2, tzinfo=UTC)
    session = CountSession.open(
        category_id="white-goods",
        quantities={"p1": 5},
        stock_version=4,
        opened_at=opened_at,
    )

    completed = complete_count_session(
        session,
        counted_quantities={"p1": 3},
        current_quantities={"p1": 5},
        current_version=4,
        actor_name="Ayşe",
        acknowledge_differences=True,
        completed_at=completed_at,
    )
    retry = complete_count_session(
        completed.session,
        counted_quantities={"p1": 3},
        current_quantities={"p1": 3},
        current_version=4,
        actor_name="Ayşe",
        completed_at=datetime(2026, 1, 3, tzinfo=UTC),
    )

    assert completed.adjustments == {"p1": -2}
    assert completed.movements[0].movement_type is MovementType.STOCK_COUNT_ADJUSTMENT
    assert completed.movements[0].quantity_delta == -2
    assert completed.movements[0].actor_name == "Ayşe"
    assert completed.session.opened_at == opened_at
    assert completed.session.completed_at == completed_at
    assert completed.session.stock_version == 4
    assert completed.actor_name == "Ayşe"
    assert completed.session.completed
    assert retry == completed


def test_count_completion_requires_all_differences_to_be_reviewed() -> None:
    session = CountSession.open(
        category_id="white-goods",
        quantities={"p1": 5},
        stock_version=1,
        opened_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="fark incelemesi"):
        complete_count_session(
            session,
            counted_quantities={"p1": 3},
            current_quantities={"p1": 5},
            current_version=1,
            actor_name=None,
            acknowledge_differences=False,
            completed_at=datetime(2026, 1, 2, tzinfo=UTC),
        )


def test_count_completion_rejects_stale_stock_version() -> None:
    session = CountSession.open(
        category_id="white-goods",
        quantities={"p1": 5},
        stock_version=1,
        opened_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="güncel değil"):
        complete_count_session(
            session,
            counted_quantities={"p1": 5},
            current_quantities={"p1": 6},
            current_version=2,
            actor_name=None,
            completed_at=datetime(2026, 1, 2, tzinfo=UTC),
        )


def test_count_session_requires_explicit_difference_acknowledgement() -> None:
    session = CountSession.open(
        category_id="white-goods",
        quantities={"p1": 5},
        stock_version=1,
        opened_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="fark incelemesi"):
        complete_count_session(
            session,
            counted_quantities={"p1": 3},
            current_quantities={"p1": 5},
            current_version=1,
            actor_name=None,
            completed_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
