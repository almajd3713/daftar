"""Find a formula model's inputs and outputs (R-9), and everything needed to run it."""

from dataclasses import dataclass, field
import re
from typing import Any

from daftar_worker.formulas.references import clean_sheet, parse_reference
from daftar_worker.sheet.grid import Cell, Grid, a1, text_of


MAX_MODEL_CELLS = 5000
MAX_RANGE_CELLS = 2000
RANGE_TEXT = re.compile(
    r"(?:(?P<sheet>'(?:[^']|'')+'|[A-Za-z_À-ɏ؀-ۿ][\w.À-ɏ؀-ۿ]*)!)?"
    r"(?<![\w.])\$?[A-Z]{1,3}\$?[1-9][0-9]*(?::\$?[A-Z]{1,3}\$?[1-9][0-9]*)?(?![\w(])"
)
STRING = re.compile(r'"(?:[^"]|"")*"')


@dataclass
class Port:
    sheet: str
    row: int
    column: int
    label: str
    kind: str
    value: Any


@dataclass
class Model:
    inputs: list[Port] = field(default_factory=list)
    outputs: list[Port] = field(default_factory=list)
    cells: list[tuple[str, int, int, Any, str | None]] = field(default_factory=list)


def cells_read_by(formula: str, own_sheet: str) -> set[tuple[str, int, int]]:
    """Every cell a formula reads. Ranges are expanded, up to a limit."""
    found: set[tuple[str, int, int]] = set()
    for match in RANGE_TEXT.finditer(STRING.sub('""', formula)):
        reference = parse_reference(match.group(0))
        if reference is None:
            continue
        sheet = clean_sheet(reference.sheet) or own_sheet
        size = (reference.bottom - reference.top + 1) * (reference.right - reference.left + 1)
        if size > MAX_RANGE_CELLS:
            continue
        for row in range(reference.top, reference.bottom + 1):
            for column in range(reference.left, reference.right + 1):
                found.add((sheet, row, column))
    return found


def _label(grid: Grid, cell: Cell) -> str:
    """The text just left of a cell, or just above it. Calculators are laid out that way."""
    for column in range(cell.column - 1, max(cell.column - 4, 0), -1):
        neighbour = grid.get(cell.row, column)
        if neighbour is not None:
            if neighbour.is_text:
                return text_of(neighbour)
            break
    above = grid.get(cell.row - 1, cell.column)
    return text_of(above) if above is not None and above.is_text else ""


def _kind_of(cell: Cell) -> str:
    if cell.kind == "d":
        return "date"
    if cell.kind == "b":
        return "boolean"
    if cell.kind == "s":
        return "text"
    return "percent" if cell.number_format and "%" in cell.number_format else "decimal"


def find_model(grid: Grid, grids: dict[str, Grid]) -> Model | None:
    """Trace back from the formulas nothing else reads. None if the model is too large."""
    formulas = {(grid.name, row, column): cell for (row, column), cell in grid.cells.items() if cell.formula}
    if not formulas:
        return None
    reads = {key: cells_read_by(str(cell.formula), grid.name) for key, cell in formulas.items()}
    read_by_any = {key for targets in reads.values() for key in targets}
    outputs = [key for key in formulas if key not in read_by_any]
    if not outputs:
        return None

    seen: set[tuple[str, int, int]] = set()
    pending = list(outputs)
    inputs: list[tuple[str, int, int]] = []
    while pending:
        key = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        if len(seen) > MAX_MODEL_CELLS:
            return None
        owner = grids.get(key[0])
        cell = owner.get(key[1], key[2]) if owner else None
        if cell is None:
            continue
        if cell.formula:
            pending.extend(cells_read_by(str(cell.formula), key[0]))
        elif key[0] == grid.name:
            inputs.append(key)

    model = Model()
    for sheet, row, column in sorted(seen):
        owner = grids.get(sheet)
        cell = owner.get(row, column) if owner else None
        if cell is not None:
            model.cells.append((sheet, row, column, cell.value, cell.formula))
    for key in sorted(inputs):
        cell = grid.get(key[1], key[2])
        assert cell is not None
        model.inputs.append(Port(*key, _label(grid, cell), _kind_of(cell), cell.value))
    for key in sorted(outputs):
        cell = grid.get(key[1], key[2])
        assert cell is not None
        model.outputs.append(Port(*key, _label(grid, cell), _kind_of(cell), cell.value))
    return model if model.inputs else None


def port_key(prefix: str, port: Port) -> str:
    return f"{prefix}_{a1(port.row, port.column).lower()}"

