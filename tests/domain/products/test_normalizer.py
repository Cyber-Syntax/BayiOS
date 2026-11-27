import pytest

from bayios.domain.products import normalize_product_name


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("  Çamaşır   Makinesi  ", "çamaşır makinesi"),
        ("İ ı I i", "i ı ı i"),
        ("A\u030a", "å"),
    ],
)
def test_normalize_product_name_returns_canonical_name(raw_name: str, expected: str) -> None:
    assert normalize_product_name(raw_name) == expected


def test_normalize_product_name_preserves_leading_zeroes() -> None:
    assert normalize_product_name(" 07325 A ") == "07325 a"

