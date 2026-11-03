"""Infer a field's type from a column: formats first, then validation, patterns, then statistics."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
import re
from typing import Any

from daftar_worker.analyser.grid import Cell, text_of


# Column names that make an otherwise plain number more specific.
MONEY_HINT = re.compile(
    r"\b(montants?|prix|soldes?|totale?s?|d[ûu]s?|pay[ée]e?s?|co[ûu]ts?|frais|salaires?|recettes?|d[ée]penses?"
    r"|tarifs?|reste|acomptes?|amounts?|prices?|costs?|fees?|balance|paid)\b"
    r"|مبلغ|المبلغ|سعر|السعر|ثمن|رصيد|الرصيد|تكلفة|مصاريف|راتب|المدفوع|المتبقي",
    re.IGNORECASE,
)
PHONE_HINT = re.compile(r"t[ée]l|phone|mobile|gsm|portable|هاتف|جوال|نقال", re.IGNORECASE)
DATE_HINT = re.compile(r"date|تاريخ|يوم|\bjour\b|[ée]ch[ée]ance|naissance|inscri", re.IGNORECASE)
CURRENCY_FORMAT = re.compile(r'(\bDA\b|"DA"|DZD|د\.?ج|\[\$[^\]]*(DA|DZD|د\.?ج)[^\]]*\])', re.IGNORECASE)
DATE_FORMAT_CODES = re.compile(r"[dmyhs]", re.IGNORECASE)
FORMAT_LITERAL = re.compile(r'"[^"]*"|\\.|\[[^\]]*\]')

DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
PHONE = re.compile(r"^(\+213|00213|0)[5-7][0-9]{8}$")
LANDLINE = re.compile(r"^(\+213|00213|0)[2-4][0-9]{7,8}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
TEXT_DATE = re.compile(r"^([0-9]{1,2})[/.\-]([0-9]{1,2})[/.\-]([0-9]{4}|[0-9]{2})$")
TEXT_DATETIME = re.compile(r"^([0-9]{1,2})[/.\-]([0-9]{1,2})[/.\-]([0-9]{4}|[0-9]{2})\s+[0-9]{1,2}:[0-9]{2}")
TEXT_MONEY = re.compile(r"^(-?[0-9][0-9 .,  ]*)\s*(DA|DZD|د\.?ج\.?|دج)$", re.IGNORECASE)
TEXT_PERCENT = re.compile(r"^-?[0-9]+([.,][0-9]+)?\s*%$")
TEXT_INTEGER = re.compile(r"^-?[1-9][0-9]{0,2}([   .,][0-9]{3})+$|^-?(0|[1-9][0-9]*)$")
TEXT_DECIMAL = re.compile(r"^-?[0-9]{1,3}([   .][0-9]{3})*,[0-9]+$|^-?[0-9]+[.,][0-9]+$")
BOOLEAN_WORDS = {"oui", "non", "yes", "no", "vrai", "faux", "true", "false", "نعم", "لا", "o", "n"}
MULTI_SEPARATOR = re.compile(r"\s*[;,/+]\s*")

SERIAL_LOW = 18264  # 1950-01-01.
SERIAL_HIGH = 73050  # 2099-12-31.
MATCH_SHARE = 0.9
CHOICE_MAX_DISTINCT = 12
CHOICE_MIN_ROWS = 6
LONG_TEXT_MEDIAN = 80
LONG_TEXT_MAX = 200


@dataclass
class TypeGuess:
    type: str
    score: float
    reason: str  # A key that explain.py turns into words.
    matched: int
    total: int
    result_type: str | None = None
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    choices: list[dict[str, Any]] = field(default_factory=list)
    choice_source: str | None = None
    target: dict[str, str] | None = None


def _is_date_format(number_format: str | None) -> bool:
    if not number_format:
        return False
    code = FORMAT_LITERAL.sub("", number_format).split(";")[0]
    return bool(DATE_FORMAT_CODES.search(code)) and "0" not in code and "#" not in code


def _is_valid_date(day: int, month: int, year: int) -> bool:
    if year < 100:
        year += 2000
    try:
        date(year, month, day)
    except ValueError:
        return False
    return 1900 <= year <= 2100


def normal_text(cell: Cell) -> str:
    return text_of(cell).translate(DIGITS).strip()


def _phone_digits(text: str) -> str:
    return re.sub(r"[\s.\-()]", "", text)


def is_phone(text: str) -> bool:
    digits = _phone_digits(text)
    return bool(PHONE.match(digits) or LANDLINE.match(digits))


def _share(cells: list[Cell], test: Any) -> int:
    return sum(1 for cell in cells if test(cell))


def _guess(kind: str, reason: str, matched: int, total: int, base: float) -> TypeGuess:
    # A column with exceptions is less sure, and small columns are less sure than large ones.
    rate = matched / total
    size_penalty = 0.1 if total < 3 else 0.0
    score = max(0.0, base - (1 - rate) * 1.5 - size_penalty)
    return TypeGuess(kind, round(score, 3), reason, matched, total)


def _number_type(numbers: list[Cell], header: str, total: int) -> TypeGuess | None:
    count = len(numbers)
    if count == 0 or count / total < MATCH_SHARE:
        return None
    formats = [cell.number_format or "" for cell in numbers]
    if _share_formats(formats, lambda fmt: "%" in fmt) / count >= MATCH_SHARE:
        return _guess("percent", "percentFormat", count, total, 0.97)
    if _share_formats(formats, lambda fmt: bool(CURRENCY_FORMAT.search(fmt))) / count >= MATCH_SHARE:
        return _guess("money", "currencyFormat", count, total, 0.97)
    values = [cell.value for cell in numbers]
    whole = all(float(value).is_integer() for value in values)
    if whole and DATE_HINT.search(header) and all(SERIAL_LOW <= value <= SERIAL_HIGH for value in values):
        return _guess("date", "serialDate", count, total, 0.82)
    if whole and PHONE_HINT.search(header) and all(
        is_phone("0" + str(int(value))) for value in values
    ):
        return _guess("phone", "phoneLostZero", count, total, 0.8)
    if MONEY_HINT.search(header):
        return _guess("money", "moneyHeader", count, total, 0.72)
    if whole:
        return _guess("integer", "wholeNumbers", count, total, 0.9)
    return _guess("decimal", "decimalNumbers", count, total, 0.9)


def _share_formats(formats: list[str], test: Any) -> int:
    return sum(1 for fmt in formats if test(fmt))


def _text_type(texts: list[Cell], total: int) -> TypeGuess | None:
    values = [normal_text(cell) for cell in texts]
    count = len(values)
    if count == 0:
        return None

    def matches(test: Any) -> int:
        return sum(1 for value in values if test(value))

    def enough(hits: int) -> bool:
        return hits / total >= MATCH_SHARE

    def date_ok(value: str) -> bool:
        match = TEXT_DATE.match(value)
        if match is None:
            return False
        return _is_valid_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))

    checks: list[tuple[Any, str, str, float]] = [
        (is_phone, "phone", "phonePattern", 0.95),
        (EMAIL.match, "email", "emailPattern", 0.97),
        (date_ok, "date", "textDate", 0.9),
        (TEXT_DATETIME.match, "datetime", "textDate", 0.88),
        (TEXT_MONEY.match, "money", "moneyText", 0.93),
        (TEXT_PERCENT.match, "percent", "percentText", 0.9),
    ]
    for test, kind, reason, base in checks:
        hits = matches(test)
        if enough(hits):
            return _guess(kind, reason, hits, total, base)
    hits = matches(lambda value: value.casefold() in BOOLEAN_WORDS)
    if enough(hits) and len({value.casefold() for value in values}) <= 2 and count >= 2:
        return _guess("boolean", "booleanWords", hits, total, 0.85)
    hits = matches(TEXT_DECIMAL.match)
    if enough(hits):
        return _guess("decimal", "numericText", hits, total, 0.72)
    # Leading zeros mean a code: 0123 must stay text, as a number it would lose the zero.
    hits = matches(TEXT_INTEGER.match)
    if enough(hits):
        return _guess("integer", "numericText", hits, total, 0.7)
    return None


def _choices_from(values: list[str]) -> list[dict[str, Any]]:
    counts = Counter(values)
    return [{"value": value, "count": count} for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _free_text(cells: list[Cell], total: int) -> TypeGuess:
    texts = [text_of(cell) for cell in cells]
    lengths = sorted(len(text) for text in texts)
    median = lengths[len(lengths) // 2] if lengths else 0
    multiline = any("\n" in str(cell.value) for cell in cells)
    if median > LONG_TEXT_MEDIAN or (lengths and lengths[-1] > LONG_TEXT_MAX) or multiline:
        return _guess("longtext", "longValues", len(cells), total, 0.85)

    distinct = len(set(texts))
    parts = [part for text in texts for part in MULTI_SEPARATOR.split(text) if part]
    distinct_parts = len(set(parts))
    if (
        total >= CHOICE_MIN_ROWS
        and any(MULTI_SEPARATOR.search(text) for text in texts)
        and 2 <= distinct_parts < distinct
        and distinct_parts <= total * 0.5
    ):
        guess = _guess("multichoice", "fewValuesSeparated", len(cells), total, 0.65)
        guess.choices = _choices_from(parts)
        guess.choice_source = "values"
        guess.alternatives = [{"type": "text"}]
        return guess
    if total >= CHOICE_MIN_ROWS and 2 <= distinct <= CHOICE_MAX_DISTINCT and distinct <= total * 0.5:
        guess = _guess("choice", "fewValues", len(cells), total, 0.7)
        guess.choices = _choices_from(texts)
        guess.choice_source = "values"
        guess.alternatives = [{"type": "text"}]
        return guess
    # Mixed columns land here too; the score says how sure we are that they're plain text.
    all_text = sum(1 for cell in cells if cell.is_text)
    return _guess("text", "plainText", all_text, total, 0.8)


def infer_type(
    cells: list[Cell],
    header: str,
    validation: dict[str, Any] | None = None,
) -> TypeGuess | None:
    """Return the best type for a column's data cells, or None if the column is empty."""
    total = len(cells)
    if total == 0:
        return None

    if validation:
        choices = validation.get("values") or []
        if validation.get("target"):
            guess = _guess("link", "validationOtherSheet", total, total, 0.9)
            guess.target = validation["target"]
            guess.choices = [{"value": value, "count": 0} for value in choices]
            guess.choice_source = "validationList"
            guess.alternatives = [{"type": "choice"}]
            return guess
        counts = Counter(text_of(cell) for cell in cells)
        guess = _guess("choice", "validationList", total, total, 0.97)
        guess.choices = [{"value": value, "count": counts.get(value, 0)} for value in choices]
        guess.choice_source = "validationList"
        return guess

    formulas = [cell for cell in cells if cell.formula]
    if len(formulas) / total >= 0.8:
        guess = _guess("computed", "formulaColumn", len(formulas), total, 0.9)
        kinds = Counter(cell.kind for cell in formulas)
        guess.result_type = _result_type(formulas, header, kinds)
        return guess

    dates = [cell for cell in cells if cell.kind == "d"]
    if len(dates) / total >= MATCH_SHARE:
        with_time = [cell for cell in dates if _has_time(str(cell.value))]
        if with_time:
            return _guess("datetime", "dateFormat", len(dates), total, 0.95)
        return _guess("date", "dateFormat", len(dates), total, 0.97)

    booleans = [cell for cell in cells if cell.kind == "b"]
    if len(booleans) / total >= MATCH_SHARE:
        return _guess("boolean", "trueFalse", len(booleans), total, 0.97)

    numbers = [cell for cell in cells if cell.is_number]
    number_guess = _number_type(numbers, header, total)
    if number_guess is not None:
        return number_guess
    texts = [cell for cell in cells if cell.is_text]
    text_guess = _text_type(texts, total)
    if text_guess is not None:
        return text_guess
    return _free_text(cells, total)


def _has_time(value: str) -> bool:
    if "T" not in value:
        return ":" in value
    return not value.endswith("T00:00:00")


def _result_type(formulas: list[Cell], header: str, kinds: Counter[str]) -> str:
    common = kinds.most_common(1)[0][0]
    if common == "d":
        return "date"
    if common == "b":
        return "boolean"
    if common == "s":
        return "text"
    formats = [cell.number_format or "" for cell in formulas]
    if any("%" in fmt for fmt in formats):
        return "percent"
    if any(CURRENCY_FORMAT.search(fmt) for fmt in formats) or MONEY_HINT.search(header):
        return "money"
    numbers = [cell.value for cell in formulas if cell.is_number]
    return "integer" if numbers and all(float(value).is_integer() for value in numbers) else "decimal"


__all__ = ["TypeGuess", "infer_type", "is_phone"]
