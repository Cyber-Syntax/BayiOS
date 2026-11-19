from __future__ import annotations

from bayios.application.settings import (
    create_banks_bulk,
    create_categories_bulk,
    set_bank_active,
)
from bayios.application.settings.io import (
    export_banks_xlsx,
    export_categories_xlsx,
    import_banks_xlsx,
    import_categories_xlsx,
)
from tests.fakes import FakeUnitOfWork


def test_bank_excel_roundtrip() -> None:
    source = FakeUnitOfWork()
    create_banks_bulk(source, "AKBANK\nGaranti BBVA")
    bank = next(
        bank for bank in source.commissions.banks.values()
        if bank.name == "Garanti BBVA"
    )
    set_bank_active(source, bank.id, False)

    data = export_banks_xlsx(source)
    target = FakeUnitOfWork()
    result = import_banks_xlsx(target, data)

    assert result.created == 2
    names = {bank.name: bank.is_active for bank in target.commissions.banks.values()}
    assert names == {"Akbank": True, "Garanti BBVA": False}


def test_category_excel_roundtrip() -> None:
    source = FakeUnitOfWork()
    create_categories_bulk(source, "Buzdolabı\nÇAMAŞIR MAKİNESİ")

    data = export_categories_xlsx(source)
    target = FakeUnitOfWork()
    result = import_categories_xlsx(target, data)

    assert result.created == 2
    names = {category.name for category in target.products.categories.values()}
    assert names == {"Buzdolabı", "Çamaşır Makinesi"}
