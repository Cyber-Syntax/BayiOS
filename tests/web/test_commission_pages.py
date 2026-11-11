from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from bayios.bootstrap import ApplicationSettings
from bayios.main import create_app
from bayios.web.deps import get_unit_of_work
from tests.fakes import FakeUnitOfWork


@pytest.fixture
def fake_uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def client(fake_uow: FakeUnitOfWork) -> TestClient:
    settings = ApplicationSettings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/bayios"
    )
    app = create_app(settings)
    app.dependency_overrides[get_unit_of_work] = lambda: fake_uow
    return TestClient(app)


def test_commission_period_page_and_nav(client: TestClient) -> None:
    response = client.get("/commissions")

    assert response.status_code == 200
    assert "Komisyonlar" in response.text
    assert "Komisyonlar (yakında)" not in response.text
    assert "Yeni Dönem" in response.text


def test_create_period_add_rate_and_activate(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    created = client.post(
        "/commissions",
        data={"year": "2026", "month": "11"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    location = created.headers["location"]

    detail = client.get(location)
    assert detail.status_code == 200
    assert "2026-11" in detail.text

    rate = client.post(
        f"{location}/rates",
        data={
            "channel": "chippin",
            "product_group": "other",
            "installment_count": "2",
            "commission_percent": "4",
        },
        follow_redirects=False,
    )
    assert rate.status_code == 303
    detail = client.get(location)
    assert 'name="commission_percent" value="4"' in detail.text

    activated = client.post(f"{location}/activate", follow_redirects=False)
    assert activated.status_code == 303
    detail = client.get(location)
    assert "Aktif" in detail.text


def test_limit_edit_delete_and_period_deactivate_delete(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    created = client.post(
        "/commissions",
        data={"year": "2026", "month": "11"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    location = created.headers["location"]
    period_id = next(iter(fake_uow.commissions.periods))

    added = client.post(
        f"{location}/limits",
        data={"product_group": "klima", "max_installments": "10"},
        follow_redirects=False,
    )
    assert added.status_code == 303
    limit = fake_uow.commissions.limits[period_id][0]
    assert limit.max_installments == 10

    edited = client.post(
        f"{location}/limits/{limit.id}/edit",
        data={"max_installments": "7"},
        follow_redirects=False,
    )
    assert edited.status_code == 303
    assert limit.max_installments == 7

    deleted = client.post(
        f"{location}/limits/{limit.id}/delete",
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert fake_uow.commissions.limits[period_id] == []

    client.post(f"{location}/activate", follow_redirects=False)
    period = fake_uow.commissions.periods[period_id]
    assert period.status == "active"

    deactivated = client.post(
        f"{location}/deactivate", follow_redirects=False
    )
    assert deactivated.status_code == 303
    assert period.status == "inactive"

    removed = client.post(f"{location}/delete", follow_redirects=False)
    assert removed.status_code == 303
    assert period_id not in fake_uow.commissions.periods


def test_chippin_rate_without_group_can_be_edited_and_deleted(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    created = client.post(
        "/commissions",
        data={"year": "2026", "month": "11"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    location = created.headers["location"]
    period_id = next(iter(fake_uow.commissions.periods))

    added = client.post(
        f"{location}/rates",
        data={
            "channel": "chippin",
            "product_group": "",
            "installment_count": "2",
            "commission_percent": "4",
        },
        follow_redirects=False,
    )
    assert added.status_code == 303
    rate = fake_uow.commissions.rates[period_id][0]
    assert rate.product_group is None

    edited = client.post(
        f"{location}/rates/{rate.id}/edit",
        data={"commission_percent": "5"},
        follow_redirects=False,
    )
    assert edited.status_code == 303
    assert rate.commission_percent == Decimal(5)

    deleted = client.post(
        f"{location}/rates/{rate.id}/delete",
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert fake_uow.commissions.rates[period_id] == []


def test_duplicate_commission_rate_shows_validation_error(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    created = client.post(
        "/commissions",
        data={"year": "2026", "month": "11"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    location = created.headers["location"]
    period_id = next(iter(fake_uow.commissions.periods))
    data = {
        "channel": "chippin",
        "product_group": "other",
        "installment_count": "2",
        "commission_percent": "4",
    }

    first = client.post(
        f"{location}/rates", data=data, follow_redirects=False
    )
    second = client.post(
        f"{location}/rates", data=data, follow_redirects=False
    )

    assert first.status_code == 303
    assert second.status_code == 303
    page = client.get(second.headers["location"])
    assert "zaten tanımlı" in page.text
    assert len(fake_uow.commissions.rates[period_id]) == 1
