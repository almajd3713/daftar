"""What a person does to an exported file, for the round-trip tests: edit it in a spreadsheet, or read it."""

import json
import sys
from typing import Any

from openpyxl import load_workbook


def read(path: str) -> dict[str, Any]:
    formulas = load_workbook(path)
    values = load_workbook(path, data_only=True)
    return {
        name: {
            cell.coordinate: {"value": values[name][cell.coordinate].value, "formula": cell.value if cell.data_type == "f" else None}
            for row in formulas[name].iter_rows()
            for cell in row
            if cell.value is not None
        }
        | {"_rtl": {"value": formulas[name].sheet_view.rightToLeft, "formula": None}}
        for name in formulas.sheetnames
    }


def edit(path: str, edits: dict[str, Any]) -> None:
    book = load_workbook(path)
    for name, cells in edits.get("set", {}).items():
        for reference, value in cells.items():
            book[name][reference] = value
    for name, row in edits.get("deleteRow", {}).items():
        book[name].delete_rows(row)
    book.save(path)


if __name__ == "__main__":
    if sys.argv[1] == "read":
        print(json.dumps(read(sys.argv[2]), default=str))
    else:
        edit(sys.argv[2], json.loads(sys.argv[3]))
