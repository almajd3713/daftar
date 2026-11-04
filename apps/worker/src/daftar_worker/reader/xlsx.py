"""Read an .xlsx or .xlsm file in two passes: formulas, then Excel's stored results."""

from datetime import date, datetime, time, timedelta
import re
from typing import Any
import warnings

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter, range_boundaries
from openpyxl.utils.datetime import WINDOWS_EPOCH
from openpyxl.worksheet.formula import ArrayFormula, DataTableFormula

from daftar_worker.reader.colours import resolve
from daftar_worker.reader.raw import RawPackage, RawSheet


FUTURE_PREFIX = re.compile(r"_xlfn\._xlws\.|_xlfn\.|_xlws\.|_xlpm\.")
# Don't expand an array formula's range past this; the first cell still carries the formula.
MAX_ARRAY_EXPANSION = 100_000


def clean_formula(text: str) -> str:
    """Drop the file-format prefixes on newer functions, leaving text in string literals alone."""
    parts = text.split('"')
    parts[::2] = [FUTURE_PREFIX.sub("", part) for part in parts[::2]]
    return '"'.join(parts)


def encode_value(value: Any, data_type: str | None) -> tuple[Any, str]:
    """Return C-1 (v, t). A value of None with t "s" means nothing is stored."""
    if isinstance(value, bool):
        return value, "b"
    if isinstance(value, (int, float)):
        return value, "n"
    if isinstance(value, datetime):
        return value.isoformat(), "d"
    if isinstance(value, date):
        return value.isoformat(), "d"
    if isinstance(value, time):
        return value.isoformat(), "d"
    if isinstance(value, timedelta):  # [h]:mm durations: the stored value is a number of days.
        return value.total_seconds() / 86400, "n"
    if value is None:
        return None, "s"
    return str(value), "e" if data_type == "e" else "s"


def _formula_text(value: Any) -> str | None:
    if isinstance(value, ArrayFormula):
        text = value.text or ""
        return "{" + clean_formula(text if text.startswith("=") else f"={text}") + "}"
    if isinstance(value, DataTableFormula):
        return f"{{=TABLE({value.r1 or ''},{value.r2 or ''})}}"
    return None


class _StyleCache:
    def __init__(self, workbook: Any, palette: list[str]) -> None:
        self.palette = palette
        self.index = getattr(workbook, "_colors", None)
        self.cache: dict[int, tuple[dict[str, Any], str | None]] = {}

    def colour(self, color: Any) -> str | None:
        return resolve(color, self.palette, self.index)

    def fill(self, fill: Any) -> str | None:
        if fill is None:
            return None
        stops = getattr(fill, "stop", None)  # A gradient has no pattern, so use its first colour.
        if stops:
            return self.colour(stops[0].color)
        if getattr(fill, "fill_type", None) in (None, "none"):
            return None
        return self.colour(fill.fgColor)

    def of(self, cell: Any) -> tuple[dict[str, Any], str | None]:
        if not cell.has_style:
            return {}, None
        cached = self.cache.get(cell.style_id)
        if cached is not None:
            return cached
        style: dict[str, Any] = {}
        fill = self.fill(cell.fill)
        if fill:
            style["fill"] = fill
        colour = self.colour(cell.font.color) if cell.font else None
        if colour and colour != "#000000":
            style["color"] = colour
        if cell.font and cell.font.b:
            style["bold"] = True
        number_format = cell.number_format
        result = (style, None if number_format == "General" else number_format)
        self.cache[cell.style_id] = result
        return result


def _read_cells(
    ws_formulas: Any, ws_values: Any, styles: _StyleCache, serial_60: set[str], windows: bool
) -> tuple[list[dict[str, Any]], str | None]:
    # `_cells` holds only the cells present in the file. iter_rows() would walk the whole dimension,
    # which can be every row in the sheet when a file formats an entire column.
    cells = ws_formulas._cells
    values = ws_values._cells

    array_members: dict[tuple[int, int], str] = {}
    for (row, column), cell in cells.items():
        if isinstance(cell.value, ArrayFormula) and cell.value.ref:
            low_col, low_row, high_col, high_row = range_boundaries(cell.value.ref)
            text = _formula_text(cell.value) or ""
            if (high_col - low_col + 1) * (high_row - low_row + 1) <= MAX_ARRAY_EXPANSION:
                for r in range(low_row, high_row + 1):
                    for c in range(low_col, high_col + 1):
                        array_members[(r, c)] = text

    out: list[dict[str, Any]] = []
    rows: list[int] = []
    columns: list[int] = []
    for key in sorted(cells):
        cell = cells[key]
        if type(cell).__name__ == "MergedCell":
            continue
        special = _formula_text(cell.value)
        formula = special or array_members.get(key)
        if formula is None and cell.data_type == "f":
            formula = clean_formula(str(cell.value))
        stored = values.get(key)
        if formula is not None:
            value, kind = encode_value(
                stored.value if stored is not None else None,
                stored.data_type if stored is not None else None,
            )
        else:
            value, kind = encode_value(cell.value, cell.data_type)
        if value == "" and kind == "s":
            value = None
        if windows and kind == "d" and cell.coordinate in serial_60:
            value = "1900-02-29"  # Excel's leap-year bug: the day exists only in Excel.

        style, number_format = styles.of(cell)
        comment = cell.comment.text if cell.comment else None
        if value is None and formula is None and comment is None and "fill" not in style:
            continue

        entry: dict[str, Any] = {"ref": cell.coordinate, "v": value, "t": kind}
        if formula is not None:
            entry["f"] = formula
        if number_format:
            entry["fmt"] = number_format
        if style:
            entry["style"] = style
        if comment is not None:
            entry["comment"] = comment
        out.append(entry)
        rows.append(key[0])
        columns.append(key[1])

    if not out:
        return out, None
    dimension = (
        f"{get_column_letter(min(columns))}{min(rows)}:{get_column_letter(max(columns))}{max(rows)}"
    )
    return out, dimension


def _validations(worksheet: Any) -> list[dict[str, Any]]:
    out = []
    for item in worksheet.data_validations.dataValidation:
        entry: dict[str, Any] = {"ranges": str(item.sqref).split(), "type": item.type or "none"}
        if item.operator:
            entry["operator"] = item.operator
        entry["allowBlank"] = bool(item.allow_blank)
        if item.formula1 is not None:
            entry["formula1"] = item.formula1
        if item.formula2 is not None:
            entry["formula2"] = item.formula2
        out.append(entry)
    return out


def _dxf_style(dxf: Any, styles: _StyleCache) -> dict[str, Any]:
    if dxf is None:
        return {}
    style: dict[str, Any] = {}
    if dxf.fill is not None:
        # In a differential format a solid fill's visible colour is bgColor, the reverse of a cell.
        fill = styles.colour(getattr(dxf.fill, "bgColor", None)) or styles.fill(dxf.fill)
        if fill:
            style["fill"] = fill
    if dxf.font is not None:
        colour = styles.colour(dxf.font.color)
        if colour:
            style["color"] = colour
        if dxf.font.b:
            style["bold"] = True
    return style


def _conditional_formats(worksheet: Any, styles: _StyleCache) -> list[dict[str, Any]]:
    out = []
    for group in worksheet.conditional_formatting:
        ranges = str(group.sqref).split()
        for rule in group.rules:
            entry: dict[str, Any] = {
                "ranges": ranges,
                "type": rule.type,
                "formulas": [clean_formula(str(f)) for f in rule.formula],
                "priority": rule.priority or 0,
            }
            if rule.operator:
                entry["operator"] = rule.operator
            if rule.text:
                entry["text"] = rule.text
            if rule.stopIfTrue:
                entry["stopIfTrue"] = True
            style = _dxf_style(rule.dxf, styles)
            if style:
                entry["style"] = style
            if rule.colorScale is not None:
                colours = [styles.colour(color) for color in rule.colorScale.color]
                entry["colours"] = [colour for colour in colours if colour]
            out.append(entry)
    return out


def _tables(worksheet: Any) -> list[dict[str, Any]]:
    out = []
    for table in worksheet.tables.values():
        columns = []
        for column in table.tableColumns:
            entry: dict[str, Any] = {"name": column.name}
            if column.calculatedColumnFormula is not None:
                entry["formula"] = clean_formula(str(column.calculatedColumnFormula.attr_text))
            if column.totalsRowFunction:
                entry["totalsFunction"] = column.totalsRowFunction
            columns.append(entry)
        out.append(
            {
                "name": table.name,
                "ref": table.ref,
                "headerRowCount": 1 if table.headerRowCount is None else table.headerRowCount,
                "totalsRowCount": table.totalsRowCount or 0,
                "columns": columns,
            }
        )
    return sorted(out, key=lambda item: item["name"])


def _hidden_rows(worksheet: Any) -> list[str]:
    """Hidden rows as compact ranges such as "5:9"."""
    rows = sorted(index for index, row in worksheet.row_dimensions.items() if row.hidden)
    runs: list[list[int]] = []
    for row in rows:
        if runs and row == runs[-1][1] + 1:
            runs[-1][1] = row
        else:
            runs.append([row, row])
    return [f"{low}:{high}" for low, high in runs]


def _hidden_columns(worksheet: Any) -> list[str]:
    """Hidden columns as compact ranges such as "A:C". Files often hide everything unused."""
    spans = sorted(
        (column.min, column.max)
        for column in worksheet.column_dimensions.values()
        if column.hidden and column.min and column.max
    )
    runs: list[list[int]] = []
    for low, high in spans:
        if runs and low <= runs[-1][1] + 1:
            runs[-1][1] = max(runs[-1][1], high)
        else:
            runs.append([low, high])
    return [f"{get_column_letter(low)}:{get_column_letter(high)}" for low, high in runs]


def _empty_sheet(sheet: RawSheet, index: int) -> dict[str, Any]:
    return {
        "name": sheet.name,
        "index": index,
        "state": sheet.state,
        "protected": False,
        "rtl": False,
        "dimension": None,
        "hiddenRows": [],
        "hiddenColumns": [],
        "cells": [],
        "merges": [],
        "validations": [],
        "conditionalFormats": [],
        "tables": [],
    }


def _worksheet(
    sheet: RawSheet,
    index: int,
    ws_formulas: Any,
    ws_values: Any,
    styles: _StyleCache,
    package: RawPackage,
    windows: bool,
) -> dict[str, Any]:
    cells, dimension = _read_cells(
        ws_formulas, ws_values, styles, package.serial_60_cells.get(sheet.name, set()), windows
    )
    views = ws_formulas.views.sheetView if ws_formulas.views else []
    conditional = _conditional_formats(ws_formulas, styles)
    # Excel stores a 2010 data bar or icon set twice: the main rule and its x14 extension.
    known = {(tuple(rule["ranges"]), rule["type"]) for rule in conditional}
    conditional += [
        rule
        for rule in package.ext_conditional_formats.get(sheet.name, [])
        if (tuple(rule["ranges"]), rule["type"]) not in known
    ]
    conditional.sort(key=lambda item: (item["priority"], item["ranges"], item["type"]))
    return {
        "name": sheet.name,
        "index": index,
        "state": sheet.state,
        "protected": bool(ws_formulas.protection and ws_formulas.protection.sheet),
        "rtl": bool(views and views[0].rightToLeft),
        "dimension": dimension,
        "hiddenRows": _hidden_rows(ws_formulas),
        "hiddenColumns": _hidden_columns(ws_formulas),
        "cells": cells,
        "merges": sorted(str(item) for item in ws_formulas.merged_cells.ranges),
        "validations": _validations(ws_formulas) + package.ext_validations.get(sheet.name, []),
        "conditionalFormats": conditional,
        "tables": _tables(ws_formulas),
    }


def _defined_names(workbook: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [
        {"name": name, "ref": item.attr_text or ""} for name, item in workbook.defined_names.items()
    ]
    for worksheet in workbook.worksheets:
        for name, item in worksheet.defined_names.items():
            out.append({"name": name, "scope": worksheet.title, "ref": item.attr_text or ""})
    return sorted(out, key=lambda item: (item["name"], item.get("scope", "")))


def read_workbook(path: str, package: RawPackage) -> dict[str, Any]:
    """Return `sheets` and `definedNames`. Raises on a file openpyxl can't parse."""
    with warnings.catch_warnings():
        # openpyxl warns about what it drops; the raw pass reads those parts.
        warnings.simplefilter("ignore")
        with_formulas = load_workbook(path, data_only=False, rich_text=False, keep_links=False)
        with_results = load_workbook(path, data_only=True, rich_text=False, keep_links=False)
    try:
        styles = _StyleCache(with_formulas, package.palette)
        windows = with_formulas.epoch == WINDOWS_EPOCH
        worksheets = {ws.title for ws in with_formulas.worksheets}
        sheets = []
        for index, sheet in enumerate(package.sheets):
            if sheet.name in worksheets:
                sheets.append(
                    _worksheet(
                        sheet,
                        index,
                        with_formulas[sheet.name],
                        with_results[sheet.name],
                        styles,
                        package,
                        windows,
                    )
                )
            else:
                # A chart, macro or dialog sheet. It keeps its place so that every sheet gets an
                # outcome (R-3); `unsupported` records what it holds.
                sheets.append(_empty_sheet(sheet, index))
        return {"sheets": sheets, "definedNames": _defined_names(with_formulas)}
    finally:
        with_formulas.close()
        with_results.close()
