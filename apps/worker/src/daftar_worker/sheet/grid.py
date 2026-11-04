"""A sheet from a C-1 snapshot as a grid that the analyser can query."""

from collections import defaultdict
from dataclasses import dataclass
import re
from typing import Any

from openpyxl.utils import column_index_from_string, get_column_letter, range_boundaries


REF = re.compile(r"^([A-Z]+)([0-9]+)$")


@dataclass(frozen=True)
class Cell:
    row: int
    column: int
    value: Any
    kind: str  # n, s, b, d or e
    formula: str | None
    number_format: str | None
    style: dict[str, Any]

    @property
    def is_empty(self) -> bool:
        return self.value is None and self.formula is None

    @property
    def is_text(self) -> bool:
        return self.kind == "s" and self.value is not None and self.formula is None

    @property
    def is_number(self) -> bool:
        return self.kind == "n" and self.value is not None


def a1(row: int, column: int) -> str:
    return f"{get_column_letter(column)}{row}"


def a1_range(top: int, left: int, bottom: int, right: int) -> str:
    return f"{a1(top, left)}:{a1(bottom, right)}"


def column_index(letter: str) -> int:
    return int(column_index_from_string(letter))


@dataclass(frozen=True)
class Rect:
    top: int
    left: int
    bottom: int
    right: int

    @property
    def width(self) -> int:
        return self.right - self.left + 1

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1

    @property
    def a1(self) -> str:
        return a1_range(self.top, self.left, self.bottom, self.right)


class Grid:
    def __init__(self, sheet: dict[str, Any]) -> None:
        self.name: str = sheet["name"]
        self.index: int = sheet["index"]
        self.state: str = sheet["state"]
        self.sheet = sheet
        self.cells: dict[tuple[int, int], Cell] = {}
        for raw in sheet["cells"]:
            match = REF.match(raw["ref"])
            if match is None:
                continue
            row, column = int(match.group(2)), column_index(match.group(1))
            cell = Cell(
                row,
                column,
                raw.get("v"),
                raw["t"],
                raw.get("f"),
                raw.get("fmt"),
                raw.get("style") or {},
            )
            self.cells[(row, column)] = cell
        # A merged range counts as filled across its span, if its first cell holds something.
        self.merge_spans: dict[tuple[int, int], tuple[int, int]] = {}
        self.occupied: dict[int, set[int]] = defaultdict(set)
        for (row, column), cell in self.cells.items():
            if not cell.is_empty:
                self.occupied[row].add(column)
        for merge in sheet["merges"]:
            left, top, right, bottom = (int(part) for part in range_boundaries(merge))
            first = self.cells.get((top, left))
            if first is None or first.is_empty:
                continue
            self.merge_spans[(top, left)] = (bottom, right)
            for row in range(top, bottom + 1):
                self.occupied[row].update(range(left, right + 1))
        self.hidden_columns = _expand_columns(sheet.get("hiddenColumns", []))

    def get(self, row: int, column: int) -> Cell | None:
        cell = self.cells.get((row, column))
        return None if cell is None or cell.is_empty else cell

    def filled_columns(self, row: int, left: int, right: int) -> list[int]:
        return sorted(column for column in self.occupied.get(row, ()) if left <= column <= right)

    def row_cells(self, row: int, left: int, right: int) -> list[Cell]:
        found = (self.get(row, column) for column in range(left, right + 1))
        return [cell for cell in found if cell is not None]

    def column_cells(self, column: int, top: int, bottom: int) -> list[Cell]:
        found = (self.get(row, column) for row in range(top, bottom + 1))
        return [cell for cell in found if cell is not None]

    def spanning_merge(self, row: int, left: int, right: int) -> bool:
        """Whether a merge starting on this row spans more than one column of the range."""
        return any(
            merge_row == row and left <= column <= right and span[1] > column
            for (merge_row, column), span in self.merge_spans.items()
        )


def _expand_columns(ranges: list[str]) -> set[int]:
    hidden: set[int] = set()
    for item in ranges:
        low, high = item.split(":")
        hidden.update(range(column_index(low), column_index(high) + 1))
    return hidden


def text_of(cell: Cell | None) -> str:
    return " ".join(str(cell.value).split()) if cell is not None and cell.value is not None else ""
