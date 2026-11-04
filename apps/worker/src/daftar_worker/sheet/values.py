"""Cell values in a field's type, and the wording that marks a total. Used by import and re-import."""

from datetime import date, datetime
import re
from typing import Any

from openpyxl.utils.datetime import from_excel

from daftar_worker.sheet.grid import Cell, text_of
from daftar_worker.sheet.names import fingerprint


DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
TEXT_DATE = re.compile(r"^([0-9]{1,2})[/.\-]([0-9]{1,2})[/.\-]([0-9]{4}|[0-9]{2})$")
TOTAL_WORDS = re.compile(
    r"^\s*(?:sous[- ]?tota(?:l|ux)|s/\s?total|total\s+g[ée]n[ée]ral|grand\s+total|tota(?:l|ux)|subtotal|sum"
    r"|somme|cumul|(?:ال)?مجموع|(?:ال)?[إا]جمالي)(?:\s|:|$)",
    re.IGNORECASE,
)


def normal_text(cell: Cell) -> str:
    return text_of(cell).translate(DIGITS).strip()


WHITESPACE_NUMBER = re.compile(r"[\s  ]")
CURRENCY = re.compile(r"\s*(DA|DZD|د\.?ج\.?|دج)\s*$", re.IGNORECASE)
TRUE_WORDS = {"oui", "yes", "vrai", "true", "نعم", "o"}
FALSE_WORDS = {"non", "no", "faux", "false", "لا", "n"}


def parse_number(text: str) -> float | None:
    """1 234,50 and 1.234.567,89 DA as numbers. The last separator with 1-2 digits after is decimal."""
    clean = CURRENCY.sub("", text.translate(DIGITS).strip())
    clean = WHITESPACE_NUMBER.sub("", clean).rstrip("%")
    if not clean:
        return None
    last_comma, last_dot = clean.rfind(","), clean.rfind(".")
    if last_comma > last_dot:
        clean = clean.replace(".", "").replace(",", ".")
    else:
        clean = clean.replace(",", "")
    try:
        return float(clean)
    except ValueError:
        return None


def convert_value(entry: dict[str, Any], cell: Any) -> Any:
    """A cell in its field's type, as the runtime expects it. None if it can't be read as that."""
    kind = entry["type"]
    value = cell.value
    if value is None:
        return None
    if kind in ("integer", "decimal", "money", "percent"):
        number = value if cell.is_number else parse_number(normal_text(cell))
        if number is None or isinstance(number, bool):
            return None
        if kind == "percent" and not cell.is_number and "%" in str(value):
            number = number / 100
        if kind == "integer":
            return int(number) if float(number).is_integer() else None
        return number
    if kind in ("date", "datetime"):
        return _date_value(cell, kind)
    if kind == "boolean":
        if cell.kind == "b":
            return bool(value)
        word = normal_text(cell).casefold()
        return True if word in TRUE_WORDS else (False if word in FALSE_WORDS else None)
    if kind == "choice":
        return _choice_key(entry, text_of(cell))
    if kind == "multichoice":
        parts = [part for part in re.split(r"\s*[;,]\s*", text_of(cell)) if part]
        keys = [_choice_key(entry, part) for part in parts]
        return keys if all(keys) else None
    if kind == "phone":
        digits = re.sub(r"[\s.\-()]", "", normal_text(cell))
        if cell.is_number:
            digits = f"0{int(value)}"
        return digits or None
    return text_of(cell) or None


def _choice_key(entry: dict[str, Any], text: str) -> str | None:
    for choice in entry["choices"]:
        if choice.get("source") == text or fingerprint(str(choice.get("source"))) == fingerprint(
            text
        ):
            return str(choice["key"])
    return None


def _date_value(cell: Any, kind: str) -> str | None:
    value = cell.value
    if cell.kind == "n":
        try:
            moment = from_excel(value)
        except (OverflowError, ValueError, TypeError):
            return None
        return (
            moment.isoformat()[:10]
            if isinstance(moment, (date, datetime)) and kind == "date"
            else None
        )
    if cell.kind == "d":
        text = str(value)
        return text[:10] if kind == "date" else (f"{text}+01:00" if "T" in text else None)
    match = TEXT_DATE.match(normal_text(cell))
    if not match:
        return None
    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    if year < 100:
        year += 2000
    try:
        moment = date(year, month, day)
    except ValueError:
        return None
    return moment.isoformat() if kind == "date" else f"{moment.isoformat()}T00:00:00+01:00"
