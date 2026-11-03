"""Score each sheet against the pattern of each outcome (R-3), and pick the best."""

from dataclasses import dataclass
import re
from typing import Any

from daftar_worker.analyser.grid import Grid, a1, column_index, text_of
from daftar_worker.analyser.regions import SheetLayout, Table
from daftar_worker.analyser.types import TypeGuess


STATUS_HINT = re.compile(
    r"statut|[ée]tat|status|avancement|[ée]tape|stage|الحالة|حالة|المرحلة", re.IGNORECASE
)
ASSIGNEE_HINT = re.compile(
    r"responsable|assign|technicien|charg[ée]|agent|owner|المسؤول|المكلف|التقني", re.IGNORECASE
)
MONTH_NAME = re.compile(
    r"\b(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]t|septembre|octobre|novembre|d[ée]cembre"
    r"|january|february|march|april|may|june|july|august|september|october|november|december)\b"
    r"|جانفي|فيفري|مارس|أفريل|افريل|ماي|جوان|جويلية|أوت|اوت|سبتمبر|أكتوبر|اكتوبر|نوفمبر|ديسمبر"
    r"|يناير|فبراير|أبريل|ابريل|مايو|يونيو|يوليو|أغسطس|اغسطس",
    re.IGNORECASE,
)
AMOUNT_TYPES = {"money", "decimal"}
CELL_REF = re.compile(r"\$?[A-Z]{1,3}\$?[0-9]+")
SHEET_REF = re.compile(r"(?:'((?:[^']|'')+)'|([^\s'!(),=+\-*/&<>]+))!")
MIN_FORMULAS_FOR_MODEL = 2


@dataclass
class KindResult:
    outcome: str
    reason: str | None
    score: float
    scores: dict[str, float]
    facts: dict[str, Any]


def referenced_sheets(snapshot: dict[str, Any]) -> dict[str, int]:
    """How many formulas and validation lists on other sheets point at each sheet."""
    counts: dict[str, int] = {}

    def note(text: str | None, owner: str) -> None:
        for match in SHEET_REF.finditer(text or ""):
            name = (match.group(1) or match.group(2)).replace("''", "'")
            if name != owner:
                counts[name] = counts.get(name, 0) + 1

    for sheet in snapshot["sheets"]:
        for cell in sheet["cells"]:
            note(cell.get("f"), sheet["name"])
        for validation in sheet["validations"]:
            note(validation.get("formula1"), sheet["name"])
    return counts


def _formula_chain_depth(grid: Grid) -> int:
    """How many formulas read another formula. Calculators chain; tables mostly don't."""
    formula_refs = {a1(row, column) for (row, column), cell in grid.cells.items() if cell.formula}
    count = 0
    for cell in grid.cells.values():
        if cell.formula:
            refs = {match.replace("$", "") for match in CELL_REF.findall(cell.formula)}
            if refs & formula_refs:
                count += 1
    return count


def _table_scores(
    table: Table,
    guesses: dict[int, TypeGuess],
    labels: dict[int, str],
    references: int,
    sheet_name: str,
) -> dict[str, float]:
    types = [guess.type for guess in guesses.values()]
    has_date = any(kind in ("date", "datetime") for kind in types)
    has_amount = any(kind in AMOUNT_TYPES for kind in types)
    has_money = "money" in types
    has_choice = any(kind in ("choice", "link") for kind in types)
    rows = len(table.data_rows())
    columns = len(guesses)
    status = [
        column
        for column, guess in guesses.items()
        if guess.type == "choice" and STATUS_HINT.search(labels.get(column, ""))
    ]
    assignee = any(ASSIGNEE_HINT.search(label) for label in labels.values())

    scores = {"register": 0.45, "ledger": 0.0, "tracker": 0.0, "referenceList": 0.0}
    if has_date and has_money:
        scores["ledger"] += 0.7
    elif has_date and has_amount:
        scores["ledger"] += 0.35  # A plain decimal could be a grade or a weight, not money.
    # A tab named for a month holds that month's entries, so it needs no date column of its own.
    if MONTH_NAME.search(sheet_name) and has_amount:
        scores["ledger"] += 0.5
    if table.total_rows and (has_money or has_amount):
        scores["ledger"] += 0.2
    if status:
        scores["tracker"] += 0.65
        if has_date:
            scores["tracker"] += 0.2
        if assignee:
            scores["tracker"] += 0.1
        # A ledger with a paid-or-not column is still a ledger: money with dates outweighs it.
        if has_money and not assignee:
            scores["tracker"] -= 0.25
    elif has_choice and assignee and has_date:
        scores["tracker"] += 0.6
    # R-3: a reference list feeds a relation, so something must point at it.
    if references and not has_date:
        if columns <= 3 and not has_money:
            scores["referenceList"] += 0.9
        elif columns <= 5:
            scores["referenceList"] += 0.55
    elif columns <= 2 and not has_date and not has_money and rows <= 60:
        scores["referenceList"] += 0.3
    return scores


def score_sheet(
    grid: Grid,
    layout: SheetLayout,
    guesses_by_table: list[dict[int, TypeGuess]],
    labels_by_table: list[dict[int, str]],
    unsupported: list[dict[str, Any]],
    references: int,
) -> KindResult:
    facts: dict[str, Any] = {
        "cells": sum(1 for cell in grid.cells.values() if not cell.is_empty),
        "tables": len(layout.tables),
    }
    if any(item["kind"] == "macro" and item.get("sheet") == grid.name for item in unsupported):
        return KindResult("notConverted", "outOfScope", 0.95, {}, facts)
    has_visuals = any(
        item["kind"] in ("chart", "pivot") and item.get("sheet") == grid.name for item in unsupported
    )
    if facts["cells"] == 0:
        if has_visuals:
            return KindResult("notConverted", "chartOrPivotOnly", 0.97, {}, facts)
        return KindResult("notConverted", "empty", 0.99, {}, facts)

    formulas = [cell for cell in grid.cells.values() if cell.formula]
    chains = _formula_chain_depth(grid)
    facts["formulas"] = len(formulas)
    facts["formulaChains"] = chains

    if not layout.tables:
        if layout.label_value_blocks and len(formulas) >= MIN_FORMULAS_FOR_MODEL:
            return KindResult("formulaModel", None, min(0.7 + 0.05 * chains, 0.92), {}, facts)
        if has_visuals:
            return KindResult("notConverted", "chartOrPivotOnly", 0.8, {}, facts)
        if layout.label_value_blocks:
            return KindResult("notConverted", "form", 0.75, {}, facts)
        return KindResult("notConverted", "outOfScope", 0.65, {}, facts)

    # Judge by the largest table: it's what the sheet is for.
    sizes = [table.rect.width * table.rect.height for table in layout.tables]
    index = sizes.index(max(sizes))
    table = layout.tables[index]
    scores = _table_scores(table, guesses_by_table[index], labels_by_table[index], references, grid.name)
    facts["largestTable"] = table.rect.a1

    # A small grid of formulas beside labels is a calculation, even when it parses as a table.
    data_cells = sum(len(grid.row_cells(row, table.rect.left, table.rect.right)) for row in table.data_rows())
    model_share = len(formulas) / max(data_cells, 1)
    if chains >= MIN_FORMULAS_FOR_MODEL and model_share >= 0.3 and table.rect.height <= 30:
        scores["formulaModel"] = 0.75 + min(chains * 0.02, 0.15)
    # A sheet of mostly totals and subtotals summarises other data: it's a report.
    if len(table.total_rows) >= 2 and len(table.total_rows) * 2 > len(table.data_rows()):
        scores["report"] = 0.8

    best = max(sorted(scores), key=lambda name: scores[name])
    top = scores[best]
    runner_up = max((value for name, value in scores.items() if name != best), default=0.0)
    confidence = min(0.99, max(0.3, 0.5 + (top - runner_up) * 0.6 + (top - 0.45) * 0.3))
    if best == "report":
        return KindResult("notConverted", "report", round(confidence, 3), scores, facts)
    return KindResult(best, None, round(confidence, 3), scores, facts)


def resolve_validation(
    validations: list[dict[str, Any]],
    column: int,
    top: int,
    bottom: int,
    grids: dict[str, Grid],
    defined: dict[str, str],
    own_sheet: str,
) -> dict[str, Any] | None:
    """The list validation covering a column, with its values and any other sheet it draws on."""
    for validation in validations:
        if validation.get("type") != "list" or not _covers(validation["ranges"], column, top, bottom):
            continue
        source = str(validation.get("formula1") or "").strip().lstrip("=")
        if source.startswith('"'):
            items = [part.strip() for part in source.strip('"').split(",") if part.strip()]
            return {"values": items}
        source = defined.get(source, source).lstrip("=")
        return _values_from_range(source, grids, own_sheet) or {"values": []}
    return None


def _covers(ranges: list[str], column: int, top: int, bottom: int) -> bool:
    for item in ranges:
        low, _, high = item.partition(":")
        high = high or low
        low_match = re.match(r"([A-Z]+)([0-9]+)", low)
        high_match = re.match(r"([A-Z]+)([0-9]+)", high)
        if not low_match or not high_match:
            continue
        in_column = column_index(low_match.group(1)) <= column <= column_index(high_match.group(1))
        overlaps = int(low_match.group(2)) <= bottom and int(high_match.group(2)) >= top
        if in_column and overlaps:
            return True
    return False


def _values_from_range(source: str, grids: dict[str, Grid], own_sheet: str) -> dict[str, Any] | None:
    sheet_name, _, reference = source.rpartition("!")
    sheet_name = sheet_name.strip("'").replace("''", "'") or own_sheet
    match = re.fullmatch(r"\$?([A-Z]+)\$?([0-9]+)(?::\$?([A-Z]+)\$?([0-9]+))?", reference)
    grid = grids.get(sheet_name)
    if match is None or grid is None:
        return None
    column = column_index(match.group(1))
    top = int(match.group(2))
    bottom = int(match.group(4) or top)
    values = [text_of(cell) for cell in grid.column_cells(column, top, bottom)]
    result: dict[str, Any] = {"values": values}
    if sheet_name != own_sheet:
        result["target"] = {"sheet": sheet_name, "column": match.group(1)}
    return result
