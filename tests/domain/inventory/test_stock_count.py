import pytest

from bayios.domain.inventory import (
    CountSession,
    MovementType,
    StockSummary,
    complete_count_session,
)


def test_stock_summary_never_shows_negative_sellable_or_supply_need() -> None:
    summary = StockSummary(physical=2, open_reservation=5)

    assert summary.sellable == 0
    assert summary.supply_need == 3


def test_stock_movement_types_distinguish_csv_delivery_and_count() -> None:
    assert MovementType.CSV_UPDATE.value == "csv_update"
    assert MovementType.DELIVERY_OUT.value == "delivery_out"
    assert MovementType.STOCK_COUNT_ADJUSTMENT.value == "stock_count_adjustment"


def test_count_session_snapshots_quantity_and_completes_adjustment_once() -> None:
    session = CountSession.open(category_id="white-goods", quantities={"p1": 5})

    completed = complete_count_session(
        session,
        counted_quantities={"p1": 3},
        current_quantities={"p1": 5},
        current_version=1,
        actor_name="Ayşe",
    )
    retry = complete_count_session(
        completed.session,
        counted_quantities={"p1": 3},
        current_quantities={"p1": 3},
        current_version=1,
        actor_name="Ayşe",
    )

    assert completed.adjustments == {"p1": -2}
    assert completed.movements[0].movement_type is MovementType.STOCK_COUNT_ADJUSTMENT
    assert completed.movements[0].quantity_delta == -2
    assert completed.movements[0].actor_name == "Ayşe"
    assert completed.actor_name == "Ayşe"
    assert completed.session.completed
    assert retry == completed


def test_count_completion_requires_all_differences_to_be_reviewed() -> None:
    session = CountSession.open(category_id="white-goods", quantities={"p1": 5})

    with pytest.raises(ValueError, match="difference"):
        complete_count_session(
            session,
            counted_quantities={"p1": 3},
            current_quantities={"p1": 5},
            current_version=1,
            actor_name=None,
            acknowledge_differences=False,
        )


def test_count_completion_rejects_stale_stock_version() -> None:
    session = CountSession.open(category_id="white-goods", quantities={"p1": 5})

    with pytest.raises(ValueError, match="stale"):
        complete_count_session(
            session,
            counted_quantities={"p1": 5},
            current_quantities={"p1": 6},
            current_version=2,
            actor_name=None,
        )
