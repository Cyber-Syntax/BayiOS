from datetime import UTC, datetime

import pytest

from bayios.domain.inventory import (
    CountSession,
    MovementType,
    StockStatus,
    StockSummary,
    complete_count_session,
    reverse_count_session,
    stock_status,
)


def test_stock_summary_reports_physical_and_open_reservation() -> None:
    summary = StockSummary(physical=2, open_reservation=5)

    assert summary.physical == 2
    assert summary.open_reservation == 5


def test_stock_movement_types_distinguish_csv_delivery_count_and_reversal() -> None:
    assert MovementType.CSV_UPDATE.value == "csv_update"
    assert MovementType.DELIVERY_OUT.value == "delivery_out"
    assert MovementType.STOCK_COUNT_ADJUSTMENT.value == "stock_count_adjustment"
    assert MovementType.REVERSAL.value == "reversal"


def test_zero_means_out_of_stock_and_negative_stays_visible() -> None:
    assert stock_status(3) is StockStatus.IN_STOCK
    assert stock_status(0) is StockStatus.OUT_OF_STOCK
    assert stock_status(-2) is StockStatus.NEGATIVE


def test_count_applies_only_positive_quantities_and_skips_uncounted() -> None:
    opened_at = datetime(2026, 1, 1, tzinfo=UTC)
    completed_at = datetime(2026, 1, 2, tzinfo=UTC)
    session = CountSession.open(
        category_id="white-goods",
        quantities={"p1": 5, "p2": 8},
        stock_version=4,
        opened_at=opened_at,
    )

    completed = complete_count_session(
        session,
        counted_quantities={"p1": 3},
        current_quantities={"p1": 5},
        actor_name="Ayşe",
        completed_at=completed_at,
    )

    assert completed.adjustments == {"p1": -2}
    assert completed.movements[0].movement_type is MovementType.STOCK_COUNT_ADJUSTMENT
    assert completed.movements[0].quantity_delta == -2
    assert completed.movements[0].actor_name == "Ayşe"
    assert completed.counted_count == 1
    assert completed.skipped_count == 1
    assert completed.session.completed
    assert completed.session.completed_at == completed_at
    assert completed.session.adjustments == {"p1": -2}


def test_count_ignores_zero_and_uncounted_lines() -> None:
    session = CountSession.open(
        category_id="white-goods",
        quantities={"p1": 5, "p2": 8},
        stock_version=1,
        opened_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    completed = complete_count_session(
        session,
        counted_quantities={"p1": 0},
        current_quantities={},
        actor_name=None,
        completed_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert completed.adjustments == {}
    assert completed.movements == ()
    assert completed.counted_count == 0
    assert completed.skipped_count == 2


def test_count_is_idempotent_once_completed() -> None:
    session = CountSession.open(
        category_id="white-goods",
        quantities={"p1": 5},
        stock_version=4,
        opened_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    completed = complete_count_session(
        session,
        counted_quantities={"p1": 3},
        current_quantities={"p1": 5},
        actor_name="Ayşe",
        completed_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    retry = complete_count_session(
        completed.session,
        counted_quantities={"p1": 1},
        current_quantities={"p1": 1},
        actor_name="Ayşe",
        completed_at=datetime(2026, 1, 3, tzinfo=UTC),
    )

    assert retry == completed


def test_count_rejects_stock_changed_after_snapshot() -> None:
    session = CountSession.open(
        category_id="white-goods",
        quantities={"p1": 5},
        stock_version=1,
        opened_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="stok değişti"):
        complete_count_session(
            session,
            counted_quantities={"p1": 3},
            current_quantities={"p1": 4},
            actor_name=None,
            completed_at=datetime(2026, 1, 2, tzinfo=UTC),
        )


def test_reverse_count_restores_pre_count_stock() -> None:
    session = CountSession.open(
        category_id="white-goods",
        quantities={"p1": 5},
        stock_version=1,
        opened_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    completed = complete_count_session(
        session,
        counted_quantities={"p1": 3},
        current_quantities={"p1": 5},
        actor_name="Ayşe",
        completed_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    reversal = reverse_count_session(
        completed.session,
        completed.movements,
        {"p1": 3},
        "Mehmet",
        reversed_at=datetime(2026, 1, 3, tzinfo=UTC),
    )

    assert len(reversal.movements) == 1
    movement = reversal.movements[0]
    assert movement.movement_type is MovementType.REVERSAL
    assert movement.quantity_delta == 2
    assert movement.quantity_before == 3
    assert movement.quantity_after == 5
    assert movement.actor_name == "Mehmet"


def test_reverse_count_refuses_when_stock_changed_after_count() -> None:
    session = CountSession.open(
        category_id="white-goods",
        quantities={"p1": 5},
        stock_version=1,
        opened_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    completed = complete_count_session(
        session,
        counted_quantities={"p1": 3},
        current_quantities={"p1": 5},
        actor_name=None,
        completed_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="stok değişti"):
        reverse_count_session(
            completed.session,
            completed.movements,
            {"p1": 2},
            None,
            reversed_at=datetime(2026, 1, 3, tzinfo=UTC),
        )
