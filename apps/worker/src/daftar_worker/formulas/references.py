"""Read cell references out of formula text, and normalise them so copied formulas compare equal."""

from dataclasses import dataclass
import re

from daftar_worker.sheet.grid import column_index


# A string, a quoted sheet name, an unquoted sheet name, or a cell reference, whichever comes first.
TOKEN = re.compile(
    r'"(?:[^"]|"")*"'
    r"|(?P<quoted>'(?:[^']|'')+'!)"
    r"|(?P<plain>[A-Za-z_À-ɏ؀-ۿ][\w.À-ɏ؀-ۿ]*!)"
    r"|(?<![\w.\]])(?P<col>\$?[A-Z]{1,3})(?P<row>\$?[1-9][0-9]*)(?![\w(.\[])"
)
RANGE = re.compile(r"^(?:(?P<sheet>'(?:[^']|'')+'|[^!]+)!)?\$?(?P<c1>[A-Z]{1,3})\$?(?P<r1>[0-9]+)(?::\$?(?P<c2>[A-Z]{1,3})\$?(?P<r2>[0-9]+))?$")
WHOLE_COLUMN = re.compile(r"^(?:(?P<sheet>'(?:[^']|'')+'|[^!]+)!)?\$?(?P<c1>[A-Z]{1,3}):\$?(?P<c2>[A-Z]{1,3})$")


def relative_form(formula: str, row: int, column: int) -> str:
    """R1C1-style text: the same for every cell a formula was copied to."""

    def replace(match: re.Match[str]) -> str:
        if match.group("col") is None:
            return match.group(0)
        letters, number = match.group("col"), match.group("row")
        col_part = letters if letters.startswith("$") else f"C[{column_index(letters) - column}]"
        row_part = number if number.startswith("$") else f"R[{int(number) - row}]"
        return f"{row_part}{col_part}"

    return TOKEN.sub(replace, formula)


@dataclass(frozen=True)
class Reference:
    sheet: str | None
    left: int
    top: int
    right: int
    bottom: int


def clean_sheet(name: str | None) -> str | None:
    if name is None:
        return None
    return name[1:-1].replace("''", "'") if name.startswith("'") else name


def parse_reference(text: str) -> Reference | None:
    """A1 or A1:B2 with an optional sheet. None for whole columns, tables and names."""
    match = RANGE.match(text)
    if match is None:
        return None
    left, top = column_index(match.group("c1")), int(match.group("r1"))
    right = column_index(match.group("c2")) if match.group("c2") else left
    bottom = int(match.group("r2")) if match.group("r2") else top
    return Reference(clean_sheet(match.group("sheet")), left, top, right, bottom)


def parse_columns(text: str) -> tuple[str | None, int, int] | None:
    """Sheet!A:B as (sheet, first column, last column)."""
    match = WHOLE_COLUMN.match(text)
    if match is None:
        return None
    return clean_sheet(match.group("sheet")), column_index(match.group("c1")), column_index(match.group("c2"))
