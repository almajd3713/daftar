"""R-9: conditional formats and fills on a status-like column become choices with colours."""

from collections import Counter, defaultdict
import re
from typing import Any

from openpyxl.utils import get_column_letter

from daftar_worker.analyser import explain
from daftar_worker.analyser.grid import Grid, a1_range, column_index, text_of
from daftar_worker.analyser.kinds import STATUS_HINT
from daftar_worker.analyser.regions import Table
from daftar_worker.analyser.types import TypeGuess
from daftar_worker.analyser.workbook_view import SheetView


EXPRESSION = re.compile(r'^\$?([A-Z]{1,3})\$?[0-9]+\s*=\s*"([^"]*)"$')
TEXT_VALUE = re.compile(r'^"(.*)"$')
CONSISTENT = 0.9
# White and black are how cells get reset or read as text, not states.
NEUTRAL = {"#FFFFFF", "#000000"}
MAX_CHOICES = 12


def _overlaps(ranges: list[str], column: int, top: int, bottom: int) -> bool:
    for item in ranges:
        match = re.fullmatch(r"([A-Z]+)([0-9]+)(?::([A-Z]+)([0-9]+))?", item)
        if match is None:
            continue
        left = column_index(match.group(1))
        right = column_index(match.group(3) or match.group(1))
        low = int(match.group(2))
        high = int(match.group(4) or match.group(2))
        if left <= column <= right and low <= bottom and high >= top:
            return True
    return False


def _rule_value(rule: dict[str, Any], column: int) -> str | None:
    """The text a rule colours on this column, if it's that kind of rule."""
    formulas = rule.get("formulas") or []
    kind = rule.get("type")
    if kind == "cellIs" and rule.get("operator") == "equal" and formulas:
        match = TEXT_VALUE.match(str(formulas[0]))
        return match.group(1) if match else None
    if kind in ("containsText", "beginsWith") and rule.get("text"):
        return str(rule["text"])
    if kind == "expression" and formulas:
        match = EXPRESSION.match(str(formulas[0]).lstrip("="))
        if match and column_index(match.group(1)) == column:
            return match.group(2)
    return None


def _from_rules(grid: Grid, table: Table, column: int) -> list[dict[str, Any]]:
    top, bottom = table.data_top, table.data_bottom
    colours: dict[str, str] = {}
    for rule in sorted(grid.sheet["conditionalFormats"], key=lambda item: item.get("priority", 0)):
        fill = (rule.get("style") or {}).get("fill")
        if not fill or fill in NEUTRAL or not _overlaps(rule["ranges"], column, top, bottom):
            continue
        value = _rule_value(rule, column)
        if value is not None:
            colours.setdefault(value, fill)
    if not colours:
        return []
    counts: Counter[str] = Counter(text_of(grid.get(row, column)) for row in table.data_rows())
    return [
        {"value": value, "colour": colour, "count": counts.get(value, 0)}
        for value, colour in sorted(colours.items(), key=lambda item: (-counts.get(item[0], 0), item[0]))
    ]


def _from_fills(grid: Grid, table: Table, column: int) -> list[dict[str, Any]]:
    by_value: dict[str | None, Counter[str]] = defaultdict(Counter)
    for row in table.data_rows():
        cell = grid.cells.get((row, column))
        if cell is None:
            continue
        fill = cell.style.get("fill")
        if fill in NEUTRAL:
            fill = None
        value = text_of(cell) or None
        if fill or value is not None:
            by_value[value][fill or ""] += 1
    colours = {colour for counter in by_value.values() for colour in counter if colour}
    # One colour across the whole column is decoration. It takes two colours to mean something.
    if len(colours) < 2 or len(by_value) > MAX_CHOICES:
        return []
    choices = []
    consistent = total = 0
    for value, counter in by_value.items():
        if value is None:
            # Blank cells have no text to agree with: each colour is a state of its own.
            choices += [
                {"value": None, "colour": colour, "count": count} for colour, count in counter.items() if colour
            ]
            continue
        colour, count = counter.most_common(1)[0]
        consistent += count
        total += sum(counter.values())
        if colour:
            choices.append({"value": value, "colour": colour, "count": sum(counter.values())})
    if total and consistent / total < CONSISTENT:
        return []
    return sorted(choices, key=lambda item: (-item["count"], str(item["value"]), item["colour"]))


def coloured_columns(grid: Grid, table: Table) -> set[int]:
    """Columns whose colours carry meaning. Sheet kind counts these as status columns."""
    return {
        column
        for column in range(table.rect.left, table.rect.right + 1)
        if _from_rules(grid, table, column) or _from_fills(grid, table, column)
    }


def _colour_only(choices: list[dict[str, Any]]) -> bool:
    return all(choice["value"] is None for choice in choices)


def status_findings(make: Any, views: list[SheetView]) -> list[dict[str, Any]]:
    findings = []
    for view in views:
        if view.outcome == "notConverted":
            continue
        grid = view.grid
        for table, labels, guesses in zip(view.layout.tables, view.labels, view.guesses, strict=True):
            for column in range(table.rect.left, table.rect.right + 1):
                finding = _column_finding(make, grid, table, column, labels.get(column, ""), guesses.get(column))
                if finding is not None:
                    findings.append(finding)
    return findings


def _column_finding(make: Any, grid: Grid, table: Table, column: int, label: str, guess: TypeGuess | None) -> dict[str, Any] | None:
    from_rules = _from_rules(grid, table, column)
    choices = from_rules or _from_fills(grid, table, column)
    if not choices:
        return None
    # Colours on a free-text or numeric column aren't statuses, unless its title says so.
    named_status = bool(STATUS_HINT.search(label))
    status_like = named_status or (guess is not None and guess.type in ("choice", "boolean"))
    colour_only = _colour_only(choices)
    if not status_like and not colour_only:
        return None
    # One coloured value says "highlight this", which is only a status if the title says so.
    if not named_status and len(choices) < 2:
        return None
    choices = [choice for choice in choices if choice["value"] is not None] if not colour_only else choices
    if from_rules:
        score, source = 0.9, "conditionalFormat"
    elif colour_only:
        score, source = 0.5, "fill"  # A colour with no text: its meaning is anyone's guess.
    else:
        score, source = (0.8 if STATUS_HINT.search(label) else 0.65), "fill"
    letter = get_column_letter(column)
    evidence = [a1_range(table.data_top, column, table.data_bottom, column)]
    finding: dict[str, Any] = make(
        "statusColours",
        grid.name,
        evidence,
        {"table": table.rect.a1, "column": letter, "name": label or letter, "source": source, "choices": choices},
        score,
        explain.status_colours(label or letter, choices, source),
    )
    return finding
