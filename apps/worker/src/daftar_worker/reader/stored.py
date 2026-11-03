"""Read formula results directly from an original .xls or .ods.

LibreOffice's "never recalculate" setting covers .xlsx only: tests show it recalculates .xls and
.ods on load, whatever the setting. So it converts the structure of these files, and the results
come from here. Without this, the parity metric would compare against LibreOffice, not Excel.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any
import zipfile

from defusedxml import ElementTree
from openpyxl.utils import get_column_letter
from openpyxl.utils.datetime import MAC_EPOCH, WINDOWS_EPOCH, from_excel
import xlrd

from daftar_worker.reader.raw import local
from daftar_worker.reader.xlsx import encode_value


OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
ODS_ERROR = re.compile(r"^(#[A-Z0-9/!?]+|Err:\d+)$")
# A run of repeated empty cells can legitimately span a whole sheet; only formulas are stored.
MAX_REPEATS = 1_048_576


@dataclass(frozen=True)
class Stored:
    """A stored result: `kind` is number, text, boolean, date or error."""

    kind: str
    value: Any


ResultLookup = Callable[[str, str], Stored | None]


def _excel_date(serial: float, mode: int) -> tuple[Any, str]:
    if mode == 0 and serial == 60:
        return "1900-02-29", "d"  # Excel's leap-year bug: the day exists only in Excel.
    return encode_value(from_excel(serial, MAC_EPOCH if mode else WINDOWS_EPOCH), None)


def encode_stored(stored: Stored, is_date: bool, date_mode: int = 0) -> tuple[Any, str]:
    """Return C-1 (v, t) for a stored result. `is_date` says the cell has a date format."""
    if stored.kind == "number":
        if is_date:
            try:
                return _excel_date(float(stored.value), date_mode)
            except (OverflowError, ValueError):
                pass  # Outside Excel's date range: keep the number the file holds.
        value = stored.value
        return (int(value) if float(value).is_integer() else float(value)), "n"
    if stored.kind == "boolean":
        return bool(stored.value), "b"
    if stored.kind == "error":
        return str(stored.value), "e"
    if stored.kind == "date":
        return str(stored.value), "d"
    return (str(stored.value) or None), "s"


def xls_lookup(path: Path) -> tuple[ResultLookup, int]:
    """Return a lookup of stored results in an .xls file, and the file's date mode."""
    book = xlrd.open_workbook(str(path))
    sheets = {name: book.sheet_by_name(name) for name in book.sheet_names()}

    def lookup(sheet_name: str, ref: str) -> Stored | None:
        sheet = sheets.get(sheet_name)
        match = re.fullmatch(r"([A-Z]+)([0-9]+)", ref)
        if sheet is None or match is None:
            return None
        column = 0
        for letter in match.group(1):
            column = column * 26 + ord(letter) - 64
        row = int(match.group(2)) - 1
        column -= 1
        if row >= sheet.nrows or column >= sheet.ncols:
            return None
        cell = sheet.cell(row, column)
        if cell.ctype in (xlrd.XL_CELL_NUMBER, xlrd.XL_CELL_DATE):
            return Stored("number", cell.value)
        if cell.ctype == xlrd.XL_CELL_BOOLEAN:
            return Stored("boolean", cell.value)
        if cell.ctype == xlrd.XL_CELL_ERROR:
            return Stored("error", xlrd.error_text_from_code.get(cell.value, "#N/A"))
        if cell.ctype == xlrd.XL_CELL_TEXT:
            return Stored("text", cell.value)
        return Stored("text", "") if cell.ctype == xlrd.XL_CELL_EMPTY else None

    return lookup, book.datemode


def _ods_stored(cell: Any) -> Stored:
    kind = cell.get(f"{OFFICE}value-type")
    if kind in ("float", "percentage", "currency"):
        return Stored("number", float(cell.get(f"{OFFICE}value", "0")))
    if kind == "boolean":
        return Stored("boolean", cell.get(f"{OFFICE}boolean-value") == "true")
    if kind == "date":
        return Stored("date", cell.get(f"{OFFICE}date-value", ""))
    if kind == "time":
        return Stored("date", cell.get(f"{OFFICE}time-value", ""))
    text = "\n".join(
        "".join(node.itertext()) for node in cell if local(node.tag) == "p"
    )
    value = cell.get(f"{OFFICE}string-value", text)
    return Stored("error" if ODS_ERROR.match(value or "") else "text", value)


def ods_lookup(path: Path) -> ResultLookup:
    """Return a lookup of the stored results of the formula cells in an .ods file."""
    results: dict[tuple[str, str], Stored] = {}
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("content.xml"))
    for table in root.iter(f"{TABLE}table"):
        name = table.get(f"{TABLE}name", "")
        row_index = 0
        for row in table.iter(f"{TABLE}table-row"):
            repeat_rows = min(int(row.get(f"{TABLE}number-rows-repeated", "1")), MAX_REPEATS)
            column = 0
            for cell in row:
                if local(cell.tag) not in ("table-cell", "covered-table-cell"):
                    continue
                repeat = min(int(cell.get(f"{TABLE}number-columns-repeated", "1")), MAX_REPEATS)
                if cell.get(f"{TABLE}formula") is not None:
                    stored = _ods_stored(cell)
                    for extra_row in range(repeat_rows):
                        for extra_column in range(repeat):
                            ref = f"{get_column_letter(column + extra_column + 1)}"
                            results[(name, f"{ref}{row_index + extra_row + 1}")] = stored
                column += repeat
            row_index += repeat_rows

    def lookup(sheet_name: str, ref: str) -> Stored | None:
        return results.get((sheet_name, ref))

    return lookup


def apply_stored_results(
    sheets: list[dict[str, Any]], lookup: ResultLookup, date_mode: int = 0
) -> bool:
    """Overwrite every formula cell's value with the original's. False if any had none to use."""
    complete = True
    for sheet in sheets:
        for cell in sheet["cells"]:
            if "f" not in cell:
                continue
            stored = lookup(sheet["name"], cell["ref"])
            if stored is None:
                complete = False
                continue
            cell["v"], cell["t"] = encode_stored(stored, cell["t"] == "d", date_mode)
    return complete

