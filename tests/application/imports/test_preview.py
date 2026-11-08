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


def test_preview_product_import_parses_arcelik_csv_format() -> None:
    csv_bytes = (
        b"product_name,regular_price,website_discounted_price,quantity\n"
        b"0.58m  with Anderson cable,475 TL,\n"
        b"07325 A,38.099 TL,34.099 TL\n"
        b"10121,39.999 TL,\n"
    )

    result = preview_product_import(csv_bytes)

    assert len(result.rows) == 3
    # 0.58m cable: 475 TL, empty discounted price, empty quantity
    assert result.rows[0].decision == "create"
    assert result.rows[0].product_name == "0.58m  with Anderson cable"
    assert result.rows[0].regular_price == "475"
    assert result.rows[0].website_discounted_price is None
    assert result.rows[0].quantity is None

    # 07325 A: 38.099 TL, 34.099 TL, omitted quantity (3 columns)
    assert result.rows[1].decision == "create"
    assert result.rows[1].product_name == "07325 A"
    assert result.rows[1].regular_price == "38099"
    assert result.rows[1].website_discounted_price == "34099"
    assert result.rows[1].quantity is None
    assert result.rows[1].errors == ()
    assert result.rows[1].warnings == ()

    # 10121: 39.999 TL, empty discounted, empty quantity
    assert result.rows[2].decision == "create"
    assert result.rows[2].product_name == "10121"
    assert result.rows[2].regular_price == "39999"
    assert result.rows[2].website_discounted_price is None
    assert result.rows[2].quantity is None
