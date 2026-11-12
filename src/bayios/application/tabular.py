from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from zoneinfo import ZoneInfo

from bayios.application.errors import ImportFormatError

CellValue = str | int | float | Decimal | date | datetime | None
ColumnKind = Literal["text", "money", "percent", "int", "date", "datetime", "bool"]

_CLEAR_SENTINEL = object()
CLEAR = _CLEAR_SENTINEL

_FORMULA_PREFIXES = ("=", "+", "-", "@")

_TURKISH_ASCII = str.maketrans(
    {
        "ç": "c",
        "Ç": "c",
        "ğ": "g",
        "Ğ": "g",
        "ı": "i",
        "I": "i",
        "İ": "i",
        "i": "i",
        "ö": "o",
        "Ö": "o",
        "ş": "s",
        "Ş": "s",
        "ü": "u",
        "Ü": "u",
    }
)

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%y",
    "%d-%m-%y",
    "%Y/%m/%d",
)


@dataclass(frozen=True)
class RawSheet:
    name: str
    rows: tuple[tuple[CellValue, ...], ...]


@dataclass(frozen=True)
class HeaderLayout:
    row_index: int
    indexes: Mapping[str, int]
    headers: tuple[str, ...]
    unknown_headers: tuple[str, ...]


@dataclass(frozen=True)
class ColumnSpec:
    header: str
    key: str
    kind: ColumnKind = "text"
    width: int | None = None


@dataclass(frozen=True)
class SheetSpec:
    title: str
    columns: tuple[ColumnSpec, ...]
    rows: Sequence[Mapping[str, object]]
    instructions: Sequence[tuple[str, str, str]] = ()


def normalize_header(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = text.translate(_TURKISH_ASCII)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_sheet_name(value: object) -> str:
    return normalize_header(value)


def read_raw_sheets(source: bytes) -> tuple[RawSheet, ...]:
    if not source:
        raise ImportFormatError("Yüklenen dosya boş.")
    if source.startswith(b"PK"):
        from openpyxl import load_workbook

        try:
            workbook = load_workbook(io.BytesIO(source), read_only=True, data_only=True)
        except Exception as exc:
            raise ImportFormatError("Excel dosyası okunamadı.") from exc
        try:
            sheets: list[RawSheet] = []
            for worksheet in workbook.worksheets:
                rows = tuple(
                    tuple(row)
                    for row in worksheet.iter_rows(values_only=True)
                    if any(_present(value) for value in row)
                )
                if rows:
                    sheets.append(RawSheet(name=worksheet.title, rows=rows))
            if not sheets:
                raise ImportFormatError("Excel dosyasında okunacak satır bulunamadı.")
            return tuple(sheets)
        finally:
            workbook.close()

    text = _decode_source(source)
    reader = csv.reader(io.StringIO(text), delimiter=_detect_delimiter(text))
    rows = tuple(tuple(cell for cell in row) for row in reader)
    if not rows:
        raise ImportFormatError("CSV dosyasında okunacak satır bulunamadı.")
    return (RawSheet(name="CSV", rows=rows),)


def sheet_named(
    sheets: Sequence[RawSheet], names: Sequence[str]
) -> RawSheet | None:
    wanted = {normalize_sheet_name(name) for name in names}
    for sheet in sheets:
        if normalize_sheet_name(sheet.name) in wanted:
            return sheet
    return None


def first_sheet(sheets: Sequence[RawSheet]) -> RawSheet:
    if not sheets:
        raise ImportFormatError("Dosyada sayfa bulunamadı.")
    return sheets[0]


def locate_header(
    rows: Sequence[Sequence[CellValue]],
    aliases: Mapping[str, Sequence[str]],
    *,
    required: Sequence[str] = (),
    max_scan: int = 10,
    sheet_label: str = "",
) -> HeaderLayout:
    normalized_aliases: dict[str, set[str]] = {
        key: {normalize_header(alias) for alias in values}
        for key, values in aliases.items()
    }
    all_alias_names = {
        alias for values in normalized_aliases.values() for alias in values
    }
    best_missing: tuple[str, ...] | None = None
    best_row: tuple[str, ...] = ()

    for row_index, row in enumerate(rows[:max_scan]):
        normalized = [normalize_header(cell) for cell in row]
        if not any(normalized):
            continue
        indexes: dict[str, int] = {}
        duplicate: str | None = None
        for canonical, alias_names in normalized_aliases.items():
            for column_index, header in enumerate(normalized):
                if header and header in alias_names:
                    if canonical in indexes:
                        duplicate = str(row[column_index] or "")
                        break
                    indexes[canonical] = column_index
            if duplicate:
                break
        if duplicate:
            raise ImportFormatError(
                f"{_sheet_prefix(sheet_label)}'{duplicate}' kolonu birden fazla kez var."
            )
        missing = tuple(key for key in required if key not in indexes)
        if best_missing is None or len(missing) < len(best_missing):
            best_missing = missing
            best_row = tuple(str(cell or "") for cell in row)
        if not missing:
            unknown = tuple(
                str(cell)
                for cell in row
                if _present(cell) and normalize_header(cell) not in all_alias_names
            )
            return HeaderLayout(
                row_index=row_index,
                indexes=indexes,
                headers=tuple(str(cell or "") for cell in row),
                unknown_headers=unknown,
            )

    if best_missing is None:
        raise ImportFormatError(
            f"{_sheet_prefix(sheet_label)}Başlık satırı bulunamadı."
        )
    missing_text = ", ".join(best_missing)
    raise ImportFormatError(
        f"{_sheet_prefix(sheet_label)}Zorunlu kolonlar eksik: {missing_text}. "
        f"Bulunan başlıklar: {', '.join(best_row)}"
    )


def row_value(
    row: Sequence[CellValue], layout: HeaderLayout, key: str
) -> CellValue:
    index = layout.indexes.get(key)
    if index is None or index >= len(row):
        return None
    return row[index]


def cell_text(value: CellValue) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "Evet" if value else "Hayır"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value).strip()


def parse_decimal(value: CellValue, label: str) -> Decimal | None:
    if not _present(value):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise TypeError(f"{label} sayısal olmalıdır.")
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    cleaned = str(value).strip()
    cleaned = re.sub(r"(?i)\s*(?:TL|TRY|₺|%)$", "", cleaned).strip()
    cleaned = cleaned.replace(" ", "")
    if not cleaned:
        return None
    cleaned = cleaned.removeprefix("'")
    if "." in cleaned and "," in cleaned:
        last_dot = cleaned.rfind(".")
        last_comma = cleaned.rfind(",")
        if last_comma > last_dot:
            candidate = cleaned.replace(".", "").replace(",", ".")
        else:
            candidate = cleaned.replace(",", "")
    elif "." in cleaned:
        parts = cleaned.split(".")
        if len(parts) > 2 or (
            len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) >= 1
        ):
            candidate = cleaned.replace(".", "")
        else:
            candidate = cleaned
    elif "," in cleaned:
        candidate = cleaned.replace(",", ".")
    else:
        candidate = cleaned

    try:
        return Decimal(candidate)
    except InvalidOperation as exc:
        raise ValueError(f"{label} sayısal olmalıdır.") from exc


def parse_optional_decimal(
    value: CellValue, label: str
) -> Decimal | None | object:
    if not _present(value):
        return None
    if _is_clear(value):
        return CLEAR
    return parse_decimal(value, label)


def parse_int(
    value: CellValue,
    label: str,
    *,
    minimum: int | None = 0,
) -> int | None:
    number = parse_decimal(value, label)
    if number is None:
        return None
    if number != number.to_integral_value():
        raise ValueError(f"{label} tam sayı olmalıdır.")
    result = int(number)
    if minimum is not None and result < minimum:
        raise ValueError(f"{label} {minimum} veya daha büyük olmalıdır.")
    return result


def parse_date(value: CellValue, label: str) -> date | None:
    if not _present(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            from openpyxl.utils.datetime import from_excel

            converted = from_excel(float(value))
            if isinstance(converted, datetime):
                return converted.date()
            if isinstance(converted, date):
                return converted
        except Exception as exc:
            raise ValueError(f"{label} geçerli bir tarih değil.") from exc
    text = str(value).strip()
    if not text:
        return None
    for date_format in _DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    raise ValueError(f"{label} GG.AA.YYYY biçiminde olmalıdır.")


def parse_bool(value: CellValue, label: str) -> bool | None:
    if not _present(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        if Decimal(str(value)) == Decimal(1):
            return True
        if Decimal(str(value)) == Decimal(0):
            return False
    normalized = normalize_header(value)
    if normalized in {"1", "evet", "var", "true", "yes", "e", "x"}:
        return True
    if normalized in {"0", "hayir", "yok", "false", "no", "h"}:
        return False
    raise ValueError(f"{label} Evet/Hayır olmalıdır.")


def parse_enum(
    value: CellValue,
    label: str,
    choices: Mapping[str, object],
    *,
    default: object | None = None,
) -> object | None:
    if not _present(value):
        return default
    normalized = normalize_header(value)
    for code, label_text in choices.items():
        if normalized == normalize_header(code) or normalized == normalize_header(label_text):
            return code
    raise ValueError(f"{label} geçersiz: {cell_text(value)}")


def write_xlsx(
    sheets: Sequence[SheetSpec], *, include_instructions: bool = True
) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    workbook.remove(workbook.active)
    header_fill = PatternFill("solid", fgColor="D9E2F3")
    header_font = Font(bold=True)

    for sheet_spec in sheets:
        worksheet = workbook.create_sheet(title=sheet_spec.title[:31])
        for column_index, column in enumerate(sheet_spec.columns, start=1):
            cell = worksheet.cell(row=1, column=column_index, value=column.header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(vertical="center")
        worksheet.freeze_panes = "A2"
        widths: dict[int, int] = {
            index: len(column.header) + 2
            for index, column in enumerate(sheet_spec.columns, start=1)
        }
        for row_index, row in enumerate(sheet_spec.rows, start=2):
            for column_index, column in enumerate(sheet_spec.columns, start=1):
                value = row.get(column.key)
                cell = worksheet.cell(row=row_index, column=column_index)
                _write_cell(cell, value, column.kind)
                widths[column_index] = max(
                    widths[column_index],
                    min(60, len(cell_text(value)) + 2),
                )
        for column_index, column in enumerate(sheet_spec.columns, start=1):
            width = column.width or widths[column_index]
            worksheet.column_dimensions[get_column_letter(column_index)].width = min(
                60, max(10, width)
            )

    if include_instructions and any(
        sheet_spec.instructions for sheet_spec in sheets
    ):
        usage = workbook.create_sheet(title="Kullanım")
        usage.append(["Kolon", "Zorunluluk", "Açıklama"])
        for sheet_spec in sheets:
            for header, requirement, description in sheet_spec.instructions:
                usage.append([header, requirement, description])
        usage.freeze_panes = "A2"
        for column_index, width in ((1, 28), (2, 14), (3, 80)):
            usage.column_dimensions[get_column_letter(column_index)].width = width

    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def write_csv(
    headers: Sequence[str], rows: Sequence[Sequence[object]]
) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_csv_cell(value) for value in row])
    return output.getvalue().encode("utf-8-sig")


def _write_cell(cell: Any, value: object, kind: ColumnKind) -> None:
    if value is None or value == "":
        cell.value = None
        return
    if kind == "money":
        cell.value = float(Decimal(str(value)))
        cell.number_format = "#,##0.00"
        return
    if kind == "percent":
        cell.value = float(Decimal(str(value)))
        cell.number_format = "0.00"
        return
    if kind == "int":
        cell.value = int(value)
        cell.number_format = "0"
        return
    if kind == "date":
        cell.value = _excel_value(value)
        cell.number_format = "DD.MM.YYYY"
        return
    if kind == "datetime":
        cell.value = _excel_value(value)
        cell.number_format = "DD.MM.YYYY HH:MM"
        return
    if kind == "bool":
        cell.value = "Evet" if bool(value) else "Hayır"
        cell.data_type = "s"
        return
    text = cell_text(value)
    cell.value = text
    cell.data_type = "s"
    cell.number_format = "@"


def _excel_value(value: object) -> object:
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(ZoneInfo("Europe/Istanbul")).replace(tzinfo=None)
    return value


def _csv_cell(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(ZoneInfo("Europe/Istanbul"))
        return value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, bool):
        return "Evet" if value else "Hayır"
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _decode_source(source: bytes) -> str:
    try:
        return source.decode("utf-8-sig")
    except UnicodeDecodeError:
        return source.decode("cp1254").lstrip("\ufeffï»¿")


def _detect_delimiter(text: str) -> str:
    sample = text.splitlines()[0] if text.splitlines() else ""
    return ";" if sample.count(";") > sample.count(",") else ","


def _present(value: CellValue) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _is_clear(value: CellValue) -> bool:
    if not isinstance(value, str):
        return False
    raw = value.strip().casefold()
    return raw in {"-", "temizle", "clear", "yok", "sil"} or normalize_header(
        value
    ) in {"temizle", "clear", "yok", "sil"}


def _sheet_prefix(sheet_label: str) -> str:
    return f"{sheet_label}: " if sheet_label else ""
