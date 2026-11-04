"""Evaluate a C-3 expression tree on one record, with Excel's semantics.

The runtime has its own evaluator (WP-9). This one lets the analyser check each translation against
Excel's stored results, and it is what the agreement tests run. Dates are Excel serial numbers.
"""

from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal, InvalidOperation
import math
from typing import Any


EPOCH = date(1899, 12, 30)
NUMBER_FORMAT = ".15g"


class ExcelError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


DIV0, NA, NUM, VALUE = "#DIV/0!", "#N/A", "#NUM!", "#VALUE!"


def to_serial(moment: date | datetime) -> float:
    whole = date(moment.year, moment.month, moment.day)
    days = (whole - EPOCH).days
    if days < 61:  # Excel's 1900 leap-year bug shifts everything before 1 March 1900.
        days -= 1
    if isinstance(moment, datetime):
        return days + (moment.hour * 3600 + moment.minute * 60 + moment.second) / 86400
    return float(days)


def from_serial(serial: float) -> datetime:
    days = math.floor(serial)
    if days < 1:
        raise ExcelError(NUM)
    offset = days + 1 if days < 60 else days
    seconds = round((serial - days) * 86400)
    return datetime(EPOCH.year, EPOCH.month, EPOCH.day) + timedelta(days=offset, seconds=seconds)


def to_number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        raise ExcelError(VALUE) from None


def to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        number = float(value)
        return str(int(number)) if number.is_integer() and abs(number) < 1e15 else format(number, NUMBER_FORMAT)
    return str(value)


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().upper()
    if text in ("TRUE", "FALSE"):
        return text == "TRUE"
    raise ExcelError(VALUE)


def _rank(value: Any) -> int:
    if isinstance(value, bool):
        return 2
    return 1 if isinstance(value, str) else 0


def compare(left: Any, right: Any) -> int:
    """Excel's order: numbers, then text (ignoring case), then booleans. Blank adapts to the other."""
    if left is None:
        left = "" if isinstance(right, str) else (False if isinstance(right, bool) else 0.0)
    if right is None:
        right = "" if isinstance(left, str) else (False if isinstance(left, bool) else 0.0)
    if _rank(left) != _rank(right):
        return -1 if _rank(left) < _rank(right) else 1
    if isinstance(left, str):
        left, right = left.casefold(), right.casefold()
    return int(left > right) - int(left < right)


def _binary(op: str, left: Any, right: Any) -> Any:
    if op == "concat":
        return to_text(left) + to_text(right)
    if op in ("eq", "ne", "lt", "le", "gt", "ge"):
        order = compare(left, right)
        return {"eq": order == 0, "ne": order != 0, "lt": order < 0, "le": order <= 0, "gt": order > 0, "ge": order >= 0}[op]
    a, b = to_number(left), to_number(right)
    if op == "add":
        result = a + b
        # Excel's near-zero compensation: a sum that cancels to within 15 digits is exactly zero.
        return 0.0 if result != 0 and abs(result) < 1e-15 * max(abs(a), abs(b)) else result
    if op == "sub":
        result = a - b
        return 0.0 if result != 0 and abs(result) < 1e-15 * max(abs(a), abs(b)) else result
    if op == "mul":
        return a * b
    if op == "div":
        if b == 0:
            raise ExcelError(DIV0)
        return a / b
    if op == "pow":
        if a == 0 and b == 0:
            raise ExcelError(NUM)
        try:
            result = a**b
        except (ZeroDivisionError, OverflowError):
            raise ExcelError(DIV0 if a == 0 else NUM) from None
        if isinstance(result, complex):
            raise ExcelError(NUM)
        return result
    raise ExcelError(VALUE)


def _round(number: float, digits: float, mode: str) -> float:
    exponent = Decimal(1).scaleb(-int(digits))
    try:
        return float(Decimal(format(number, ".15g")).quantize(exponent, rounding=mode))
    except InvalidOperation:
        return number


def _round_away(number: float, digits: float, up: bool) -> float:
    return _round(number, digits, ROUND_UP if up else ROUND_DOWN)


def _numbers(args: list[tuple[Any, bool]]) -> list[float]:
    """Aggregate arguments: a value from a cell counts only if numeric; a typed one is coerced."""
    found = []
    for value, from_cell in args:
        if from_cell:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                found.append(float(value))
        elif value is not None:
            found.append(to_number(value))
    return found


def _date(year: float, month: float, day: float) -> float:
    y, m, d = int(year), int(month), int(day)
    if 0 <= y < 1900:
        y += 1900
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    if not 1 <= y <= 9999:
        raise ExcelError(NUM)
    return to_serial(date(y, m, 1) + timedelta(days=d - 1))


def _add_months(serial: float, months: float) -> date:
    moment = from_serial(serial)
    total = moment.year * 12 + moment.month - 1 + int(months)
    year, month = total // 12, total % 12 + 1
    last = (date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(moment.day, last))


def _end_of_month(serial: float, months: float) -> float:
    moment = _add_months(serial, months)
    return to_serial(date(moment.year + moment.month // 12, moment.month % 12 + 1, 1) - timedelta(days=1))


def _weekday(serial: float, kind: float = 1) -> float:
    number = (math.floor(serial) - 1) % 7  # 0 is Sunday.
    if kind == 1:
        return float(number + 1)
    if kind == 2:
        return float((number + 6) % 7 + 1)
    if kind == 3:
        return float((number + 6) % 7)
    raise ExcelError(NUM)


def _find(needle: str, haystack: str, start: float = 1) -> float:
    position = haystack.find(needle, int(start) - 1)
    if position < 0 or start < 1:
        raise ExcelError(VALUE)
    return float(position + 1)


def _substitute(text: str, old: str, new: str, instance: float | None = None) -> str:
    if not old:
        return text
    if instance is None:
        return text.replace(old, new)
    position = -1
    for _ in range(int(instance)):
        position = text.find(old, position + 1)
        if position < 0:
            return text
    return text[:position] + new + text[position + len(old) :]


def _mround(number: float, multiple: float) -> float:
    if multiple == 0:
        return 0.0
    if number * multiple < 0:
        raise ExcelError(NUM)
    return _round(number / multiple, 0, ROUND_HALF_UP) * multiple


def _ceiling(number: float, significance: float) -> float:
    if significance == 0:
        return 0.0
    if number > 0 > significance:
        raise ExcelError(NUM)
    return math.ceil(_round(number / significance, 12, ROUND_HALF_UP)) * significance


def _floor(number: float, significance: float) -> float:
    if significance == 0:
        raise ExcelError(DIV0)
    if number > 0 > significance:
        raise ExcelError(NUM)
    return math.floor(_round(number / significance, 12, ROUND_HALF_UP)) * significance


def _mod(number: float, divisor: float) -> float:
    if divisor == 0:
        raise ExcelError(DIV0)
    return number - divisor * math.floor(number / divisor)


def _sqrt(number: float) -> float:
    if number < 0:
        raise ExcelError(NUM)
    return math.sqrt(number)


def _proper(text: str) -> str:
    result, start = [], True
    for letter in text:
        result.append(letter.upper() if start else letter.lower())
        start = not letter.isalpha()
    return "".join(result)


def _text_part(text: str, start: int, length: int) -> str:
    if start < 1 or length < 0:
        raise ExcelError(VALUE)
    return text[start - 1 : start - 1 + length]


def _left(text: str, count: float = 1) -> str:
    if count < 0:
        raise ExcelError(VALUE)
    return text[: int(count)]


def _right(text: str, count: float = 1) -> str:
    if count < 0:
        raise ExcelError(VALUE)
    return text[-int(count) :] if count >= 1 else ""


def _raise_na() -> None:
    raise ExcelError(NA)


N, T = to_number, to_text
# Plain functions: each argument is evaluated, errors propagate, and then these run on the values.
SIMPLE: dict[str, Callable[..., Any]] = {
    "ABS": lambda a: abs(N(a)),
    "INT": lambda a: float(math.floor(N(a))),
    "SQRT": lambda a: _sqrt(N(a)),
    "POWER": lambda a, b: _binary("pow", a, b),
    "MOD": lambda a, b: _mod(N(a), N(b)),
    "ROUND": lambda a, b=0: _round(N(a), N(b), ROUND_HALF_UP),
    "ROUNDUP": lambda a, b=0: _round_away(N(a), N(b), True),
    "ROUNDDOWN": lambda a, b=0: _round_away(N(a), N(b), False),
    "MROUND": lambda a, b: _mround(N(a), N(b)),
    "CEILING": lambda a, b=1: _ceiling(N(a), N(b)),
    "FLOOR": lambda a, b=1: _floor(N(a), N(b)),
    "NOT": lambda a: not to_bool(a),
    "CONCATENATE": lambda *a: "".join(T(item) for item in a),
    "CONCAT": lambda *a: "".join(T(item) for item in a),
    "LEFT": lambda a, b=1: _left(T(a), N(b)),
    "RIGHT": lambda a, b=1: _right(T(a), N(b)),
    "MID": lambda a, b, c: _text_part(T(a), int(N(b)), int(N(c))),
    "LEN": lambda a: float(len(T(a))),
    "TRIM": lambda a: " ".join(part for part in T(a).split(" ") if part),
    "UPPER": lambda a: T(a).upper(),
    "LOWER": lambda a: T(a).lower(),
    "PROPER": lambda a: _proper(T(a)),
    "SUBSTITUTE": lambda a, b, c, d=None: _substitute(T(a), T(b), T(c), None if d is None else N(d)),
    "REPLACE": lambda a, b, c, d: T(a)[: int(N(b)) - 1] + T(d) + T(a)[int(N(b)) - 1 + int(N(c)) :],
    "FIND": lambda a, b, c=1: _find(T(a), T(b), N(c)),
    "SEARCH": lambda a, b, c=1: _find(T(a).casefold(), T(b).casefold(), N(c)),
    "VALUE": lambda a: to_number(a if a is not None else 0),
    "EXACT": lambda a, b: T(a) == T(b),
    "REPT": lambda a, b: T(a) * int(N(b)),
    "DATE": lambda a, b, c: _date(N(a), N(b), N(c)),
    "YEAR": lambda a: float(from_serial(N(a)).year),
    "MONTH": lambda a: float(from_serial(N(a)).month),
    "DAY": lambda a: float(from_serial(N(a)).day),
    "HOUR": lambda a: float(from_serial(N(a) if N(a) >= 1 else N(a) + 1).hour),
    "MINUTE": lambda a: float(from_serial(N(a) if N(a) >= 1 else N(a) + 1).minute),
    "SECOND": lambda a: float(from_serial(N(a) if N(a) >= 1 else N(a) + 1).second),
    "WEEKDAY": lambda a, b=1: _weekday(N(a), N(b)),
    "EDATE": lambda a, b: to_serial(_add_months(N(a), N(b))),
    "EOMONTH": lambda a, b: _end_of_month(N(a), N(b)),
    "DAYS": lambda a, b: float(math.floor(N(a)) - math.floor(N(b))),
    "ISBLANK": lambda a: a is None,
    "ISNUMBER": lambda a: isinstance(a, (int, float)) and not isinstance(a, bool),
    "ISTEXT": lambda a: isinstance(a, str),
    "NA": _raise_na,
    "TRUE": lambda: True,
    "FALSE": lambda: False,
}
AGGREGATES = {"SUM", "MIN", "MAX", "AVERAGE", "COUNT", "COUNTA", "PRODUCT"}
# Functions that don't evaluate all their arguments, or that catch errors.
LAZY = {"IF", "IFS", "AND", "OR", "IFERROR", "IFNA", "ISERROR", "ISNA", "SWITCH"}
CLOCK = {"TODAY", "NOW"}
TRANSLATABLE = frozenset(SIMPLE) | AGGREGATES | LAZY | CLOCK


class Evaluator:
    def __init__(
        self,
        record: Mapping[str, Any],
        related: Callable[[str, str], Any] | None = None,
        now: datetime | None = None,
    ) -> None:
        self.record = record
        self.related = related
        self.now = now

    def run(self, expr: dict[str, Any]) -> Any:
        """Return the value. An Excel error comes back as an ExcelError instance, not raised."""
        try:
            return self._eval(expr)
        except ExcelError as error:
            return error

    def _field(self, key: str) -> Any:
        value = self.record.get(key)
        if isinstance(value, ExcelError):
            raise value
        return value

    def _eval(self, expr: dict[str, Any]) -> Any:
        kind = expr["kind"]
        if kind == "literal":
            return expr["value"]
        if kind == "field":
            return self._field(expr["field"])
        if kind == "related":
            if self.related is None:
                raise ExcelError(NA)
            value = self.related(expr["via"], expr["field"])
            if isinstance(value, ExcelError):
                raise value
            return value
        if kind == "op":
            return self._op(expr)
        if kind == "call":
            return self._call(expr["fn"], expr["args"])
        raise ExcelError(VALUE)

    def _op(self, expr: dict[str, Any]) -> Any:
        op, args = expr["op"], expr["args"]
        if op == "neg":
            return -to_number(self._eval(args[0]))
        if op == "pct":
            return to_number(self._eval(args[0])) / 100
        return _binary(op, self._eval(args[0]), self._eval(args[1]))

    def _aggregate(self, name: str, args: list[dict[str, Any]]) -> Any:
        values = [(self._eval(arg), arg["kind"] in ("field", "related")) for arg in args]
        if name == "COUNTA":
            return float(sum(1 for value, from_cell in values if value is not None or not from_cell))
        if name == "COUNT":
            return float(len(_numbers(values)))
        numbers = _numbers(values)
        if name == "SUM":
            return math.fsum(numbers)
        if name == "PRODUCT":
            return math.prod(numbers) if numbers else 0.0
        if name == "AVERAGE":
            if not numbers:
                raise ExcelError(DIV0)
            return math.fsum(numbers) / len(numbers)
        return (max if name == "MAX" else min)(numbers, default=0.0)

    def _lazy(self, name: str, args: list[dict[str, Any]]) -> Any:
        if name == "IF":
            if to_bool(self._eval(args[0])):
                return self._eval(args[1]) if len(args) > 1 else True
            return self._eval(args[2]) if len(args) > 2 else False
        if name == "IFS":
            for test, result in zip(args[::2], args[1::2], strict=False):
                if to_bool(self._eval(test)):
                    return self._eval(result)
            raise ExcelError(NA)
        if name == "SWITCH":
            subject = self._eval(args[0])
            pairs = args[1:]
            for test, result in zip(pairs[::2], pairs[1::2], strict=False):
                if compare(subject, self._eval(test)) == 0:
                    return self._eval(result)
            if len(pairs) % 2:
                return self._eval(pairs[-1])
            raise ExcelError(NA)
        if name in ("AND", "OR"):
            values = [self._eval(arg) for arg in args]  # Excel evaluates all, so errors propagate.
            tests = [to_bool(value) for value in values if value is not None]
            if not tests:
                raise ExcelError(VALUE)
            return all(tests) if name == "AND" else any(tests)
        try:
            value = self._eval(args[0])
        except ExcelError as error:
            if name == "ISERROR":
                return True
            if name == "ISNA":
                return error.code == NA
            if name == "IFERROR" or error.code == NA:
                return self._eval(args[1])
            raise
        if name in ("ISERROR", "ISNA"):
            return False
        return "" if value is None else value

    def _call(self, name: str, args: list[dict[str, Any]]) -> Any:
        if name in LAZY:
            return self._lazy(name, args)
        if name in AGGREGATES:
            return self._aggregate(name, args)
        if name in CLOCK:
            if self.now is None:
                raise ExcelError(NA)
            return float(math.floor(to_serial(self.now))) if name == "TODAY" else to_serial(self.now)
        function = SIMPLE.get(name)
        if function is None:
            raise ExcelError("#NAME?")
        values = [self._eval(arg) for arg in args]
        try:
            return function(*values)
        except TypeError:
            raise ExcelError(VALUE) from None
        except (OverflowError, ValueError):
            raise ExcelError(NUM) from None
