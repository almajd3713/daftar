"""Turn structured references, such as Table1[[#This Row],[Qty]], into plain A1 references.

C-1 promises A1 formulas, the formula engine has no structured references, and neither do the
translator or an exported sheet that no longer has the Table. If anything in a reference can't be
resolved, it's left as written: the engine then shows #NAME?, which is flagged, never a wrong number.

A reference to a whole column becomes a fixed range, so like any range typed by hand it doesn't
grow with rows added later in the app.
"""

from dataclasses import dataclass
import re
from typing import Any

from openpyxl.utils import get_column_letter, range_boundaries


NAME_START = re.compile(r"[A-Za-z_\\\u0080-￿]")
NAME_PART = re.compile(r"[\w.\\\u0080-￿]")
SPECIALS = {"#all", "#data", "#headers", "#totals", "#this row"}


@dataclass(frozen=True)
class SheetTable:
    name: str
    sheet: str
    top: int
    left: int
    bottom: int
    right: int
    header_rows: int
    total_rows: int
    columns: tuple[str, ...]

    @property
    def data_top(self) -> int:
        return self.top + self.header_rows

    @property
    def data_bottom(self) -> int:
        return self.bottom - self.total_rows

    def contains(self, sheet: str, row: int, column: int) -> bool:
        return sheet == self.sheet and self.top <= row <= self.bottom and self.left <= column <= self.right


def tables_of(sheets: list[dict[str, Any]]) -> list[SheetTable]:
    found = []
    for sheet in sheets:
        for table in sheet.get("tables", []):
            left, top, right, bottom = range_boundaries(table["ref"])
            if None in (left, top, right, bottom):
                continue
            found.append(
                SheetTable(
                    table["name"], sheet["name"], int(top or 0), int(left or 0), int(bottom or 0), int(right or 0),
                    int(table["headerRowCount"]), int(table["totalsRowCount"]),
                    tuple(str(column["name"]) for column in table["columns"]),
                )
            )  # fmt: skip
    return found


def _closing(text: str, start: int) -> int | None:
    """Where the bracket opened at `start` closes. A ' escapes the next character in a column name."""
    depth = 0
    position = start
    while position < len(text):
        char = text[position]
        if char == "'":
            position += 1
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return position
        position += 1
    return None


def _column_name(text: str) -> str:
    return re.sub(r"'(.)", r"\1", text).strip().casefold()


def _parts(inner: str) -> list[str]:
    """The items of a reference, split on its top-level commas: [#Headers],[A]:[B] gives two."""
    out: list[str] = []
    depth = 0
    current = ""
    position = 0
    while position < len(inner):
        char = inner[position]
        if char == "'" and position + 1 < len(inner):
            current += inner[position : position + 2]
            position += 2
            continue
        depth += {"[": 1, "]": -1}.get(char, 0)
        if char == "," and depth == 0:
            out.append(current)
            current = ""
        else:
            current += char
        position += 1
    out.append(current)
    return [item.strip() for item in out]


def _unwrap(item: str) -> str:
    return item[1:-1] if item.startswith("[") and item.endswith("]") else item


def _quoted_sheet(name: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", name):
        return f"{name}!"
    escaped = name.replace("'", "''")
    return f"'{escaped}'!"


def _select(table: SheetTable, inner: str) -> tuple[list[str], tuple[int, int] | None] | None:
    """Which areas and which columns. None when the reference says something unknown."""
    areas: list[str] = []
    span: tuple[int, int] | None = None
    text = inner.strip()
    if text.startswith("@"):
        areas.append("#this row")
        text = text[1:].strip()
        if not text:
            return None
    for item in _parts(text) if text else []:
        kind = _unwrap(item).strip().casefold()
        if kind in SPECIALS:
            areas.append(kind)
            continue
        names = [_column_name(_unwrap(part)) for part in re.split(r"\]\s*:\s*\[", item.strip()[1:-1])] if item.startswith("[") and "]:[" in item.replace(" ", "") else [_column_name(_unwrap(item))]
        wanted = [name.casefold() for name in table.columns]
        if span is not None or any(name not in wanted for name in names):
            return None
        places = [wanted.index(name) for name in names]
        span = (min(places), max(places))
    return areas, span


def _rows(table: SheetTable, areas: list[str], row: int) -> tuple[int, int, bool] | None:
    """First row, last row, and whether it's the formula's own row. None if it makes no sense."""
    if not areas or areas == ["#data"]:
        return table.data_top, table.data_bottom, False
    if areas == ["#all"]:
        return table.top, table.bottom, False
    if areas == ["#this row"]:
        return (row, row, True) if table.data_top <= row <= table.data_bottom else None
    pieces = {
        "#headers": (table.top, table.data_top - 1),
        "#data": (table.data_top, table.data_bottom),
        "#totals": (table.data_bottom + 1, table.bottom),
    }
    chosen = [pieces[area] for area in areas if area in pieces]
    if len(chosen) != len(areas):
        return None
    first, last = min(item[0] for item in chosen), max(item[1] for item in chosen)
    if last < first or sum(end - start + 1 for start, end in chosen) != last - first + 1:
        return None
    return first, last, False


def _a1(table: SheetTable, inner: str, sheet: str, row: int) -> str | None:
    selected = _select(table, inner)
    if selected is None:
        return None
    areas, span = selected
    rows = _rows(table, areas, row)
    if rows is None:
        return None
    first_row, last_row, own_row = rows
    first_column = table.left + (span[0] if span else 0)
    last_column = table.left + (span[1] if span else table.right - table.left)
    start, end = get_column_letter(first_column), get_column_letter(last_column)
    prefix = "" if table.sheet == sheet else _quoted_sheet(table.sheet)
    if own_row:
        # Relative, so that copying the formula down reads each record's own row.
        return f"{prefix}{start}{row}" if start == end else f"{prefix}{start}{row}:{end}{row}"
    if start == end and first_row == last_row:
        return f"{prefix}${start}${first_row}"
    return f"{prefix}${start}${first_row}:${end}${last_row}"


def expand_formula(formula: str, tables: list[SheetTable], sheet: str, row: int, column: int) -> str:
    """The formula with every reference it can resolve in A1 form. Strings stay untouched."""
    if "[" not in formula:
        return formula
    by_name = {table.name.casefold(): table for table in tables}
    out: list[str] = []
    position = 0
    while position < len(formula):
        char = formula[position]
        if char in "\"'":
            end = position + 1
            while end < len(formula):
                if formula[end] == char:
                    if end + 1 < len(formula) and formula[end + 1] == char:
                        end += 2
                        continue
                    break
                end += 1
            out.append(formula[position : end + 1])
            position = end + 1
            continue
        if NAME_START.match(char) or char == "[":
            end = position
            while end < len(formula) and NAME_PART.match(formula[end]):
                end += 1
            name = formula[position:end]
            if end < len(formula) and formula[end] == "[":
                closing = _closing(formula, end)
                # [1]!Table1[Qty] is a table in another file, even if this one has a Table1 too.
                outside = bool(out) and out[-1].endswith("!")
                table = None if outside else (by_name.get(name.casefold()) if name else next((item for item in tables if item.contains(sheet, row, column)), None))
                replaced = _a1(table, formula[end + 1 : closing], sheet, row) if table and closing else None
                if replaced is not None and closing is not None:
                    out.append(replaced)
                    position = closing + 1
                    continue
                stop = (closing + 1) if closing else end + 1
                out.append(formula[position:stop])
                position = stop
                continue
            if end > position:
                out.append(name)
                position = end
                continue
        out.append(char)
        position += 1
    return "".join(out)


def expand_sheets(sheets: list[dict[str, Any]]) -> None:
    """Rewrite `f` in place, keeping what the file said in `fStructured`."""
    tables = tables_of(sheets)
    if not tables:
        return
    for sheet in sheets:
        for cell in sheet["cells"]:
            formula = cell.get("f")
            if not formula or "[" not in formula:
                continue
            match = re.match(r"([A-Z]+)([0-9]+)$", cell["ref"])
            if match is None:
                continue
            _, _, column, _ = range_boundaries(f"{match.group(1)}{match.group(2)}")
            expanded = expand_formula(formula, tables, sheet["name"], int(match.group(2)), int(column or 0))
            if expanded != formula:
                cell["fStructured"] = formula
                cell["f"] = expanded


__all__ = ["SheetTable", "expand_formula", "expand_sheets", "tables_of"]
