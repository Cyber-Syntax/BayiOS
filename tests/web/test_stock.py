from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from bayios.adapters.db.models.products import Product, ProductCategory
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


def test_stock_count_flow_updates_stock_and_history(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))
    category = next(iter(fake_uow.products.categories.values()))

    open_res = client.post(
        "/stock/sessions",
        data={"category_id": str(category.id), "note": "Aylık sayım"},
        follow_redirects=False,
    )
    assert open_res.status_code == 303
    location = open_res.headers["location"]
    assert location.startswith("/stock/sessions/")

    session_id = location.rsplit("/", 1)[-1]
    page = client.get(location)
    assert page.status_code == 200
    assert "Aylık sayım" in page.text
    assert "Sayılan Miktar" in page.text

    save_res = client.post(
        f"/stock/sessions/{session_id}/count",
        data={f"counted_{product.id}": "3"},
        follow_redirects=False,
    )
    assert save_res.status_code == 303
    assert "msg=counts_saved" in save_res.headers["location"]

    review = client.get(f"/stock/sessions/{session_id}")
    assert review.status_code == 200
    assert "Fark İncelemesi" in review.text
    assert "Sayımı Tamamla" in review.text

    complete_res = client.post(
        f"/stock/sessions/{session_id}/complete",
        data={"acknowledge_differences": "on"},
        follow_redirects=True,
    )
    assert complete_res.status_code == 200
    assert "Sayım tamamlandı" in complete_res.text

    assert product.physical_stock == 3
    movements = fake_uow.products.get_stock_movements(product.id)
    assert len(movements) == 1
    assert movements[0].movement_type == "stock_count_adjustment"
    assert movements[0].quantity_delta == -2


def test_complete_without_acknowledging_differences_returns_error(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))
    open_res = client.post(
        "/stock/sessions", data={}, follow_redirects=False
    )
    session_id = open_res.headers["location"].rsplit("/", 1)[-1]
    client.post(
        f"/stock/sessions/{session_id}/count",
        data={f"counted_{product.id}": "1"},
        follow_redirects=False,
    )

    response = client.post(
        f"/stock/sessions/{session_id}/complete",
        data={},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "fark incelemesi" in response.text
    assert product.physical_stock == 5


def test_print_page_has_hand_writable_columns(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    category = next(iter(fake_uow.products.categories.values()))

    response = client.get(f"/stock/print?category_id={category.id}")

    assert response.status_code == 200
    assert "A4 Sayım Listesi" in response.text
    assert "07325 A" in response.text
    assert "Sayılan Miktar" in response.text
    assert "Fark" in response.text


def _add_products(fake_uow: FakeUnitOfWork, category_id: uuid.UUID, count: int) -> None:
    for i in range(count):
        fake_uow.products.add(
            Product(
                id=uuid.uuid4(),
                name=f"Ürün {i:03d}",
                name_normalized=f"ürün {i:03d}",
                regular_price=Decimal("100.00"),
                physical_stock=i,
                category_id=category_id,
            )
        )


def test_stock_page_lists_open_sessions_at_top(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    category = next(iter(fake_uow.products.categories.values()))

    open_res = client.post(
        "/stock/sessions",
        data={"category_id": str(category.id), "note": "Aylık sayım"},
        follow_redirects=False,
    )
    session_id = open_res.headers["location"].rsplit("/", 1)[-1]

    response = client.get("/stock")

    assert response.status_code == 200
    assert "Açık Sayım Oturumları" in response.text
    assert "Devam Et" in response.text
    assert "Sayım Geçmişi" in response.text
    assert f"/stock/sessions/{session_id}" in response.text


def test_stock_page_paginates_product_list(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    category = next(iter(fake_uow.products.categories.values()))
    _add_products(fake_uow, category.id, 60)

    first = client.get("/stock")
    second = client.get("/stock?page=2")

    assert first.status_code == 200
    assert second.status_code == 200
    assert "Ürün 000" in first.text
    assert "Ürün 059" not in first.text
    assert "Ürün 059" in second.text
    assert "Git" in first.text
    assert "page-jump-input" in first.text


def test_session_page_paginates_items(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    category = next(iter(fake_uow.products.categories.values()))
    _add_products(fake_uow, category.id, 60)

    open_res = client.post(
        "/stock/sessions",
        data={"category_id": str(category.id)},
        follow_redirects=False,
    )
    location = open_res.headers["location"]

    page_one = client.get(location)
    page_two = client.get(f"{location}?page=2")

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

    open_res = client.post(
        "/stock/sessions",
        data={"category_id": str(category.id)},
        follow_redirects=False,
    )
    location = open_res.headers["location"]

    response = client.get(location)

    assert response.status_code == 200
    assert "sticky-action-bar" in response.text
    assert 'form="count-form"' in response.text
    assert "Miktarları Kaydet" in response.text
