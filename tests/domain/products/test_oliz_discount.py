from decimal import Decimal

import pytest

from bayios.domain.products import calculate_oliz_discount


@pytest.mark.parametrize(
    ("regular_price", "oliz_price", "expected"),
    [
        (Decimal("58599.00"), Decimal("48599.00"), Decimal("10000.00")),
        (Decimal("38099.00"), Decimal("34099.00"), Decimal("4000.00")),
        (Decimal("100.00"), Decimal("99.99"), Decimal("0.01")),
        (Decimal("100.00"), Decimal("100.00"), None),
        (Decimal("100.00"), Decimal("120.00"), None),
        (Decimal("100.00"), None, None),
        (None, Decimal("90.00"), None),
        (Decimal("100.00"), Decimal(0), None),
    ],
)
def test_calculate_oliz_discount_returns_only_positive_difference(
    regular_price: Decimal | None,
    oliz_price: Decimal | None,
    expected: Decimal | None,
) -> None:
    assert calculate_oliz_discount(regular_price, oliz_price) == expected
