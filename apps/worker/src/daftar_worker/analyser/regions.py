"""Find table regions: cut the sheet at empty rows and columns, then classify each block's rows."""

from collections.abc import Iterable
from dataclasses import dataclass, field
import re

from daftar_worker.analyser.grid import Cell, Grid, Rect, a1_range, column_index, text_of


TOTAL_WORDS = re.compile(
    r"^\s*(?:sous[- ]?tota(?:l|ux)|s/\s?total|total\s+g[ée]n[ée]ral|grand\s+total|tota(?:l|ux)|subtotal|sum"
    r"|somme|cumul|(?:ال)?مجموع|(?:ال)?[إا]جمالي)(?:\s|:|$)",
    re.IGNORECASE,
)
AGGREGATE = re.compile(
    r"^=\s*(SUM|SUBTOTAL|AVERAGE|COUNT|COUNTA|MAX|MIN|PRODUCT)\s*\((?:\s*[0-9]+\s*,)?\s*"
    r"\$?([A-Z]{1,3})\$?([0-9]+)\s*:\s*\$?([A-Z]{1,3})\$?([0-9]+)\s*\)\s*$",
    re.IGNORECASE,
)
MAX_HEADER_ROWS = 3
MAX_TOTAL_LABEL_WORDS = 5
MIN_ROWS_ONE_COLUMN = 4
ARITHMETIC_TOLERANCE = 0.005
SPACED_RUNS = 3
TITLE_SEARCH_ROWS = 6
MIN_HEADER_CELLS = 2
MIN_LONE_HEADER_CELLS = 3
MAX_GAP_UNDER_HEADER = 3
NEW_HEADER_SHARE = 0.6
NEW_HEADER_SEARCH_ROWS = 2
MIN_GROUPED_WIDTH = 3


@dataclass
class TotalRow:
    row: int
    aggregates: list[tuple[int, str]]  # column, function
    source: str  # formula, keyword, arithmetic or afterTotal


@dataclass
class Table:
    rect: Rect
    header_rows: list[int]
    total_rows: list[TotalRow]
    title_rows: list[int]
    note_rows: list[int]
    header_confidence: float
    blank_rows: list[int] = field(default_factory=list)

    @property
    def data_top(self) -> int:
        top = (self.header_rows[-1] + 1) if self.header_rows else self.rect.top
        while top in self.blank_rows:
            top += 1
        return top

    @property
    def data_bottom(self) -> int:
        bottom = self.rect.bottom
        totals = {item.row for item in self.total_rows}
        while bottom in totals and bottom > self.data_top:
            bottom -= 1
        return bottom

    def data_rows(self) -> list[int]:
        skipped = (
            {item.row for item in self.total_rows} | set(self.note_rows) | set(self.blank_rows)
        )
        return [row for row in range(self.data_top, self.rect.bottom + 1) if row not in skipped]

    @property
    def data_range(self) -> str:
        return a1_range(self.data_top, self.rect.left, self.data_bottom, self.rect.right)


@dataclass
class SheetLayout:
    tables: list[Table] = field(default_factory=list)
    # Blocks that hold content but no table: titles, notes and label-and-value forms.
    other_blocks: list[Rect] = field(default_factory=list)
    label_value_blocks: list[Rect] = field(default_factory=list)


def _bounding(grid: Grid, rect: Rect) -> Rect | None:
    rows = [
        row
        for row in range(rect.top, rect.bottom + 1)
        if grid.filled_columns(row, rect.left, rect.right)
    ]
    if not rows:
        return None
    columns = [column for row in rows for column in grid.filled_columns(row, rect.left, rect.right)]
    return Rect(rows[0], min(columns), rows[-1], max(columns))


def _split_runs(values: Iterable[int]) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    for value in sorted(values):
        if runs and value == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], value)
        else:
            runs.append((value, value))
    return runs


def cut_blocks(grid: Grid, rect: Rect) -> list[Rect]:
    """Recursive cut at fully empty rows and columns."""
    bounded = _bounding(grid, rect)
    if bounded is None:
        return []

    # A title over side-by-side tables would hide the gap between them, so ignore the top rows that
    # hold a single value (or one merged span) when looking for an empty column.
    first_wide = bounded.top
    while first_wide < bounded.bottom and _is_lone_row(grid, first_wide, bounded):
        first_wide += 1
    used_columns = {
        column
        for row in range(first_wide, bounded.bottom + 1)
        for column in grid.filled_columns(row, bounded.left, bounded.right)
    }
    column_runs = _join_spacer_runs(grid, _split_runs(used_columns), first_wide, bounded.bottom)
    if len(column_runs) > 1:
        blocks: list[Rect] = []
        if first_wide > bounded.top:
            blocks += cut_blocks(
                grid, Rect(bounded.top, bounded.left, first_wide - 1, bounded.right)
            )
        for low, high in column_runs:
            blocks += cut_blocks(grid, Rect(first_wide, low, bounded.bottom, high))
        return blocks

    used_rows = [
        row
        for row in range(bounded.top, bounded.bottom + 1)
        if grid.filled_columns(row, bounded.left, bounded.right)
    ]
    row_runs = _split_runs(used_rows)
    if len(row_runs) > 1:
        blocks = []
        for low, high in row_runs:
            blocks += cut_blocks(grid, Rect(low, bounded.left, high, bounded.right))
        return blocks
    return [bounded]


def _rows_of_run(grid: Grid, run: tuple[int, int], top: int, bottom: int) -> set[int]:
    return {row for row in range(top, bottom + 1) if grid.filled_columns(row, run[0], run[1])}


def _join_spacer_runs(
    grid: Grid, runs: list[tuple[int, int]], top: int, bottom: int
) -> list[tuple[int, int]]:
    """An empty column isn't a boundary when what follows it can't stand alone.

    Thin columns laid out with spacers between them are one table. So is a block of figures on the same
    rows that has no labels of its own: its rows only mean something through the block to its left.
    """
    if len(runs) < 2:
        return runs
    rows = [_rows_of_run(grid, run, top, bottom) for run in runs]
    if len(runs) >= SPACED_RUNS and all(high == low for low, high in runs[1:]):
        if all(_shared(rows[0], other) >= 0.8 for other in rows[1:]):
            return [(runs[0][0], runs[-1][1])]
    joined = [runs[0]]
    for run, its_rows, previous_rows in zip(runs[1:], rows[1:], rows, strict=False):
        gap = run[0] - joined[-1][1] - 1
        if (
            gap == 1
            and _overlap(previous_rows, its_rows) >= 0.75
            and not _has_own_labels(grid, run, top, bottom)
        ):
            joined[-1] = (joined[-1][0], run[1])
        else:
            joined.append(run)
    return joined


def _overlap(first: set[int], second: set[int]) -> float:
    return len(first & second) / max(1, len(first | second))


def _shared(first: set[int], second: set[int]) -> float:
    return len(first & second) / max(1, min(len(first), len(second)))


def _has_own_labels(grid: Grid, run: tuple[int, int], top: int, bottom: int) -> bool:
    """Whether the run's first column holds text or dates under its first row, as a key column does."""
    cells = grid.column_cells(run[0], top + 1, bottom)
    return (
        bool(cells) and sum(cell.is_text or cell.kind == "d" for cell in cells) / len(cells) > 0.5
    )


def _is_lone_row(grid: Grid, row: int, rect: Rect) -> bool:
    """One value in the row, or one merged span. That's how titles and notes look."""
    cells = grid.row_cells(row, rect.left, rect.right)
    return len(cells) <= 1 and rect.width > 1


def _is_header_like(cells: list[Cell]) -> bool:
    """All text. A formula that builds a label ("Test 1") counts, since its result is text."""
    if not cells:
        return False
    return all(
        cell.kind == "s" and cell.value is not None and len(text_of(cell)) <= 80 for cell in cells
    )


def _is_period_header(cells: list[Cell], following: list[Cell]) -> bool:
    """A label, then a rising series across the columns: Année, 2000, 2001 or Agent, 1, 2, 3.

    The series must rise, and the next row must start with its own label, or this would match
    ordinary records that begin with a name.
    """
    if len(cells) < 3 or not cells[0].is_text or not following or not following[0].is_text:
        return False
    series = cells[1:]
    if all(cell.kind == "d" for cell in series):
        values = [str(cell.value) for cell in series]
        return values == sorted(set(values))
    if not all(cell.is_number and float(cell.value).is_integer() for cell in series):
        return False
    numbers = [int(cell.value) for cell in series]
    rising = all(later > earlier for earlier, later in zip(numbers, numbers[1:], strict=False))
    steps_by_one = all(
        later - earlier == 1 for earlier, later in zip(numbers, numbers[1:], strict=False)
    )
    return rising and (steps_by_one or all(1900 <= number <= 2100 for number in numbers))


def _is_date_header(cells: list[Cell]) -> bool:
    """A row of rising dates across the columns, with figures under it and no label before it."""
    if len(cells) < 3 or not all(cell.kind == "d" for cell in cells):
        return False
    values = [str(cell.value) for cell in cells]
    return values == sorted(set(values))


def _is_data_like(cells: list[Cell]) -> bool:
    return any(cell.is_number or cell.kind in ("d", "b") or cell.formula for cell in cells)


def _style_key(cells: list[Cell]) -> tuple[bool, bool]:
    return (
        bool(cells) and all(cell.style.get("bold") for cell in cells),
        bool(cells) and all("fill" in cell.style for cell in cells),
    )


def _find_headers(grid: Grid, rect: Rect, top: int, bottom: int) -> tuple[list[int], float]:
    first = grid.row_cells(top, rect.left, rect.right)
    if _is_period_header(first, grid.row_cells(top + 1, rect.left, rect.right)):
        return [top], 0.8
    if _is_date_header(first):
        return [top], 0.7
    if not _is_header_like(first):
        return [], 0.0
    # An all-text sheet could have data in its first row. Style and repetition tell them apart.
    values = [text_of(cell).casefold() for cell in first]
    below = _column_profile_differs(grid, rect, top, bottom)
    styled = any(_style_key(first))
    repeated = len(set(values)) < len(values)
    if (
        repeated
        and not styled
        and not below
        and not grid.spanning_merge(top, rect.left, rect.right)
    ):
        return [], 0.0

    rows = [top]
    while len(rows) < MAX_HEADER_ROWS and rows[-1] < bottom - 1:
        current = rows[-1]
        following = current + 1
        next_cells = grid.row_cells(following, rect.left, rect.right)
        if not _is_header_like(next_cells):
            break
        current_cells = grid.row_cells(current, rect.left, rect.right)
        has_gaps = len(grid.filled_columns(current, rect.left, rect.right)) > len(current_cells)
        partial = len(current_cells) < rect.width
        spans = grid.spanning_merge(current, rect.left, rect.right)
        third = grid.row_cells(following + 1, rect.left, rect.right)
        same_style = any(_style_key(current_cells)) and _style_key(current_cells) == _style_key(
            next_cells
        )
        # The row below the next must look unlike it, or we'd swallow text rows as headers.
        if (spans or has_gaps or partial or same_style) and (
            _style_key(next_cells) != _style_key(third) or _is_data_like(third) or spans
        ):
            rows.append(following)
        else:
            break

    # Plain text over plain text with no styling could just as well be the first record.
    confidence = 0.5
    if styled:
        confidence += 0.25
    if below:
        confidence += 0.25
    if len(rows) > 1:
        confidence = min(confidence, 0.8)
    return rows, min(confidence, 0.95)


def _column_profile_differs(grid: Grid, rect: Rect, top: int, bottom: int) -> bool:
    """Whether a text first row sits on columns that hold numbers or dates below it."""
    for column in range(rect.left, rect.right + 1):
        below = grid.column_cells(column, top + 1, bottom)
        if below and sum(1 for cell in below if not cell.is_text) / len(below) > 0.5:
            return True
    return False


def _looks_like_label_value(grid: Grid, rect: Rect, top: int, bottom: int) -> bool:
    """A form or input block: unique text labels on the left, assorted values on the right."""
    if rect.width > 3 or bottom - top < 1:
        return False
    labels = grid.column_cells(rect.left, top, bottom)
    if len(labels) < (bottom - top + 1) * 0.8 or not all(cell.is_text for cell in labels):
        return False
    if len({text_of(cell).casefold() for cell in labels}) != len(labels):
        return False
    if any(text_of(cell).rstrip().endswith(":") for cell in labels):
        return True
    # A top row that's all text across the block is a header, so this is a table.
    top_row = grid.row_cells(top, rect.left, rect.right)
    if len(top_row) == rect.width and _is_header_like(top_row):
        return False
    values = [
        cell
        for column in range(rect.left + 1, rect.right + 1)
        for cell in grid.column_cells(column, top, bottom)
    ]
    if not values:
        return True
    has_formula = any(cell.formula for cell in values)
    kinds = {cell.kind for cell in values}
    return has_formula and not _is_copied_column(values) or len(kinds) > 1


def _is_copied_column(values: list[Cell]) -> bool:
    """Whether every value is a formula, as in a column of a table rather than a calculation."""
    return all(cell.formula for cell in values) and len(values) >= 3


def _aggregate_of(cell: Cell) -> str | None:
    """The aggregate a cell's formula applies to the same column above it, if any."""
    if not cell.formula:
        return None
    match = AGGREGATE.match(cell.formula)
    if match is None or match.group(2).upper() != match.group(4).upper():
        return None
    in_same_column = column_index(match.group(2).upper()) == cell.column
    if not in_same_column or int(match.group(5)) >= cell.row:
        return None  # SUM(B$2:B5) on row 5 is a running total, a data column.
    function = match.group(1).upper()
    return "sum" if function == "SUBTOTAL" else function.lower()


def _find_total_rows(grid: Grid, rect: Rect, data_top: int, bottom: int) -> list[TotalRow]:
    found: list[TotalRow] = []
    for row in range(data_top, bottom + 1):
        cells = grid.row_cells(row, rect.left, rect.right)
        if not cells:
            continue
        aggregates = [
            (cell.column, function)
            for cell in cells
            if (function := _aggregate_of(cell)) is not None
        ]
        first_text = next((text_of(cell) for cell in cells if cell.is_text), "")
        has_word = (
            bool(TOTAL_WORDS.match(first_text)) and len(first_text.split()) <= MAX_TOTAL_LABEL_WORDS
        )
        if aggregates:
            found.append(TotalRow(row, aggregates, "formula"))
        elif has_word and any(cell.is_number or cell.formula for cell in cells):
            numeric = [(cell.column, "sum") for cell in cells if cell.is_number or cell.formula]
            found.append(TotalRow(row, numeric, "keyword"))

    # Values only: the last row equals the sum of the rows above it, with its label cell empty.
    if not any(item.row == bottom for item in found):
        arithmetic = _arithmetic_total(grid, rect, data_top, bottom, found)
        if arithmetic:
            found.append(TotalRow(bottom, arithmetic, "arithmetic"))
    found.sort(key=lambda item: item.row)
    return found + _rows_after_total(grid, rect, bottom, found)


def _rows_after_total(
    grid: Grid, rect: Rect, bottom: int, totals: list[TotalRow]
) -> list[TotalRow]:
    """Tax and grand-total lines under a total: sparse rows that leave the first column empty."""
    if not totals:
        return []
    extra: list[TotalRow] = []
    for row in range(totals[-1].row + 1, bottom + 1):
        cells = grid.row_cells(row, rect.left, rect.right)
        figures = [cell for cell in cells if cell.is_number or cell.formula]
        if not figures or grid.get(row, rect.left) is not None:
            break
        extra.append(TotalRow(row, [], "afterTotal"))
    return extra


def _arithmetic_total(
    grid: Grid, rect: Rect, data_top: int, bottom: int, known: list[TotalRow]
) -> list[tuple[int, str]]:
    cells = grid.row_cells(bottom, rect.left, rect.right)
    numbers = [cell for cell in cells if cell.is_number and not cell.formula]
    # A real record fills its row; a pasted total leaves the identifying columns empty.
    if not numbers or len(cells) == rect.width or bottom - data_top < 2:
        return []
    excluded = {item.row for item in known}
    matched = []
    for cell in numbers:
        above = [
            other.value
            for other in grid.column_cells(cell.column, data_top, bottom - 1)
            if other.is_number and other.row not in excluded
        ]
        if len(above) < 2:
            return []
        if abs(sum(above) - cell.value) <= ARITHMETIC_TOLERANCE:
            matched.append((cell.column, "sum"))
    return matched if len(matched) == len(numbers) else []


def _trim_edges(grid: Grid, rect: Rect) -> tuple[int, int, list[int], list[int]]:
    """Set aside lone title rows above the table and lone note rows below it."""
    top, bottom = rect.top, rect.bottom
    titles: list[int] = []
    while top < bottom and _is_lone_title(grid, top, rect):
        titles.append(top)
        top += 1
    header = _strong_header_row(grid, rect, top)
    if header is not None:
        titles.extend(range(top, header))
        top = header
    notes: list[int] = []
    while bottom > top and _is_lone_text(grid, bottom, rect):
        notes.append(bottom)
        bottom -= 1
    return top, bottom, titles, sorted(notes)


def _is_header_row(cells: list[Cell]) -> bool:
    """Labels, dates or both: a header often mixes a few names with a run of months."""
    text = [cell for cell in cells if cell.kind == "s"]
    dates = [cell for cell in cells if cell.kind == "d"]
    return _is_date_header(cells) or (
        bool(cells) and len(text) + len(dates) == len(cells) and _is_header_like(text)
    )


def _strong_header_row(grid: Grid, rect: Rect, top: int) -> int | None:
    """A full row of labels under a few sparse rows: what's above it is a title block, not the table."""
    counts = {
        row: len(grid.row_cells(row, rect.left, rect.right)) for row in range(top, rect.bottom + 1)
    }
    for row in range(top + 1, min(top + TITLE_SEARCH_ROWS, rect.bottom) + 1):
        cells = grid.row_cells(row, rect.left, rect.right)
        above = [counts[other] for other in range(top, row)]
        if (
            len(cells) >= MIN_HEADER_CELLS
            and _is_header_row(cells)
            and len(cells) >= 2 * max(above)
            and len(cells) >= rect.width * 0.5
        ):
            return row
    return None


def _is_lone_text(grid: Grid, row: int, rect: Rect) -> bool:
    cells = grid.row_cells(row, rect.left, rect.right)
    if rect.width < 2 or len(cells) > 1:
        return False
    if not cells:
        return True
    return cells[0].is_text


def _is_lone_title(grid: Grid, row: int, rect: Rect) -> bool:
    """A lone text, or a lone date such as the report date on top of a wide table."""
    if _is_lone_text(grid, row, rect):
        return True
    cells = grid.row_cells(row, rect.left, rect.right)
    return len(cells) == 1 and cells[0].kind == "d" and rect.width >= 3


def _group_label_rows(grid: Grid, rect: Rect, top: int, bottom: int, totals: set[int]) -> list[int]:
    """A lone label inside a table, heading the records under it. It isn't a record itself."""
    if rect.width < MIN_GROUPED_WIDTH:
        return []
    found = []
    for row in range(top, bottom):
        cells = grid.row_cells(row, rect.left, rect.right)
        if row in totals or len(cells) != 1 or not cells[0].is_text:
            continue
        following = next(
            (
                cells
                for other in range(row + 1, bottom + 1)
                if (cells := grid.row_cells(other, rect.left, rect.right))
            ),
            [],
        )
        if len(following) >= 2:
            found.append(row)
    return found


def analyse_block(grid: Grid, rect: Rect, layout: SheetLayout) -> None:
    top, bottom, titles, notes = _trim_edges(grid, rect)
    height = bottom - top + 1
    columns_used = {
        column
        for row in range(top, bottom + 1)
        for column in grid.filled_columns(row, rect.left, rect.right)
    }
    if height < 2 or (len(columns_used) < 2 and height < MIN_ROWS_ONE_COLUMN):
        layout.other_blocks.append(rect)
        return
    content = Rect(top, min(columns_used), bottom, max(columns_used))
    if _looks_like_label_value(grid, content, top, bottom):
        layout.label_value_blocks.append(content)
        return
    headers, confidence = _find_headers(grid, content, top, bottom)
    data_top = headers[-1] + 1 if headers else top
    # A lone column with no title is a scrap of working figures, not a table.
    if data_top > bottom or (not headers and len(columns_used) == 1):
        layout.other_blocks.append(rect)
        return
    totals = _find_total_rows(grid, content, data_top, bottom)
    blank = [
        row
        for row in range(data_top, bottom + 1)
        if not grid.filled_columns(row, content.left, content.right)
    ]
    groups = _group_label_rows(grid, content, data_top, bottom, {item.row for item in totals})
    notes = sorted({*notes, *groups})
    layout.tables.append(Table(content, headers, totals, titles, notes, confidence, blank))


def _continues(grid: Grid, upper: Table, lower: Rect) -> bool:
    """A blank row inside a table: the block below has the same columns and no header of its own."""
    if (lower.left, lower.right) != (upper.rect.left, upper.rect.right):
        return False
    if lower.top - upper.rect.bottom > 2 or upper.note_rows:
        return False
    first = grid.row_cells(lower.top, lower.left, lower.right)
    if _is_header_like(first) and any(_style_key(first)):
        return False
    for column in range(lower.left, lower.right + 1):
        above = grid.get(upper.rect.bottom, column)
        below = grid.get(lower.top, column)
        if above is not None and below is not None and above.kind != below.kind:
            return False
    return not (
        _is_header_like(first) and _column_profile_differs(grid, lower, lower.top, lower.bottom)
    )


def _anchor_row(grid: Grid, block: Rect) -> int | None:
    """The row of a block that heads a table, when it's clear enough to carry on across blank rows."""
    top = block.top
    while top < block.bottom and _is_lone_title(grid, top, block):
        top += 1
    row = _strong_header_row(grid, block, top) or top
    cells = grid.row_cells(row, block.left, block.right)
    if len(cells) < MIN_HEADER_CELLS or not _is_header_row(cells) or len(cells) < block.width * 0.5:
        return None
    styled = any(_style_key(cells))
    alone = all(
        _is_header_row(grid.row_cells(other, block.left, block.right))
        for other in range(row, block.bottom + 1)
    )
    figures_below = _column_profile_differs(grid, block, row, block.bottom)
    # Two plain labels on a row, with nothing under them, are as likely a form as a header.
    alone_is_enough = alone and len(cells) >= MIN_LONE_HEADER_CELLS
    return row if styled or alone_is_enough or figures_below else None


def _opens_new_table(grid: Grid, block: Rect, anchor_cells: list[Cell], span: Rect) -> bool:
    """A row of labels as wide as the anchor's, or repeating it, starts a table of its own."""
    return any(
        _row_opens_table(grid, block, row, anchor_cells, span)
        for row in range(block.top, min(block.top + NEW_HEADER_SEARCH_ROWS, block.bottom + 1))
    )


def _row_opens_table(
    grid: Grid, block: Rect, row: int, anchor_cells: list[Cell], span: Rect
) -> bool:
    cells = grid.row_cells(row, span.left, span.right)
    if not _is_header_row(cells) or len(cells) < MIN_HEADER_CELLS:
        return False
    if len(cells) < len(anchor_cells) * NEW_HEADER_SHARE:
        return False
    if _is_date_header(cells):
        return True
    anchor_words = {text_of(cell).casefold() for cell in anchor_cells}
    words = {text_of(cell).casefold() for cell in cells}
    repeats = len(anchor_words & words) >= len(words) * 0.5
    styled_like_anchor = any(_style_key(anchor_cells)) and _style_key(anchor_cells) == _style_key(
        cells
    )
    return (
        repeats
        or styled_like_anchor
        or (block.bottom > row and _column_profile_differs(grid, block, row, block.bottom))
    )


def _holds_records(grid: Grid, block: Rect) -> bool:
    """More than a lone label, which only belongs to a table if records follow it."""
    cells = [
        cell
        for row in range(block.top, block.bottom + 1)
        for cell in grid.row_cells(row, block.left, block.right)
    ]
    if any(not cell.is_text for cell in cells):
        return True
    return block.height >= 2 and block.width >= 2


def _sits_under(block: Rect, left: int, right: int) -> bool:
    """Mostly under the header's columns. Row labels may stick out to its left, nothing to its right."""
    shared = min(block.right, right) - max(block.left, left) + 1
    return shared >= block.width * 0.7 and block.right <= right + 1


def _filled_width(grid: Grid, block: Rect) -> int:
    return len(
        {
            column
            for row in range(block.top, block.bottom + 1)
            for column in grid.filled_columns(row, block.left, block.right)
        }
    )


def _inside(inner: Rect, outer: Rect) -> bool:
    return (
        outer.top <= inner.top
        and inner.bottom <= outer.bottom
        and outer.left <= inner.left
        and inner.right <= outer.right
    )


def _join_under_headers(grid: Grid, blocks: list[Rect]) -> list[Rect]:
    """Blocks under one header belong to it, across blank rows and group labels, until a new header.

    People leave blank rows between groups of records and between a header and its first row. Without
    this each group would become a table with no header.
    """
    remaining = sorted(blocks, key=lambda item: (item.top, item.left))
    joined: list[Rect] = []
    while remaining:
        current = remaining.pop(0)
        anchor = _anchor_row(grid, current)
        if anchor is not None:
            anchor_cells = grid.row_cells(anchor, current.left, current.right)
            left = min(cell.column for cell in anchor_cells)
            right = max(cell.column for cell in anchor_cells)
            span = Rect(anchor, left, anchor, right)
            pending: list[Rect] = []
            taken: list[Rect] = []
            bottom = current.bottom
            for block in remaining:
                if block.top - bottom - 1 > MAX_GAP_UNDER_HEADER:
                    if block.top > bottom:
                        # Sorted by top, so nothing later is closer.
                        break
                    continue
                if block.top <= bottom:
                    continue
                if not _sits_under(block, left, right):
                    break
                if (
                    len(anchor_cells) >= 5
                    and _filled_width(grid, block) < len(anchor_cells) * 0.4
                    and _holds_records(grid, block)
                    and block.height > 1
                    and block.width <= 2
                ):
                    break
                if _opens_new_table(grid, block, anchor_cells, span):
                    break
                pending.append(block)
                if _holds_records(grid, block):
                    taken.extend(pending)
                    pending = []
                bottom = block.bottom
            if taken:
                last = max(item.bottom for item in taken)
                union_left = min([current.left, *[item.left for item in taken]])
                union_right = max([current.right, *[item.right for item in taken]])
                current = Rect(current.top, union_left, last, union_right)
                remaining = [
                    item for item in remaining if item not in taken and not _inside(item, current)
                ]
        joined.append(current)
    return joined


def _set_aside_scraps(grid: Grid, layout: SheetLayout) -> None:
    """Thin blocks of plain text beside a real table are notes and labels, not tables of their own."""
    if not layout.tables:
        return
    widest = max(table.rect.width for table in layout.tables)
    kept = []
    for table in layout.tables:
        cells = [
            cell
            for row in range(table.rect.top, table.rect.bottom + 1)
            for cell in grid.row_cells(row, table.rect.left, table.rect.right)
        ]
        header_cells = grid.row_cells(table.rect.top, table.rect.left, table.rect.right)
        rows_bold = all(
            any(_style_key(grid.row_cells(row, table.rect.left, table.rect.right)))
            for row in range(table.rect.top, table.rect.bottom + 1)
        )
        plain = all(cell.is_text for cell in cells) and (
            not any(_style_key(header_cells)) or rows_bold
        )
        tiny_pair = table.rect.width <= 2 and table.rect.height <= 2
        if widest >= 2 * table.rect.width + 1 and (
            (table.rect.width <= 2 and plain and table.rect.height <= 8) or tiny_pair
        ):
            layout.other_blocks.append(table.rect)
        else:
            kept.append(table)
    layout.tables = kept


def detect_layout(grid: Grid) -> SheetLayout:
    layout = SheetLayout()
    rows = [row for row, columns in grid.occupied.items() if columns]
    if not rows:
        return layout
    columns = [column for row in rows for column in grid.occupied[row]]
    blocks = _join_under_headers(
        grid, cut_blocks(grid, Rect(min(rows), min(columns), max(rows), max(columns)))
    )
    blocks.sort(key=lambda item: (item.left, item.top))
    merged: list[Rect] = []
    for block in blocks:
        if merged and merged[-1].left == block.left and merged[-1].right == block.right:
            probe = SheetLayout()
            analyse_block(grid, merged[-1], probe)
            if probe.tables and _continues(grid, probe.tables[0], block):
                merged[-1] = Rect(merged[-1].top, block.left, block.bottom, block.right)
                continue
        merged.append(block)
    for block in merged:
        analyse_block(grid, block, layout)
    _set_aside_scraps(grid, layout)
    layout.tables.sort(key=lambda table: (table.rect.top, table.rect.left))
    return layout


def flatten_headers(grid: Grid, table: Table) -> dict[int, str]:
    """One label per column. A merged parent carries across its span, joined with " / "."""
    labels: dict[int, list[str]] = {}
    for row in table.header_rows:
        carried: str | None = None
        carried_until = -1
        for column in range(table.rect.left, table.rect.right + 1):
            cell = grid.get(row, column)
            if cell is not None:
                span = grid.merge_spans.get((row, column))
                carried = text_of(cell).removesuffix("T00:00:00")
                carried_until = span[1] if span else column
                labels.setdefault(column, []).append(carried)
            elif column <= carried_until and carried:
                labels.setdefault(column, []).append(carried)
    return {column: " / ".join(_dedupe(parts)) for column, parts in labels.items()}


def _dedupe(parts: list[str]) -> list[str]:
    return [part for index, part in enumerate(parts) if index == 0 or part != parts[index - 1]]


__all__ = ["SheetLayout", "Table", "TotalRow", "detect_layout", "flatten_headers"]
