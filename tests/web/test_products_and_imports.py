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


def test_get_products_list_shows_at_most_25_per_page(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    for index in range(30):
        name = f"Ürün {index:03d}"
        fake_uow.products.add(
            Product(
                id=uuid.uuid4(),
                name=name,
                name_normalized=name.lower(),
                regular_price=Decimal("100.00"),
                physical_stock=1,
            )
        )

    first_page = client.get("/products")
    assert first_page.status_code == 200
    assert first_page.text.count('class="product-checkbox"') == 25
    assert "Toplam 31 ürün" in first_page.text
    assert "page=2" in first_page.text

    second_page = client.get("/products?page=2")
    assert second_page.status_code == 200
    assert second_page.text.count('class="product-checkbox"') == 6


def test_get_products_htmx_search_renders_partial_table(client: TestClient) -> None:
    response = client.get("/products?q=07325", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "07325 A" in response.text
    # Should not include full html wrapper shell
    assert "<!doctype html>" not in response.text


def test_get_products_category_filter_renders_partial(client: TestClient) -> None:
    from bayios.adapters.db.models.products import ProductCategory

    uow = client.app.dependency_overrides[get_unit_of_work]()
    category = ProductCategory(id=uuid.uuid4(), name="Buzdolabı")
    uow.products.add_category(category)
    product = next(iter(uow.products.get_all()))
    product.category_id = category.id

    response = client.get(
        f"/products?category_id={category.id}", headers={"HX-Request": "true"}
    )
    assert response.status_code == 200
    assert "07325 A" in response.text
    assert "<!doctype html>" not in response.text


def test_get_product_detail(client: TestClient, fake_uow: FakeUnitOfWork) -> None:
    p = next(iter(fake_uow.products.get_all()))
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
    assert imported.regular_price == Decimal(42199)
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
    assert "Kategori" in csv_res.text

    xlsx_res = client.get("/products/export/xlsx")
    assert xlsx_res.status_code == 200
    assert xlsx_res.content.startswith(b"PK")


def test_post_create_manual_product_route(client: TestClient, fake_uow: FakeUnitOfWork) -> None:
    res = client.post(
        "/products",
        data={
            "name": "Yeni Manuel Ürün",
            "regular_price": "25.000 TL",
            "website_discounted_price": "22.500 TL",
            "cost_price": "18.000 TL",
            "physical_stock": "4",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert fake_uow.committed
    assert "Yeni ürün kataloğa eklendi." in client.get(res.headers["location"]).text
    prod = fake_uow.products.get_by_normalized_name("yeni manuel ürün")
    assert prod is not None
    assert prod.regular_price == Decimal(25000)
    assert prod.physical_stock == 4


def test_post_create_duplicate_product_shows_turkish_error_not_json(
    client: TestClient,
) -> None:
    response = client.post(
        "/products", data={"name": "07325 a"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert "application/json" not in response.headers.get("content-type", "")

    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert "İşlem yapılamadı:" in page.text
    assert "adında bir ürün zaten mevcut." in page.text


def test_update_product_duplicate_name_shows_error_on_detail(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))
    fake_uow.products.add(
        Product(
            id=uuid.uuid4(),
            name="Başka Ürün",
            name_normalized="başka ürün",
            regular_price=Decimal("100.00"),
            physical_stock=1,
        )
    )

    response = client.post(
        f"/products/{product.id}/edit",
        data={"name": "Başka Ürün"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert "İşlem yapılamadı:" in page.text
    assert "adında bir ürün zaten mevcut." in page.text


def test_bulk_archive_and_unarchive_route(client: TestClient, fake_uow: FakeUnitOfWork) -> None:
    prod = next(iter(fake_uow.products.get_all()))
    res = client.post(
        "/products/bulk-archive",
        data={"product_ids": [str(prod.id)], "action": "archive"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert fake_uow.committed
    assert "Seçilen ürün(ler) arşivlendi." in client.get(res.headers["location"]).text
    assert prod.is_archived is True

    # Unarchive
    res2 = client.post(
        "/products/bulk-archive",
        data={"product_ids": [str(prod.id)], "action": "unarchive"},
        follow_redirects=False,
    )
    assert res2.status_code == 303
    assert fake_uow.committed
    assert "Seçilen ürün(ler) arşivden çıkarıldı." in client.get(res2.headers["location"]).text
    assert prod.is_archived is False


def test_bulk_category_assigns_multiple_products(client: TestClient, fake_uow: FakeUnitOfWork) -> None:
    from bayios.adapters.db.models.products import ProductCategory

    category = ProductCategory(id=uuid.uuid4(), name="Buzdolabı")
    fake_uow.products.add_category(category)

    p1 = Product(
        id=uuid.uuid4(),
        name="07325 A",
        name_normalized="07325 a",
        regular_price=Decimal("38099.00"),
        physical_stock=5,
    )
    p2 = Product(
        id=uuid.uuid4(),
        name="09325 A",
        name_normalized="09325 a",
        regular_price=Decimal("42199.00"),
        physical_stock=3,
    )
    fake_uow.products.add(p1)
    fake_uow.products.add(p2)

    res = client.post(
        "/products/bulk-category",
        data={"product_ids": [str(p1.id), str(p2.id)], "category_id": str(category.id)},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert fake_uow.committed
    assert "2 ürünün kategorisi güncellendi." in client.get(res.headers["location"]).text
    assert p1.category_id == category.id
    assert p2.category_id == category.id


def test_bulk_delete_requires_confirmation_route(client: TestClient, fake_uow: FakeUnitOfWork) -> None:
    prod = next(iter(fake_uow.products.get_all()))

    # Without confirmation fails
    fail_res = client.post(
        "/products/bulk-delete",
        data={"product_ids": [str(prod.id)]},
    )
    assert fail_res.status_code == 400
    assert "Silme işlemi iki aşamalı doğrulama gerektirir" in fail_res.text

    # With confirmation succeeds
    ok_res = client.post(
        "/products/bulk-delete",
        data={"product_ids": [str(prod.id)], "confirmed": "yes_delete_permanently"},
        follow_redirects=False,
    )
    assert ok_res.status_code == 303
    assert fake_uow.committed
    assert "Seçilen ürün(ler) veritabanından kalıcı olarak silindi." in client.get(
        ok_res.headers["location"]
    ).text
    assert fake_uow.products.get_by_id(prod.id) is None


def test_update_product_stock_route(client: TestClient, fake_uow: FakeUnitOfWork) -> None:
    prod = next(iter(fake_uow.products.get_all()))
    res = client.post(
        f"/products/{prod.id}/stock",
        data={"physical_stock": "12", "note": "Sayım fazlası bulundu"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert fake_uow.committed
    assert "Ürün stoku başarıyla güncellendi." in client.get(res.headers["location"]).text
    assert prod.physical_stock == 12


def test_update_product_stock_route_can_redirect_back_to_list(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    prod = next(iter(fake_uow.products.get_all()))
    res = client.post(
        f"/products/{prod.id}/stock",
        data={
            "physical_stock": "7",
            "note": "Liste hızlı güncelleme",
            "redirect_to": "/products?q=07325&status=active",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"].startswith("/products?")
    assert "msg=stock_updated" in res.headers["location"]
    assert fake_uow.committed
    assert prod.physical_stock == 7


def test_update_product_route_records_history(client: TestClient, fake_uow: FakeUnitOfWork) -> None:
    prod = next(iter(fake_uow.products.get_all()))
    res = client.post(
        f"/products/{prod.id}/edit",
        data={
            "name": "07325 A Guncel",
            "regular_price": "40.000 TL",
            "website_discounted_price": "",
            "cost_price": "30.000 TL",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert fake_uow.committed
    assert "Ürün bilgileri güncellendi." in client.get(res.headers["location"]).text
    assert prod.name == "07325 A Guncel"
    assert prod.regular_price == Decimal(40000)
    assert prod.website_discounted_price is None
    assert prod.cost_price == Decimal(30000)
    assert len(fake_uow.products.get_price_history(prod.id)) == 3


def test_commit_with_all_skipped_shows_accurate_message(client: TestClient) -> None:
    csv_content = (
        b"product_name,regular_price,quantity\n"
        b"Deneme Urun,1000,1\n"
    )
    source_b64 = base64.b64encode(csv_content).decode("ascii")
    # All rows skipped
    res = client.post(
        "/imports/products/commit",
        data={
            "file_name": "deneme.csv",
            "file_type": "csv",
            "source_b64": source_b64,
            "decisions_json": '{"2": "skip"}',
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    # Shows 0 new, 0 updated, 1 skipped!
    assert "0 yeni ürün eklendi, 0 ürün güncellendi, 1 satır atlandı" in res.text


def test_product_edit_creates_category_with_commission_group(
    client: TestClient, fake_uow: FakeUnitOfWork
) -> None:
    product = next(iter(fake_uow.products.get_all()))

    response = client.post(
        f"/products/{product.id}/edit",
        data={
            "name": product.name,
            "regular_price": "38099",
            "website_discounted_price": "34099",
            "cost_price": "",
            "category_id": "",
            "new_category_name": "Klima",
            "new_category_group": "klima",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    category = fake_uow.products.get_category_by_name("Klima")
    assert category is not None
    assert category.commission_group == "klima"
    assert product.category_id == category.id

    page = client.get(f"/products/{product.id}")
    assert page.status_code == 200
    assert "Klima" in page.text
