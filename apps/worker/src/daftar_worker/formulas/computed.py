"""Find formula columns, translate them, and check each translation against stored results."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from daftar_worker.analyser.grid import Cell, Grid, a1
from daftar_worker.analyser.types import TypeGuess
from daftar_worker.formulas.engine import is_supported
from daftar_worker.formulas.evaluate import Evaluator, ExcelError, to_serial
from daftar_worker.formulas.references import relative_form
from daftar_worker.formulas.translate import Lookup, field_key, translate


COPIED_SHARE = 0.8
CLOCK_FUNCTIONS = {"TODAY", "NOW"}
MAX_LISTED_CELLS = 20
TOLERANCE = 1e-9


@dataclass
class ComputedColumn:
    column: int
    formula: str
    matching: int
    total: int
    expr: dict[str, Any] | None
    deps: list[str]
    reasons: list[str]
    functions: set[str]
    missing_functions: list[str]
    lookups: list[Lookup]
    outliers: list[str] = field(default_factory=list)
    checked: int = 0
    agreed: int = 0


def _value_type(guess: TypeGuess | None) -> str:
    if guess is None:
        return "any"
    kind = guess.result_type if guess.type == "computed" else guess.type
    return {
        "integer": "number", "decimal": "number", "money": "number", "percent": "number",
        "date": "date", "datetime": "date", "text": "text", "longtext": "text", "phone": "text",
        "email": "text", "choice": "text", "multichoice": "text", "boolean": "boolean",
    }.get(kind or "", "any")  # fmt: skip


def cell_scalar(cell: Cell | None) -> Any:
    """A cell's stored value as the evaluator sees it: dates are serial numbers."""
    if cell is None or cell.value is None:
        return None
    if cell.kind == "e":
        return ExcelError(str(cell.value))
    if cell.kind == "d":
        try:
            return to_serial(datetime.fromisoformat(str(cell.value)))
        except ValueError:
            return _time_fraction(str(cell.value))
    return cell.value


def _time_fraction(value: str) -> Any:
    try:
        hours, minutes, seconds = (float(part) for part in value.split(":"))
    except ValueError:
        return None
    return (hours * 3600 + minutes * 60 + seconds) / 86400


def results_agree(expected: Any, actual: Any) -> bool:
    if isinstance(expected, ExcelError) or isinstance(actual, ExcelError):
        return (
            isinstance(expected, ExcelError) and isinstance(actual, ExcelError) and expected.code == actual.code
        )
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        scale = max(abs(expected), abs(actual))
        return abs(expected - actual) <= TOLERANCE * scale
    return (expected or "") == (actual or "")


def find_computed(
    grid: Grid, column: int, rows: list[int], guesses: dict[int, TypeGuess], left: int, right: int, verify: bool
) -> ComputedColumn | None:
    """A column whose cells hold one formula, copied down. None if there's no such formula.

    `verify` says the stored results are Excel's, so a translation can be checked against them.
    """
    cells = [(row, grid.get(row, column)) for row in rows]
    filled = [(row, cell) for row, cell in cells if cell is not None]
    formulas = [(row, cell) for row, cell in filled if cell.formula]
    if not formulas:
        return None
    shapes = Counter(relative_form(str(cell.formula), row, column) for row, cell in formulas)
    shape, count = shapes.most_common(1)[0]
    if count < 2 or count / len(filled) < COPIED_SHARE:
        return None

    first_row, first = next((row, cell) for row, cell in formulas if relative_form(str(cell.formula), row, column) == shape)
    types = {other: _value_type(guesses.get(other)) for other in range(left, right + 1) if other != column}
    translation = translate(str(first.formula), grid.name, first_row, types)
    missing = sorted(name for name in translation.functions if not is_supported(name))
    outliers = [
        a1(row, column)
        for row, cell in filled
        if not cell.formula or relative_form(str(cell.formula), row, column) != shape
    ]
    result = ComputedColumn(
        column,
        str(first.formula),
        count,
        len(filled),
        translation.expr,
        translation.deps,
        translation.reasons,
        translation.functions,
        missing,
        translation.lookups,
        outliers,
    )
    # TODAY() stored the clock of the last save, which the snapshot doesn't hold. The file-level
    # parity check freezes that clock; here, such a column just stays unverified.
    checkable = not (translation.functions & CLOCK_FUNCTIONS)
    if verify and checkable and translation.expr is not None and not _has_lookup(translation.expr):
        _check_translation(grid, result, formulas, shape, left, right)
    return result


def _has_lookup(expr: dict[str, Any]) -> bool:
    return expr["kind"] == "related" or any(_has_lookup(arg) for arg in expr.get("args", []))


def _check_translation(
    grid: Grid,
    result: ComputedColumn,
    formulas: list[tuple[int, Cell]],
    shape: str,
    left: int,
    right: int,
) -> None:
    """Run the translation on each row against what the file stores. A disagreement sends it back.

    The rule that keeps a computed field from being silently wrong: a translation that can't
    reproduce every stored result goes to the engine, and the reason is on the finding.
    """
    assert result.expr is not None
    for row, cell in formulas:
        if relative_form(str(cell.formula), row, result.column) != shape:
            continue
        record = {field_key(column): cell_scalar(grid.get(row, column)) for column in range(left, right + 1)}
        actual = Evaluator(record).run(result.expr)
        expected = cell_scalar(cell)
        result.checked += 1
        result.agreed += results_agree(expected, actual)
    if result.agreed < result.checked:
        result.expr = None
        result.reasons.append("disagreesWithStoredResults")
