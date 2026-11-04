"""What one sheet's analysis leaves for the checks that look across sheets."""

from dataclasses import dataclass

from daftar_worker.analyser.regions import SheetLayout
from daftar_worker.analyser.types import TypeGuess
from daftar_worker.sheet.grid import Grid


@dataclass
class SheetView:
    grid: Grid
    layout: SheetLayout
    labels: list[dict[int, str]]
    guesses: list[dict[int, TypeGuess]]
    outcome: str
