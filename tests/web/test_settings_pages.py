from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bayios.bootstrap import ApplicationSettings
from bayios.main import create_app
from bayios.web.deps import get_unit_of_work
from tests.fakes import FakeUnitOfWork


def test_empty_bulk_preview_shows_validation_message(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    empty = client.post(
        "/settings/banks/bulk-preview",
        data={"names": "   "},
        follow_redirects=False,
    )
    assert empty.status_code == 303
    page = client.get(empty.headers["location"])
    assert "En az bir ad girilmelidir" in page.text

    missing = client.post(
        "/settings/categories/bulk-preview",
        data={},
        follow_redirects=False,
    )
    assert missing.status_code == 303
    page = client.get(missing.headers["location"])
    assert "En az bir ad girilmelidir" in page.text


def test_used_bank_requires_force_to_delete_with_rates(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    import uuid
    from datetime import UTC, datetime

    from bayios.adapters.db.models.commissions import (
        CommissionPeriod,
        CommissionRate,
    )

    client.post("/settings/banks", data={"name": "Silinecek"})
    bank = next(iter(fake_uow.commissions.banks.values()))
    period = CommissionPeriod(
        id=uuid.uuid4(),
        period_key="2026-11",
        valid_from=datetime(2026, 11, 1, tzinfo=UTC),
        valid_until=datetime(2026, 11, 30, tzinfo=UTC),
        status="inactive",
    )
    fake_uow.commissions.add_period(period)
    fake_uow.commissions.add_rate(
        CommissionRate(
            id=uuid.uuid4(),
            period_id=period.id,
            channel="pos",
            bank_id=bank.id,
            product_group="other",
            installment_count=2,
            commission_percent=4,
            scope_key=f"pos|{bank.id}|other|-|2",
        )
    )

    blocked = client.post(
        f"/settings/banks/{bank.id}/delete",
        data={"confirm": "1"},
        follow_redirects=False,
    )
    assert blocked.status_code == 303
    assert bank.id in fake_uow.commissions.banks
    page = client.get(blocked.headers["location"])
    assert "silme onayını" in page.text

    forced = client.post(
        f"/settings/banks/{bank.id}/delete",
        data={"confirm": "1", "force": "1"},
        follow_redirects=False,
    )
    assert forced.status_code == 303
    assert bank.id not in fake_uow.commissions.banks
    assert fake_uow.commissions.rates[period.id] == []



def test_bank_card_networks_update(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    client.post("/settings/banks", data={"name": "Yapı Kredi"})
    bank = next(iter(fake_uow.commissions.banks.values()))
    response = client.post(
        f"/settings/banks/{bank.id}/card-networks",
        data={"card_networks": "World, Bonus"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert bank.card_networks == ["World", "Bonus"]
    page = client.get(response.headers["location"])
    assert "World" in page.text
    assert "Bonus" in page.text


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


def test_bank_settings_page_and_single_add(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    page = client.get("/settings/banks")
    assert page.status_code == 200
    assert "Bankalar" in page.text

    created = client.post(
        "/settings/banks", data={"name": "AKBANK"}, follow_redirects=False
    )
    assert created.status_code == 303
    bank = next(iter(fake_uow.commissions.banks.values()))
    assert bank.name == "Akbank"
    assert bank.name_normalized == "akbank"


def test_bank_bulk_preview_commit_rename_active_delete(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    client.post("/settings/banks", data={"name": "Akbank"})
    preview = client.post(
        "/settings/banks/bulk-preview",
        data={"names": "Garanti BBVA\nakbank\nYeni Banka"},
        follow_redirects=False,
    )
    assert preview.status_code == 200
    assert "Yeni" in preview.text
    assert "Mevcut" in preview.text

    committed = client.post(
        "/settings/banks/bulk",
        data={"names": "Garanti BBVA\nakbank\nYeni Banka"},
        follow_redirects=False,
    )
    assert committed.status_code == 303
    names = {bank.name for bank in fake_uow.commissions.banks.values()}
    assert names == {"Akbank", "Garanti BBVA", "Yeni Banka"}

    bank = next(
        bank for bank in fake_uow.commissions.banks.values()
        if bank.name == "Yeni Banka"
    )
    renamed = client.post(
        f"/settings/banks/{bank.id}/rename",
        data={"name": "yeni banka"},
        follow_redirects=False,
    )
    assert renamed.status_code == 303
    assert bank.name == "Yeni Banka"

    deactivated = client.post(
        f"/settings/banks/{bank.id}/active",
        data={"active": "0"},
        follow_redirects=False,
    )
    assert deactivated.status_code == 303
    assert bank.is_active is False

    without_confirm = client.post(
        f"/settings/banks/{bank.id}/delete",
        data={},
        follow_redirects=False,
    )
    assert without_confirm.status_code == 303
    assert bank.id in fake_uow.commissions.banks

    deleted = client.post(
        f"/settings/banks/{bank.id}/delete",
        data={"confirm": "1"},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert bank.id not in fake_uow.commissions.banks


def test_bank_merge_repoints_and_deletes_source(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    client.post("/settings/banks", data={"name": "Akbank"})
    client.post("/settings/banks", data={"name": "Akbannk"})
    source = next(
        bank for bank in fake_uow.commissions.banks.values()
        if bank.name == "Akbannk"
    )
    target = next(
        bank for bank in fake_uow.commissions.banks.values()
        if bank.name == "Akbank"
    )

    merged = client.post(
        f"/settings/banks/{source.id}/merge",
        data={"target_id": str(target.id)},
        follow_redirects=False,
    )
    assert merged.status_code == 303
    assert source.id not in fake_uow.commissions.banks
    assert target.id in fake_uow.commissions.banks


def test_category_settings_flow(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    created = client.post(
        "/settings/categories",
        data={"name": "ÇAMAŞIR MAKİNESİ"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    category = next(iter(fake_uow.products.categories.values()))
    assert category.name == "Çamaşır Makinesi"

    grouped = client.post(
        f"/settings/categories/{category.id}/group",
        data={"commission_group": "klima"},
        follow_redirects=False,
    )
    assert grouped.status_code == 303
    assert category.commission_group == "klima"

    renamed = client.post(
        f"/settings/categories/{category.id}/rename",
        data={"name": "Çamaşır Makinesi"},
        follow_redirects=False,
    )
    assert renamed.status_code == 303
    assert category.name == "Çamaşır Makinesi"

    deleted = client.post(
        f"/settings/categories/{category.id}/delete",
        data={"confirm": "1"},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert category.id not in fake_uow.products.categories
