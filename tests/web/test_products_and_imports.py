from __future__ import annotations

import base64
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from bayios.adapters.db.models.products import Product
from bayios.bootstrap import ApplicationSettings
from bayios.main import create_app
from bayios.web.deps import get_unit_of_work
from tests.fakes import FakeUnitOfWork


@pytest.fixture
def fake_uow() -> FakeUnitOfWork:
    uow = FakeUnitOfWork()
    p1 = Product(
        id=uuid.uuid4(),
        name="07325 A",
        name_normalized="07325 a",
        regular_price=Decimal("38099.00"),
        website_discounted_price=Decimal("34099.00"),
        physical_stock=5,
    )
    uow.products.add(p1)
    return uow


@pytest.fixture
def client(fake_uow: FakeUnitOfWork) -> TestClient:
    settings = ApplicationSettings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/bayios"
    )
    app = create_app(settings)
    app.dependency_overrides[get_unit_of_work] = lambda: fake_uow
    return TestClient(app)


def test_get_products_list_renders_html(client: TestClient) -> None:
    response = client.get("/products")
    assert response.status_code == 200
    assert "Ürünler" in response.text
    assert "07325 A" in response.text
    assert "38.099,00 TL" in response.text


def test_get_products_htmx_search_renders_partial_table(client: TestClient) -> None:
    response = client.get("/products?q=07325", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "07325 A" in response.text
    # Should not include full html wrapper shell
    assert "<!doctype html>" not in response.text


def test_get_product_detail(client: TestClient, fake_uow: FakeUnitOfWork) -> None:
    p = list(fake_uow.products.get_all())[0]
    response = client.get(f"/products/{p.id}")
    assert response.status_code == 200
    assert p.name in response.text
    assert "Fiyat Geçmişi" in response.text
    assert "Stok Hareket Geçmişi" in response.text


def test_get_imports_upload_page(client: TestClient) -> None:
    response = client.get("/imports/products")
    assert response.status_code == 200
    assert "Ürün Kataloğu İçe Aktar" in response.text
    assert "Dosya Seçin" in response.text


def test_post_imports_preview_and_commit(client: TestClient, fake_uow: FakeUnitOfWork) -> None:
    csv_content = (
        b"product_name,regular_price,website_discounted_price,quantity\n"
        b"09325 A,42.199 TL,38.199 TL,3\n"
    )
    # 1. Preview
    preview_res = client.post(
        "/imports/products/preview",
        files={"file": ("test.csv", csv_content, "text/csv")},
    )
    assert preview_res.status_code == 200
    assert "İçe Aktarma Önizlemesi" in preview_res.text
    assert "09325 A" in preview_res.text
    assert "42.199,00 TL" in preview_res.text

    # 2. Commit
    source_b64 = base64.b64encode(csv_content).decode("ascii")
    commit_res = client.post(
        "/imports/products/commit",
        data={
            "file_name": "test.csv",
            "file_type": "csv",
            "source_b64": source_b64,
            "decisions_json": '{"2": "create"}',
        },
        follow_redirects=True,
    )
    assert commit_res.status_code == 200
    assert "09325 A" in commit_res.text

    # Verify in repo
    imported = fake_uow.products.get_by_normalized_name("09325 a")
    assert imported is not None
    assert imported.regular_price == Decimal("42199")
    assert imported.physical_stock == 3


def test_preview_real_arcelik_csv_page(client: TestClient) -> None:
    from pathlib import Path

    csv_path = Path("arcelik-06-09-2026.csv")
    if not csv_path.exists():
        return
    content = csv_path.read_bytes()
    preview_res = client.post(
        "/imports/products/preview",
        files={"file": ("arcelik-06-09-2026.csv", content, "text/csv")},
    )
    assert preview_res.status_code == 200
    assert "İçe Aktarma Önizlemesi" in preview_res.text
    # Ensure there is no broken Alpine x-data syntax
    assert 'x-data="decisionForm(' not in preview_res.text
    assert 'decisionsJsonInput' in preview_res.text
    assert 'decision-select' in preview_res.text
    assert 'Toplu Karar:' in preview_res.text


def test_export_endpoints(client: TestClient) -> None:
    csv_res = client.get("/products/export/csv")
    assert csv_res.status_code == 200
    assert csv_res.headers["content-type"].startswith("text/csv")
    assert "07325 A" in csv_res.text

    xlsx_res = client.get("/products/export/xlsx")
    assert xlsx_res.status_code == 200
    assert xlsx_res.content.startswith(b"PK")
