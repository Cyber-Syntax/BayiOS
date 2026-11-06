from bayios.application.imports import preview_product_import


def test_preview_product_import_classifies_new_and_invalid_rows() -> None:
    result = preview_product_import(
        b"product_name,regular_price,quantity\nNew Product,1200,3\n,not-a-price,abc\n"
    )

    assert [row.decision for row in result.rows] == ["create", "error"]
    assert result.rows[0].product_name == "New Product"
    assert result.rows[0].regular_price == "1200"
    assert result.rows[1].errors == (
        "Name is required",
        "Regular Price must be a number",
        "Quantity must be a non-negative integer",
    )


def test_preview_product_import_accepts_cp1254_semicolon_and_bom() -> None:
    result = preview_product_import(
        b"\xef\xbb\xbf" + "Name;Regular Price;Quantity\nBuzdolabı;12,50;0\n".encode("cp1254")
    )

    assert result.rows[0].decision == "create"
    assert result.rows[0].product_name == "Buzdolabı"
    assert result.rows[0].regular_price == "12.50"
    assert result.rows[0].quantity == "0"


def test_preview_product_import_reads_xlsx_rows() -> None:
    from io import BytesIO

    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["product_name", "regular_price", "quantity"])
    sheet.append(["Bulaşık Makinesi", 2500, 1])
    stream = BytesIO()
    workbook.save(stream)

    result = preview_product_import(stream.getvalue())

    assert result.rows[0].decision == "create"
    assert result.rows[0].regular_price == "2500"
    assert result.rows[0].quantity == "1"
