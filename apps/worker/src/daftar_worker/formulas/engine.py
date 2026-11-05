"""Our interface to the formula engine. This is the only module that may import Formualizer.

It is pre-1.0 and its API changes between releases (D-5), so nothing else depends on its shapes.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from functools import lru_cache
from pathlib import Path
import tempfile
from typing import Any
import zipfile

import formualizer
from formualizer import EvaluationConfig, Workbook, WorkbookConfig


# Engine error kinds to what Excel shows.
ERRORS = {
    "Div": "#DIV/0!", "Na": "#N/A", "NA": "#N/A", "Name": "#NAME?", "Null": "#NULL!", "Num": "#NUM!",
    "Ref": "#REF!", "Value": "#VALUE!", "Spill": "#SPILL!", "Calc": "#CALC!", "Circ": "#CIRC!",
    "GettingData": "#GETTING_DATA",
}  # fmt: skip
MAX_EVAL_MS = 120_000


class EngineError(Exception):
    """The engine couldn't load or evaluate a workbook."""


@dataclass(frozen=True)
class EngineValue:
    """A result in engine-neutral form. `kind` is number, text, boolean, date, time, error or empty."""

    kind: str
    value: Any


def _to_value(raw: Any) -> EngineValue:
    if raw is None:
        return EngineValue("empty", None)
    if isinstance(raw, bool):
        return EngineValue("boolean", raw)
    if isinstance(raw, (int, float)):
        return EngineValue("number", raw)
    if isinstance(raw, str):
        return EngineValue("text", raw)
    if isinstance(raw, datetime):
        return EngineValue("date", raw)
    if isinstance(raw, date):
        return EngineValue("date", datetime(raw.year, raw.month, raw.day))
    if isinstance(raw, time):
        return EngineValue("time", raw)
    if isinstance(raw, dict) and raw.get("type") == "Error":
        kind = str(raw.get("kind"))
        return EngineValue("error", ERRORS.get(kind, f"#{kind.upper()}!"))
    return EngineValue("error", "#VALUE!")


def _config() -> WorkbookConfig:
    evaluation = EvaluationConfig()
    evaluation.max_eval_time_ms = MAX_EVAL_MS
    return WorkbookConfig(eval_config=evaluation)


def _pin_clock(workbook: Workbook, clock: datetime | None) -> None:
    if clock is not None:
        moment = clock if clock.tzinfo else clock.replace(tzinfo=timezone.utc)
        workbook.set_deterministic_clock(moment)


def _repacked(path: str, folder: str) -> str:
    """The same parts in a plain ZIP. The engine refuses ZIP64 entries and mismatched ZIP headers,
    which some real workbooks have and Excel and openpyxl read without complaint."""
    target = str(Path(folder) / "repacked.xlsx")
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out:
        for item in source.infolist():
            if not item.is_dir():
                out.writestr(item.filename, source.read(item))
    return target


def _open_workbook(path: str, folder: tempfile.TemporaryDirectory[str]) -> Workbook:
    try:
        return Workbook.from_path(path, config=_config())
    except OSError:
        return Workbook.from_path(_repacked(path, folder.name), config=_config())


class EngineWorkbook:
    """A whole workbook, loaded from an .xlsx and recalculated from its formulas.

    `replacements` are (sheet, row, column, formula) to use in place of what the file says.
    """

    def __init__(self, path: str, clock: datetime | None = None, replacements: Iterable[tuple[str, int, int, str]] = ()) -> None:
        # It lives as long as this object, in case the engine reads a repacked file lazily.
        self._folder = tempfile.TemporaryDirectory(prefix="daftar-engine-")
        try:
            self._workbook = _open_workbook(path, self._folder)
            _pin_clock(self._workbook, clock)
            for sheet, row, column, formula in replacements:
                self._workbook.set_formula(sheet, row, column, formula)
            self._workbook.evaluate_all()
        except Exception as error:
            raise EngineError(type(error).__name__) from error

    def value(self, sheet: str, row: int, column: int) -> EngineValue:
        try:
            return _to_value(self._workbook.get_value(sheet, row, column))
        except Exception as error:
            raise EngineError(type(error).__name__) from error


def evaluate_cells(
    cells: Iterable[tuple[str, int, int, Any, str | None]],
    targets: Sequence[tuple[str, int, int]],
    clock: datetime | None = None,
) -> list[EngineValue]:
    """Build a small model from (sheet, row, column, value, formula) and evaluate the targets.

    This is how calculators run. Values must be plain numbers, text or booleans.
    """
    workbook = Workbook()
    known: set[str] = set()
    for sheet, row, column, value, formula in cells:
        if sheet not in known:
            workbook.add_sheet(sheet)
            known.add(sheet)
        if formula is not None:
            workbook.set_formula(sheet, row, column, formula)
        elif value is not None:
            workbook.set_value(sheet, row, column, value)
    _pin_clock(workbook, clock)
    return [_to_value(workbook.evaluate_cell(sheet, row, column)) for sheet, row, column in targets]


def recalculate(data: bytes) -> bytes:
    """Fill in a workbook's formula results. It must be the last step: saving again drops them."""
    try:
        result = formualizer.recalculate_xlsx_bytes(data)
    except Exception as error:
        raise EngineError(type(error).__name__) from error
    return bytes(result["bytes"])


def parse_formula(formula: str) -> dict[str, Any]:
    """Parse to an AST of plain dicts. Raises EngineError on a formula it can't parse."""
    try:
        ast: dict[str, Any] = formualizer.parse(formula).to_dict()
    except Exception as error:
        raise EngineError(type(error).__name__) from error
    return ast


@lru_cache(maxsize=4096)
def is_supported(function: str) -> bool:
    """Whether the engine knows a function. Asking it is the only reliable way in this version."""
    workbook = Workbook()
    workbook.add_sheet("Probe")
    try:
        workbook.set_formula("Probe", 1, 1, f"={function}()")
        result = _to_value(workbook.evaluate_cell("Probe", 1, 1))
    except Exception:
        return False
    return not (result.kind == "error" and result.value == "#NAME?")
