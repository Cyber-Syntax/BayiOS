from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from bayios.adapters.db.models.products import Product, ProductCategory
from bayios.adapters.db.models.reservations import Reservation, ReservationItem
from bayios.bootstrap import ApplicationSettings
from bayios.main import create_app
from bayios.web.deps import get_unit_of_work
from tests.fakes import FakeUnitOfWork


@pytest.fixture
def fake_uow() -> FakeUnitOfWork:
    uow = FakeUnitOfWork()
    category = ProductCategory(id=uuid.uuid4(), name="Beyaz Eşya")
    uow.products.add_category(category)
    product = Product(
        id=uuid.uuid4(),
        name="07325 A",
        name_normalized="07325 a",
        regular_price=Decimal("38099.00"),
        physical_stock=5,
        category_id=category.id,
        is_archived=False,
    )
    uow.products.add(product)
    return uow


@pytest.fixture
def client(fake_uow: FakeUnitOfWork) -> TestClient:
    settings = ApplicationSettings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/bayios"
    )
    app = create_app(settings)
    app.dependency_overrides[get_unit_of_work] = lambda: fake_uow
    return TestClient(app)


def _add_product(
    fake_uow: FakeUnitOfWork,
    name: str,
    *,
    stock: int,
    category_id: uuid.UUID | None = None,
) -> Product:
    product = Product(
        id=uuid.uuid4(),
        name=name,
        name_normalized=name.lower(),
        regular_price=Decimal("100.00"),
        physical_stock=stock,
        category_id=category_id,
        is_archived=False,
    )
    fake_uow.products.add(product)
    return product


def _open_session(client: TestClient, **data) -> str:
    response = client.post("/stock/sessions", data=data, follow_redirects=False)
    assert response.status_code == 303
    return response.headers["location"].rsplit("/", 1)[-1]


def test_stock_page_lists_stock_summary(client: TestClient) -> None:
    response = client.get("/stock")

    assert response.status_code == 200
    assert "Stok / Sayım" in response.text
    assert "07325 A" in response.text
    assert "Beyaz Eşya" in response.text
    assert "Fiziksel Stok" in response.text
    assert "Satılabilir Stok" not in response.text


def test_stock_page_htmx_returns_results_fragment(client: TestClient) -> None:
    response = client.get("/stock", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "07325 A" in response.text
    assert "Listelenen Ürün" in response.text
    assert "<!doctype html>" not in response.text


def test_zero_and_negative_stock_labels(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    category = next(iter(fake_uow.products.categories.values()))
    _add_product(fake_uow, "Sıfır Ürün", stock=0, category_id=category.id)
    _add_product(fake_uow, "Negatif Ürün", stock=-2, category_id=category.id)

    response = client.get("/stock")

    assert "Stok yok" in response.text
    assert "Stok düzeltmesi gerekli" in response.text


def test_stock_count_flow_saves_and_applies_positive_count(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))
    category = next(iter(fake_uow.products.categories.values()))
    session_id = _open_session(client, category_id=str(category.id), note="Aylık sayım")

    page = client.get(f"/stock/sessions/{session_id}")
    assert page.status_code == 200
    assert "Aylık sayım" in page.text
    assert "Sayımı Kaydet" in page.text
    assert "Ara Kaydet" in page.text

    save = client.post(
        f"/stock/sessions/{session_id}/save",
        data={f"counted_{product.id}": "4"},
        follow_redirects=True,
    )

    assert save.status_code == 200
    assert "Kaydedildi" in save.text
    assert "Tamamlandı" in save.text
    assert product.physical_stock == 4
    movements = fake_uow.products.get_stock_movements(product.id)
    assert len(movements) == 1
    assert movements[0].movement_type == "stock_count_adjustment"
    assert movements[0].quantity_delta == -1


def test_partial_count_can_close_without_touching_uncounted(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    category = next(iter(fake_uow.products.categories.values()))
    counted = _add_product(fake_uow, "Sayılan", stock=5, category_id=category.id)
    skipped = _add_product(fake_uow, "Sayılmayan", stock=8, category_id=category.id)
    session_id = _open_session(client, category_id=str(category.id))

    save = client.post(
        f"/stock/sessions/{session_id}/save",
        data={f"counted_{counted.id}": "3"},
        follow_redirects=True,
    )

    assert save.status_code == 200
    assert "Sayılmayan" in save.text
    assert counted.physical_stock == 3
    assert skipped.physical_stock == 8


def test_zero_count_leaves_stock_unchanged(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))
    session_id = _open_session(client)

    save = client.post(
        f"/stock/sessions/{session_id}/save",
        data={f"counted_{product.id}": "0"},
        follow_redirects=True,
    )

    assert save.status_code == 200
    assert product.physical_stock == 5
    assert fake_uow.products.get_stock_movements(product.id) == []


def test_cancel_open_session_keeps_stock(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))
    session_id = _open_session(client)
    client.post(
        f"/stock/sessions/{session_id}/count",
        data={f"counted_{product.id}": "3"},
        follow_redirects=False,
    )

    response = client.post(
        f"/stock/sessions/{session_id}/cancel",
        data={"reason": "Yanlış kategori"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "İptal edildi" in response.text
    assert "Yanlış kategori" in response.text
    assert product.physical_stock == 5
    assert fake_uow.products.get_stock_movements(product.id) == []

    stock_page = client.get("/stock")
    assert "İptal" in stock_page.text


def test_reverse_completed_session_restores_stock(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))
    session_id = _open_session(client)
    client.post(
        f"/stock/sessions/{session_id}/save",
        data={f"counted_{product.id}": "3"},
        follow_redirects=False,
    )
    assert product.physical_stock == 3

    response = client.post(
        f"/stock/sessions/{session_id}/cancel",
        data={"reason": "Yanlış sayım"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Geri Alındı" in response.text
    assert product.physical_stock == 5
    movements = fake_uow.products.get_stock_movements(product.id)
    assert [movement.movement_type for movement in movements] == [
        "stock_count_adjustment",
        "reversal",
    ]


def test_quick_count_searches_adds_and_saves(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))
    session_id = _open_session(client, mode="quick")

    page = client.get(f"/stock/sessions/{session_id}")
    assert page.status_code == 200
    assert "Ürün Ekle" in page.text
    assert "quick-search" in page.text
    assert "Henüz ürün eklenmedi" in page.text

    lookup = client.get(f"/stock/sessions/{session_id}/lookup?q=07325")
    assert lookup.status_code == 200
    assert "07325 A" in lookup.text
    assert "Ekle" in lookup.text

    added = client.post(
        f"/stock/sessions/{session_id}/items",
        data={"product_id": str(product.id)},
        headers={"HX-Request": "true"},
    )
    assert added.status_code == 200
    assert "07325 A" in added.text
    assert f"counted_{product.id}" in added.text

    save = client.post(
        f"/stock/sessions/{session_id}/save",
        data={f"counted_{product.id}": "4"},
        follow_redirects=True,
    )
    assert save.status_code == 200
    assert product.physical_stock == 4


def test_print_page_is_a5_with_category_and_reservation_columns(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    second_category = ProductCategory(id=uuid.uuid4(), name="Mutfak")
    fake_uow.products.add_category(second_category)
    _add_product(fake_uow, "Mutfak Ürünü", stock=2, category_id=second_category.id)

    response = client.get("/stock/print")

    assert response.status_code == 200
    assert "A5 Sayım Listesi" in response.text
    assert "print-a5.css" in response.text
    assert "Beyaz Eşya" in response.text
    assert "Mutfak" in response.text
    assert "category-row" in response.text
    assert "Fiziksel" in response.text
    assert "Rezervasyon" in response.text
    assert "A4 Sayım Listesi" not in response.text


def test_print_in_stock_only_excludes_zero_and_negative(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    category = next(iter(fake_uow.products.categories.values()))
    _add_product(fake_uow, "Sıfır Ürün", stock=0, category_id=category.id)
    _add_product(fake_uow, "Negatif Ürün", stock=-2, category_id=category.id)

    response = client.get("/stock/print?in_stock=1")

    assert response.status_code == 200
    assert "Sadece Stokta" in response.text
    assert "07325 A" in response.text
    assert "Sıfır Ürün" not in response.text
    assert "Negatif Ürün" not in response.text


def test_print_reserved_only_lists_reserved_products(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    category = next(iter(fake_uow.products.categories.values()))
    reserved = next(iter(fake_uow.products.get_all()))
    _add_product(fake_uow, "Rezervesiz", stock=4, category_id=category.id)
    reservation = Reservation(
        id=uuid.uuid4(),
        customer_name="Test Müşteri",
        reservation_date=datetime.now(UTC),
        reminder_due_at=datetime.now(UTC),
        reminder_status="pending",
    )
    fake_uow.reservations.add(reservation)
    fake_uow.reservations.add_item(
        ReservationItem(
            id=uuid.uuid4(),
            reservation_id=reservation.id,
            product_id=reserved.id,
            product_name_snapshot=reserved.name,
            quantity=2,
            delivered_quantity=0,
            cancelled_quantity=0,
            status="reserved",
        )
    )

    response = client.get(f"/stock/print?category_id={category.id}&reserved_only=1")

    assert response.status_code == 200
    assert "Rezervasyonlu Ürünler" in response.text
    assert "07325 A" in response.text
    assert "Rezervesiz" not in response.text


def test_export_in_stock_only_filters_zero_and_negative(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    category = next(iter(fake_uow.products.categories.values()))
    _add_product(fake_uow, "Sıfır Ürün", stock=0, category_id=category.id)
    _add_product(fake_uow, "Negatif Ürün", stock=-2, category_id=category.id)

    response = client.get("/stock/export/xlsx?in_stock=1")

    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content))
    values = [
        cell
        for row in workbook["Stok"].iter_rows(min_row=2, values_only=True)
        for cell in row
        if cell is not None
    ]
    assert "07325 A" in values
    assert "Sıfır Ürün" not in values
    assert "Negatif Ürün" not in values


def test_stock_page_paginates_product_list(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    category = next(iter(fake_uow.products.categories.values()))
    for i in range(60):
        _add_product(fake_uow, f"Ürün {i:03d}", stock=i, category_id=category.id)

    first = client.get("/stock")
    second = client.get("/stock?page=2")

    assert first.status_code == 200
    assert second.status_code == 200
    assert "Ürün 000" in first.text
    assert "Ürün 059" not in first.text
    assert "Ürün 059" in second.text
    assert "page-jump-input" in first.text


def test_session_page_paginates_items(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    category = next(iter(fake_uow.products.categories.values()))
    for i in range(60):
        _add_product(fake_uow, f"Ürün {i:03d}", stock=i, category_id=category.id)
    session_id = _open_session(client, category_id=str(category.id))

    page_one = client.get(f"/stock/sessions/{session_id}")
    page_two = client.get(f"/stock/sessions/{session_id}?page=2")

    assert page_one.status_code == 200
    assert page_two.status_code == 200
    assert "Toplam 61 satır" in page_one.text
    assert "Ürün 000" in page_one.text
    assert "Ürün 059" not in page_one.text
    assert "Ürün 059" in page_two.text
    assert "page-jump-input" in page_one.text


def test_session_page_has_fixed_save_button(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    category = next(iter(fake_uow.products.categories.values()))
    session_id = _open_session(client, category_id=str(category.id))

    response = client.get(f"/stock/sessions/{session_id}")

    assert response.status_code == 200
    assert "sticky-action-bar" in response.text
    assert 'form="count-form"' in response.text
    assert "Sayımı Kaydet" in response.text
    assert "Ara Kaydet" in response.text
