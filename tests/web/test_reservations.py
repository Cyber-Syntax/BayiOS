from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from bayios.adapters.db.models.products import Product
from bayios.application.reservations import NewReservationItem, create_reservation
from bayios.bootstrap import ApplicationSettings
from bayios.main import create_app
from bayios.web.deps import get_unit_of_work
from tests.fakes import FakeUnitOfWork

TODAY = datetime.now(UTC).date().isoformat()


@pytest.fixture
def fake_uow() -> FakeUnitOfWork:
    uow = FakeUnitOfWork()
    product = Product(
        id=uuid.uuid4(),
        name="07325 A",
        name_normalized="07325 a",
        regular_price=Decimal("38099.00"),
        physical_stock=5,
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


def _product(fake_uow: FakeUnitOfWork) -> Product:
    return next(iter(fake_uow.products.get_all()))


def _create_via_ui(client: TestClient, fake_uow: FakeUnitOfWork, quantity: int = 2) -> str:
    product = _product(fake_uow)
    response = client.post(
        "/reservations",
        data={
            "customer_name": "Ayşe Yılmaz",
            "reservation_date": TODAY,
            "note": "Kapıda teslim",
            "product_id": str(product.id),
            "quantity": str(quantity),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return response.headers["location"].split("?")[0]


def _item_id(fake_uow: FakeUnitOfWork) -> uuid.UUID:
    bucket = next(iter(fake_uow.reservations.items.values()))
    return bucket[0].id


def test_reservation_list_page_renders_and_nav_is_enabled(
    client: TestClient,
) -> None:
    response = client.get("/reservations")

    assert response.status_code == 200
    assert "Rezervasyonlar" in response.text
    assert 'href="/reservations/new"' in response.text
    assert "Bu filtreye uyan rezervasyon bulunmuyor." in response.text
    assert "Rezervasyonlar (yakında)" not in response.text
    assert 'href="/reservations"' in response.text


def test_create_reservation_from_ui_redirects_to_detail(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    location = _create_via_ui(client, fake_uow, quantity=2)
    page = client.get(location)

    assert page.status_code == 200
    assert "Ayşe Yılmaz" in page.text
    assert "Rezerveli" in page.text
    assert "Kapıda teslim" in page.text
    assert "Teslim Et" in page.text
    assert "A4 (Depo + Bayi)" in page.text
    assert _product(fake_uow).physical_stock == 5


def test_create_requires_customer_name_in_ui(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    response = client.post(
        "/reservations",
        data={
            "customer_name": " ",
            "product_id": str(_product(fake_uow).id),
            "quantity": "1",
        },
    )

    assert response.status_code == 400
    assert "Müşteri adı zorunludur." in response.text


def test_dates_are_shown_in_turkish_format(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = _product(fake_uow)

    response = client.post(
        "/reservations",
        data={
            "customer_name": "Ayşe Yılmaz",
            "reservation_date": "10.11.2026",
            "product_id": str(product.id),
            "quantity": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    reservation = next(iter(fake_uow.reservations.reservations.values()))
    assert reservation.reservation_date.date() == date(2026, 11, 10)

    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert "10 Kasım 2026" in page.text
    assert "10 Aralık 2027" in page.text


def test_new_reservation_date_input_has_picker_without_preview(
    client: TestClient,
) -> None:
    page = client.get("/reservations/new")

    assert page.status_code == 200
    assert 'name="reservation_date"' in page.text
    assert "data-date-picker" in page.text
    assert f'value="{TODAY}"' in page.text
    assert "reservation-date-preview" not in page.text


def test_create_error_keeps_submitted_reservation_date(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    response = client.post(
        "/reservations",
        data={
            "customer_name": " ",
            "reservation_date": "2026-11-10",
            "product_id": str(_product(fake_uow).id),
            "quantity": "1",
        },
    )

    assert response.status_code == 400
    assert "Müşteri adı zorunludur." in response.text
    assert 'name="reservation_date"' in response.text
    assert 'value="2026-11-10"' in response.text
    assert f'value="{TODAY}"' not in response.text


def test_detail_date_fields_use_turkish_picker(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = _product(fake_uow)
    create_reservation(
        fake_uow,
        "Ayşe Yılmaz",
        [NewReservationItem(product.id, 1)],
        reservation_date=datetime(2026, 11, 10, 9, tzinfo=UTC),
    )
    reservation = next(iter(fake_uow.reservations.reservations.values()))

    page = client.get(f"/reservations/{reservation.id}")

    assert page.status_code == 200
    assert 'name="service_date"' in page.text
    assert 'placeholder="Servis tarihi"' in page.text
    assert 'data-date-picker data-date-preview="edit-date-preview"' in page.text
    assert 'id="edit-date-preview"' in page.text
    assert "10 Kasım 2026" in page.text
    assert 'data-date-picker data-date-preview="snooze-date-preview"' in page.text


def test_layout_loads_local_turkish_picker_assets(client: TestClient) -> None:
    page = client.get("/reservations")

    assert page.status_code == 200
    assert "/static/vendor/flatpickr/flatpickr.min.css" in page.text
    assert "/static/vendor/flatpickr/flatpickr.min.js" in page.text
    assert "/static/vendor/flatpickr/l10n/tr.js" in page.text
    assert "/static/js/date-picker.js" in page.text
    assert "unpkg.com" not in page.text
    assert "cdn.jsdelivr" not in page.text


def test_create_redirect_shows_success_banner(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = _product(fake_uow)

    response = client.post(
        "/reservations",
        data={
            "customer_name": "Ayşe Yılmaz",
            "product_id": str(product.id),
            "quantity": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "msg=created" in response.headers["location"]

    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert "Rezervasyon oluşturuldu." in page.text
    assert "İşlem yapılamadı" not in page.text


def test_status_deliver_and_cancel_flow_through_ui(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    location = _create_via_ui(client, fake_uow, quantity=3)
    reservation_id = location.rsplit("/", 1)[-1]
    item_id = _item_id(fake_uow)

    status_response = client.post(
        f"/reservations/{reservation_id}/items/{item_id}/status",
        data={"target_status": "service_assigned", "note": "Servis atandı"},
        follow_redirects=False,
    )
    assert status_response.status_code == 303

    deliver_response = client.post(
        f"/reservations/{reservation_id}/items/{item_id}/deliver",
        data={"quantity": "1", "idempotency_key": "ui-delivery-1"},
        follow_redirects=False,
    )
    assert deliver_response.status_code == 303

    cancel_response = client.post(
        f"/reservations/{reservation_id}/items/{item_id}/cancel",
        data={"quantity": "1", "note": "Müşteri vazgeçti"},
        follow_redirects=False,
    )
    assert cancel_response.status_code == 303

    detail = client.get(f"/reservations/{reservation_id}?msg=delivered")
    assert detail.status_code == 200
    assert "Teslimat kaydedildi" in detail.text
    assert "Kısmi süreçte" in detail.text
    assert _product(fake_uow).physical_stock == 4
    assert len(fake_uow.products.stock_movements) == 1


def test_low_stock_delivery_error_is_shown(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    location = _create_via_ui(client, fake_uow, quantity=3)
    reservation_id = location.rsplit("/", 1)[-1]
    _product(fake_uow).physical_stock = 1

    response = client.get(
        f"/reservations/{reservation_id}?msg=error:Fiziksel stok yetersiz; teslim için gerekçe girilmelidir."
    )

    assert response.status_code == 200
    assert "gerekçe girilmelidir" in response.text


def test_failed_delivery_redirects_with_encoded_error(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    location = _create_via_ui(client, fake_uow, quantity=3)
    reservation_id = location.rsplit("/", 1)[-1]
    item_id = _item_id(fake_uow)
    _product(fake_uow).physical_stock = 1

    response = client.post(
        f"/reservations/{reservation_id}/items/{item_id}/deliver",
        data={"quantity": "3", "idempotency_key": "fail-1"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "error%3A" in response.headers["location"]
    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert "gerekçe girilmelidir" in page.text


def test_snooze_shows_history_and_new_label(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    location = _create_via_ui(client, fake_uow, quantity=1)
    reservation_id = location.rsplit("/", 1)[-1]

    response = client.post(
        f"/reservations/{reservation_id}/reminder/snooze",
        data={"new_due_at": "", "note": "Müşteri arandı"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    detail = client.get(f"/reservations/{reservation_id}?msg=snoozed")
    assert detail.status_code == 200
    assert "Hatırlatma ertelendi" in detail.text
    assert "Ertelendi" in detail.text
    assert "Müşteri arandı" in detail.text


def test_print_both_copies_and_single_copy(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    location = _create_via_ui(client, fake_uow, quantity=2)
    reservation_id = location.rsplit("/", 1)[-1]

    both = client.get(f"/reservations/{reservation_id}/print?copy=both")
    assert both.status_code == 200
    assert "DEPO KOPYASI" in both.text
    assert "BAYİ KOPYASI" in both.text
    assert "print-page-break" in both.text

    depot = client.get(f"/reservations/{reservation_id}/print?copy=depot")
    assert "DEPO KOPYASI" in depot.text
    assert "BAYİ KOPYASI" not in depot.text

    listing = client.get("/reservations/print?status=open")
    assert listing.status_code == 200
    assert "BayiOS Rezervasyon Listesi" in listing.text
    assert "Ayşe Yılmaz" in listing.text


def test_htmx_list_fragment(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    _create_via_ui(client, fake_uow, quantity=1)

    response = client.get("/reservations?status=open", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "Ayşe Yılmaz" in response.text
    assert "<!doctype html>" not in response.text


def test_home_lists_overdue_reminders(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = _product(fake_uow)
    create_reservation(
        fake_uow,
        "Gecikmiş Müşteri",
        [NewReservationItem(product.id, 1)],
        reservation_date=datetime(2024, 1, 15, tzinfo=UTC),
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "Rezervasyon Hatırlatmaları" in response.text
    assert "Gecikmiş Müşteri" in response.text
    assert "Gecikmiş" in response.text


def test_product_detail_links_to_new_reservation(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = _product(fake_uow)

    detail = client.get(f"/products/{product.id}")
    new_page = client.get(f"/reservations/new?product_id={product.id}")

    assert detail.status_code == 200
    assert f"/reservations/new?product_id={product.id}" in detail.text
    assert new_page.status_code == 200
    assert "07325 A" in new_page.text
    assert "Rezervasyonu Kaydet" in new_page.text


def test_delete_products_blocked_by_open_reservation(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = _product(fake_uow)
    create_reservation(
        fake_uow,
        "Ayşe Yılmaz",
        [NewReservationItem(product.id, 1)],
    )

    response = client.post(
        "/products/bulk-delete",
        data={
            "product_ids": str(product.id),
            "confirmed": "yes_delete_permanently",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("msg=delete_blocked")
    assert product.id in fake_uow.products.products
