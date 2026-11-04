"""R-23: compare an edited workbook with the data, by key columns. Applying it is the runtime's job."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

from openpyxl.utils import column_index_from_string, get_column_letter

from daftar_worker.reader import read_file
from daftar_worker.roundtrip.export import MASK, _first_column, extra_tab, period_label, sheet_name
from daftar_worker.sheet.grid import Cell, Grid, text_of
from daftar_worker.sheet.names import fingerprint
from daftar_worker.sheet.values import TOTAL_WORDS, convert_value


TOLERANCE = 1e-9
PERIOD_NAME = re.compile(r"[0-9]{4}(-(0[1-9]|1[0-2]|Q[1-4]))?")


def _choice_key(field: dict[str, Any], text: str) -> str | None:
    wanted = fingerprint(text)
    for choice in field.get("choices", []):
        names = [choice.get("source"), choice["label"]["fr"], choice["label"]["ar"], choice["key"]]
        if any(name is not None and fingerprint(str(name)) == wanted for name in names):
            return str(choice["key"])
    return None


def _plain(field: dict[str, Any], cell: Cell, zone: ZoneInfo) -> Any:
    """A cell in the form the data holds it. A link stays as its key's text; the runtime resolves it."""
    kind = field["type"]
    if kind == "link":
        return text_of(cell) or None
    if kind == "choice":
        return _choice_key(field, text_of(cell))
    if kind == "multichoice":
        keys = [_choice_key(field, part) for part in re.split(r"\s*;\s*", text_of(cell)) if part]
        return keys if keys and all(keys) else None
    value = convert_value(field, cell)
    if kind == "datetime" and value is not None:
        # A sheet has no time zones, whatever offset the reader assumed: it shows the firm's clock.
        moment = datetime.fromisoformat(value).replace(tzinfo=zone)
        return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return value


def _normal(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    # A sheet's text reaches us with its spacing tidied, so spacing alone is neither a key nor an edit.
    return " ".join(str(value).split())


def _same(field: dict[str, Any], current: Any, incoming: Any) -> bool:
    if current in (None, "") or incoming in (None, ""):
        return current in (None, "") and incoming in (None, "")
    kind = field["type"]
    if kind in ("link", "text", "longtext"):
        return _normal(current) == _normal(incoming)
    if kind == "multichoice":
        return sorted(current) == sorted(incoming)
    if kind == "date":
        return str(current)[:10] == str(incoming)[:10]
    if kind == "datetime":
        # A sheet shows whole seconds at best, so a stored fraction of one isn't an edit.
        return abs((_instant(current) - _instant(incoming)).total_seconds()) < 1
    if isinstance(current, (int, float)) and isinstance(incoming, (int, float)) and not isinstance(current, bool):
        return abs(current - incoming) <= TOLERANCE * max(abs(current), abs(incoming))
    return bool(current == incoming)


def _instant(value: Any) -> datetime:
    moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _locate_columns(grid: Grid, mapping: dict[str, Any], first: int) -> dict[str, int]:
    """Find columns by their header text, so a moved column still lines up. Else by their letter."""
    header_row = mapping["headerRow"]
    by_header: dict[str, int] = {}
    for row, column in sorted(grid.cells):
        if row == header_row:
            by_header.setdefault(fingerprint(text_of(grid.cells[(row, column)])), column)
    located: dict[str, int] = {}
    for position, item in enumerate(mapping["columns"]):
        found = by_header.get(fingerprint(item["header"]))
        if found is not None:
            located[item["field"]] = found
        elif not by_header:
            located[item["field"]] = column_index_from_string(item["column"]) if item.get("column") else first + position
    return located


def _is_total_row(grid: Grid, row: int, columns: list[int], keys: list[int]) -> bool:
    """Written by an export, or typed by hand: a label saying so, or no key and only formulas."""
    filled = [cell for cell in (grid.get(row, column) for column in columns) if cell is not None]
    if not filled:
        return True
    # "Total Énergies" with a typed number is a customer: a label counts only beside a formula, or alone.
    if any(cell.is_text and TOTAL_WORDS.match(text_of(cell)) for cell in filled) and (any(cell.formula for cell in filled) or len(filled) == 1):
        return True
    return all(grid.get(row, column) is None for column in keys) and any(cell.formula for cell in filled)


def _rows(grid: Grid, mapping: dict[str, Any], located: dict[str, int], keys: list[str]) -> Iterator[int]:
    columns = list(located.values())
    key_columns = [located[key] for key in keys if key in located]
    bottom = max((row for row, column in grid.cells if column in columns), default=0)
    for row in range(mapping["headerRow"] + 1, bottom + 1):
        if not _is_total_row(grid, row, columns, key_columns):
            yield row


def _first_day(label: str | None) -> str | None:
    if not label:
        return None
    if "Q" in label:
        year, quarter = label.split("-Q")
        return f"{year}-{(int(quarter) - 1) * 3 + 1:02d}-01"
    return f"{label}-01" if "-" in label else f"{label}-01-01"


class _Entity:
    def __init__(self, entity: dict[str, Any], mapping: dict[str, Any], current: list[dict[str, Any]], zone: ZoneInfo, problems: list[dict[str, Any]]) -> None:
        self.entity = entity
        self.mapping = mapping
        self.zone = zone
        self.problems = problems
        self.fields = {field["key"]: field for field in entity["fields"]}
        period = entity.get("period") or {}
        self.period_key: str | None = period.get("field")
        self.granularity: str = period.get("granularity", "month")
        self.keys = [key for key in mapping["keyColumns"] if key != self.period_key]
        self.existing: dict[str, dict[str, Any]] = {}
        for row in current:
            key = self.key_of(row)
            if key in self.existing:
                # Which row an edit means can't be told, so neither is compared.
                problems.append({"entity": entity["key"], "field": "duplicateKey", "id": row.get("_id")})
            else:
                self.existing[key] = row
        self.seen: set[str] = set()
        self.added: list[dict[str, Any]] = []
        self.changed: list[dict[str, Any]] = []

    def key_of(self, row: dict[str, Any]) -> str:
        parts = [_normal(row.get(key)) for key in self.keys]
        if self.period_key:
            parts.insert(0, period_label(row.get(self.period_key), self.granularity) or "")
        return "␟".join(parts)

    def read_tab(self, grid: Grid, source: dict[str, Any], label: str | None) -> None:
        located = _locate_columns(grid, self.mapping, _first_column(source))
        for row in _rows(grid, self.mapping, located, self.keys):
            self.read_row(grid, row, located, label)

    def read_row(self, grid: Grid, row: int, located: dict[str, int], label: str | None) -> None:
        incoming: dict[str, Any] = {}
        hidden: list[str] = []
        for key, column in located.items():
            field = self.fields.get(key)
            if field is None or field["type"] in ("computed", "child"):
                continue
            cell = grid.get(row, column)
            if cell is None:
                incoming[key] = None
            elif cell.value == MASK:  # A masked export comes back masked: not a change.
                hidden.append(key)
            else:
                value = _plain(field, cell, self.zone)
                if value is None:
                    self.problems.append({"sheet": grid.name, "cell": f"{get_column_letter(column)}{row}", "field": key})
                    hidden.append(key)
                else:
                    incoming[key] = value
        if self.period_key:
            incoming[self.period_key] = _first_day(label)
        if not all(incoming.get(key) not in (None, "") for key in self.keys):
            self.problems.append({"sheet": grid.name, "cell": f"row {row}", "field": "missingKey"})
            return
        key = self.key_of(incoming)
        if key in self.seen:
            self.problems.append({"sheet": grid.name, "cell": f"row {row}", "field": "duplicateKey"})
            return
        self.seen.add(key)
        before = self.existing.get(key)
        if before is None:
            self.added.append({"key": key, "values": {name: value for name, value in incoming.items() if value is not None}})
            return
        fields: dict[str, list[Any]] = {}
        for name, value in incoming.items():
            if name == self.period_key or self._same_or_hidden(grid, row, name, before.get(name), value):
                continue
            fields[name] = [before.get(name), value]
        if fields:
            self.changed.append({"key": key, "id": before.get("_id"), "version": before.get("_version"), "fields": fields})

    def _same_or_hidden(self, grid: Grid, row: int, name: str, before: Any, value: Any) -> bool:
        if before != MASK:
            return _same(self.fields[name], before, value)
        # This user can't see the field, so they can't change it. Blank is what deleting the mask looks like.
        if value is not None:
            self.problems.append({"sheet": grid.name, "cell": f"row {row}", "field": name, "reason": "hidden"})
        return True

    def result(self, any_sheet: bool) -> dict[str, Any]:
        # A sheet that isn't in the file says nothing about its rows, so they aren't "missing".
        missing = [{"key": key, "id": row.get("_id")} for key, row in self.existing.items() if key not in self.seen] if any_sheet else []
        return {"added": self.added, "changed": self.changed, "missing": missing}


def _extra_tabs(grids: dict[str, Grid], known: set[str], entity_key: str, shared: bool) -> Iterator[tuple[Grid, str | None]]:
    """The tabs an export adds for periods the workbook never had, or one the owner added the same way."""
    for name, grid in grids.items():
        if name in known:
            continue
        if extra_tab(None, entity_key, shared) == name:
            yield grid, None
            continue
        label = name.removesuffix(f" {entity_key}") if shared else name
        if PERIOD_NAME.fullmatch(label) and extra_tab(label, entity_key, shared) == name:
            yield grid, label


def diff_workbook(
    path: str | Path,
    spec: dict[str, Any],
    current: dict[str, list[dict[str, Any]]],
    file_name: str | None = None,
    timezone: str = "UTC",
) -> dict[str, Any]:
    """`current` holds each entity's rows in export form. Nothing here writes anything."""
    snapshot = read_file(path, file_name)
    grids = {sheet["name"]: Grid(sheet) for sheet in snapshot["sheets"]}
    zone = ZoneInfo(timezone)
    entities = {entity["key"]: entity for entity in spec["entities"]}
    shared = sum(1 for entity in spec["entities"] if entity.get("period")) > 1
    known = {name for mapping in spec["mapping"] for source in mapping["sources"] for name in (source["sheet"], sheet_name(source["sheet"]))}
    result: dict[str, Any] = {}
    problems: list[dict[str, Any]] = []
    for mapping in spec["mapping"]:
        entity = entities.get(mapping["entity"])
        if entity is None:
            continue
        state = _Entity(entity, mapping, current.get(entity["key"], []), zone, problems)
        if not state.keys:
            # Without keys no row can be matched, and guessing would overwrite the wrong one.
            problems.append({"entity": entity["key"], "field": "noKeyColumns"})
            result[entity["key"]] = {"added": [], "changed": [], "missing": []}
            continue
        any_sheet = False
        for source in mapping["sources"]:
            grid = grids.get(source["sheet"]) or grids.get(sheet_name(source["sheet"]))
            if grid is not None:
                any_sheet = True
                state.read_tab(grid, source, source.get("period"))
        if state.period_key:
            for grid, label in _extra_tabs(grids, known, entity["key"], shared):
                any_sheet = True
                state.read_tab(grid, {"sheet": grid.name}, label)
        result[entity["key"]] = state.result(any_sheet)
    return {"entities": result, "problems": problems}


