"""R-22: write the data back in the layout the owner knows: their sheets, headers and column order."""

from datetime import date, datetime
import io
import re
from typing import Any
from zoneinfo import ZoneInfo

from openpyxl.utils import column_index_from_string, get_column_letter
import xlsxwriter

from daftar_worker.formulas.engine import EngineError, recalculate


MONEY_FORMAT = '#,##0.00 "DA"'
DATE_FORMAT = "dd/mm/yyyy"
DATETIME_FORMAT = "dd/mm/yyyy hh:mm"
PERCENT_FORMAT = "0.00%"
TOTAL_WORDS = {"fr-DZ": "Total", "ar-DZ": "المجموع"}
TOTAL_FUNCTIONS = {"sum": "SUM", "average": "AVERAGE", "count": "COUNT", "counta": "COUNTA", "max": "MAX", "min": "MIN", "product": "PRODUCT"}
MASK = "*"
ILLEGAL_SHEET = re.compile(r"[\[\]:*?/\\]")
RELATIVE_ROW = re.compile(r"\"(?:[^\"]|\"\")*\"|'(?:[^']|'')+'!|\[[^\]]*\]|(?<![\w.\]$])(\$?[A-Z]{1,3})(\$?)([1-9][0-9]*)(?![\w(.\[])")
NO_PERIOD = "Sans période"


def shift_rows(formula: str, delta: int) -> str:
    """Copy a formula down, as Excel would."""

    def replace(match: re.Match[str]) -> str:
        if match.group(1) is None or match.group(2) == "$":
            return match.group(0)
        return f"{match.group(1)}{int(match.group(3)) + delta}"

    return RELATIVE_ROW.sub(replace, formula)


def sheet_name(name: str) -> str:
    return ILLEGAL_SHEET.sub(" ", name).strip()[:31] or "Feuille"


def _column_number(mapping_column: dict[str, Any], position: int, first: int) -> int:
    letter = mapping_column.get("column")
    return column_index_from_string(letter) if letter else first + position


def _first_column(source: dict[str, Any]) -> int:
    match = re.match(r"[A-Z]+", source.get("range") or "")
    return column_index_from_string(match.group(0)) if match else 1


def _kind(field: dict[str, Any]) -> str:
    return str(field.get("resultType") or field["type"]) if field["type"] == "computed" else str(field["type"])


class _Formats:
    def __init__(self, book: Any) -> None:
        self.header = book.add_format({"bold": True})
        self.money = book.add_format({"num_format": MONEY_FORMAT})
        self.percent = book.add_format({"num_format": PERCENT_FORMAT})
        self.date = book.add_format({"num_format": DATE_FORMAT})
        self.datetime = book.add_format({"num_format": DATETIME_FORMAT})
        self.total_label = book.add_format({"bold": True})
        self.total_money = book.add_format({"bold": True, "num_format": MONEY_FORMAT})
        self.total = book.add_format({"bold": True})

    def of(self, kind: str) -> Any:
        return {"money": self.money, "percent": self.percent, "date": self.date, "datetime": self.datetime}.get(kind)


def _choice_text(field: dict[str, Any], key: Any, locale: str) -> Any:
    for choice in field.get("choices", []):
        if choice["key"] == key:
            # The text the workbook had, so a re-import matches; else the label in the export's language.
            return choice.get("source") or choice["label"]["ar" if locale.startswith("ar") else "fr"]
    return key


def _write_value(sheet: Any, row: int, column: int, field: dict[str, Any], value: Any, formats: _Formats, locale: str, zone: ZoneInfo) -> None:
    """row and column are zero-based here, as XlsxWriter's are."""
    if value is None:
        return
    if value == MASK:
        sheet.write_string(row, column, MASK)
        return
    kind = _kind(field)
    if kind in ("integer", "decimal", "money", "percent") and isinstance(value, (int, float)):
        sheet.write_number(row, column, value, formats.of(kind))
    elif kind == "date" and isinstance(value, str):
        sheet.write_datetime(row, column, date.fromisoformat(value[:10]), formats.date)
    elif kind == "datetime" and isinstance(value, str):
        # Excel has no time zones: the sheet shows the time the firm's clock showed.
        moment = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(zone).replace(tzinfo=None)
        sheet.write_datetime(row, column, moment, formats.datetime)
    elif kind == "boolean":
        sheet.write_boolean(row, column, bool(value))
    elif kind == "choice":
        sheet.write_string(row, column, str(_choice_text(field, value, locale)))
    elif kind == "multichoice" and isinstance(value, list):
        sheet.write_string(row, column, "; ".join(str(_choice_text(field, item, locale)) for item in value))
    else:
        # write_string, never write(): text that looks like a formula must stay text.
        sheet.write_string(row, column, str(value))


def _sources(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    return mapping.get("sources") or [{"sheet": mapping["entity"]}]


def period_label(value: Any, granularity: str) -> str | None:
    """The period a date falls in, in the form a mapping's tabs use."""
    text = str(value or "")[:10]
    if not text:
        return None
    if granularity == "year":
        return text[:4]
    if granularity == "quarter":
        return f"{text[:4]}-Q{(int(text[5:7]) - 1) // 3 + 1}"
    return text[:7]


def extra_tab(label: str | None, entity: str, shared: bool) -> str:
    """The tab for a period the workbook never had. Two entities can't both have a tab called 2026-04."""
    return sheet_name(f"{label or NO_PERIOD} {entity}" if shared else (label or NO_PERIOD))


def _tabs(entity: dict[str, Any], mapping: dict[str, Any], rows: list[dict[str, Any]], shared: bool) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Every row in exactly one tab. A month added in the app gets a tab of its own: an export loses nothing."""
    sources = _sources(mapping)
    tabs: list[tuple[dict[str, Any], list[dict[str, Any]]]] = [(source, []) for source in sources]
    period = entity.get("period")
    if not period:
        tabs[0][1].extend(rows)
        return tabs
    first_of = {source["period"]: place for place, source in reversed(list(enumerate(sources))) if source.get("period")}
    extras: dict[str | None, list[dict[str, Any]]] = {}
    for row in rows:
        label = period_label(row.get(period["field"]), period["granularity"])
        if label in first_of:
            tabs[first_of[label]][1].append(row)
        else:
            extras.setdefault(label, []).append(row)
    for label, extra_rows in sorted(extras.items(), key=lambda item: item[0] or ""):
        tabs.append(({"sheet": extra_tab(label, entity["key"], shared)}, extra_rows))
    return tabs


def _unplaced(mapping: dict[str, Any], placed: list[tuple[dict[str, Any], int]], rows: list[dict[str, Any]], fields: dict[str, dict[str, Any]]) -> list[tuple[dict[str, Any], int]]:
    """A row holding a value for a column its tab never had: the column joins the tab, so nothing is lost."""
    have = {item["field"] for item, _ in placed}
    next_column = max((column for _, column in placed), default=0)
    extra = []
    for item in mapping["columns"]:
        if item["field"] in fields and item["field"] not in have and any(row.get(item["field"]) not in (None, "") for row in rows):
            next_column += 1
            extra.append((item, next_column))
    return extra


def _formula_fits(field: dict[str, Any], here: dict[str, int], home: dict[str, int]) -> bool:
    """A formula names letters of the mapping's own layout, so it holds only where they're the same."""
    needed = [field["key"], *field["computed"].get("deps", [])]
    return all(here.get(key) == home.get(key) for key in needed)


def _write_tab(
    book: Any,
    formats: _Formats,
    entity: dict[str, Any],
    mapping: dict[str, Any],
    source: dict[str, Any],
    rows: list[dict[str, Any]],
    locale: str,
    use_formulas: bool,
    taken: set[str],
    zone: ZoneInfo,
) -> None:
    name = sheet_name(source["sheet"])
    while name in taken:
        name = f"{name[:28]} {len(taken)}"
    taken.add(name)
    sheet = book.add_worksheet(name)
    if locale.startswith("ar"):
        sheet.right_to_left()
    fields = {field["key"]: field for field in entity["fields"]}
    first = _first_column(source)
    header_row = source.get("headerRow", mapping["headerRow"])
    layout = source.get("columns") or mapping["columns"]
    placed = [
        (item, _column_number(item, position, first))
        for position, item in enumerate(layout)
        if item["field"] in fields
    ]
    placed += _unplaced(mapping, placed, rows, fields)
    letters_here = {item["field"]: column for item, column in placed}
    home_letters = {
        item["field"]: _column_number(item, position, _first_column(_sources(mapping)[0]))
        for position, item in enumerate(mapping["columns"])
    }
    same_rows = header_row == mapping["headerRow"]
    for item, column in placed:
        sheet.write_string(header_row - 1, column - 1, item["header"], formats.header)
    first_data = header_row + 1
    for index, row in enumerate(rows):
        number = first_data + index
        for item, column in placed:
            field = fields[item["field"]]
            value = row.get(item["field"])
            formula = (field.get("computed") or {}).get("excel")
            if formula and use_formulas and value != MASK and same_rows and _formula_fits(field, letters_here, home_letters):
                # The value goes in too, so a reader that skips recalculation still sees the result.
                sheet.write_formula(
                    number - 1,
                    column - 1,
                    shift_rows(formula, index),
                    formats.of(_kind(field)),
                    value if isinstance(value, (int, float, str, bool)) else 0,
                )
            else:
                _write_value(sheet, number - 1, column - 1, field, value, formats, locale, zone)
    # A total over a column of masks would be a 0 that looks like an answer.
    masked = {key for row in rows for key, value in row.items() if value == MASK}
    _write_totals(sheet, formats, mapping, [pair for pair in placed if pair[0]["field"] not in masked], fields, first_data, len(rows), locale)


def _write_totals(
    sheet: Any,
    formats: _Formats,
    mapping: dict[str, Any],
    placed: list[tuple[dict[str, Any], int]],
    fields: dict[str, dict[str, Any]],
    first_data: int,
    count: int,
    locale: str,
) -> None:
    totals = {item["field"]: item["function"] for item in mapping.get("totals", [])}
    if not totals or not count:
        return
    row = first_data + count
    label_done = False
    for item, column in placed:
        function = totals.get(item["field"])
        if function:
            letter = get_column_letter(column)
            style = formats.total_money if _kind(fields[item["field"]]) == "money" else formats.total
            sheet.write_formula(row - 1, column - 1, f"={TOTAL_FUNCTIONS[function]}({letter}{first_data}:{letter}{row - 1})", style, 0)
        elif not label_done:
            sheet.write_string(row - 1, column - 1, TOTAL_WORDS.get(locale, "Total"), formats.total_label)
            label_done = True


def build_workbook(
    spec: dict[str, Any],
    rows_by_entity: dict[str, list[dict[str, Any]]],
    locale: str | None = None,
    use_formulas: bool = True,
    timezone: str = "UTC",
) -> bytes:
    """Write every entity the mapping knows, then fill in the results as the very last step."""
    language = locale or spec["app"]["defaultLocale"]
    zone = ZoneInfo(timezone)
    buffer = io.BytesIO()
    book = xlsxwriter.Workbook(buffer, {"in_memory": True})
    formats = _Formats(book)
    entities = {entity["key"]: entity for entity in spec["entities"]}
    shared = sum(1 for entity in spec["entities"] if entity.get("period")) > 1
    taken: set[str] = set()
    for mapping in spec["mapping"]:
        entity = entities.get(mapping["entity"])
        if entity is None:
            continue
        for source, rows in _tabs(entity, mapping, rows_by_entity.get(entity["key"], []), shared):
            _write_tab(book, formats, entity, mapping, source, rows, language, use_formulas, taken, zone)
    if not taken:
        book.add_worksheet("Daftar")
    book.close()
    data = buffer.getvalue()
    try:
        return recalculate(data)
    except EngineError:
        # The file still opens: Excel recalculates it, and the stored values are the app's own.
        return data
