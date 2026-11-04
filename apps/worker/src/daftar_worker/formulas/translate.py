"""Translate a formula's AST into the C-3 expression tree, for one row of a table.

Only what a record can compute on its own translates: its own fields, and lookups that become a
relation. Anything else stays with the engine, and the reason is reported, never hidden.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from openpyxl.utils import get_column_letter

from daftar_worker.formulas.engine import EngineError, parse_formula
from daftar_worker.formulas.evaluate import TRANSLATABLE
from daftar_worker.formulas.references import parse_columns, parse_reference


BINARY = {
    "+": "add", "-": "sub", "*": "mul", "/": "div", "^": "pow", "&": "concat",
    "=": "eq", "<>": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge",
}  # fmt: skip
BOOLEAN_FUNCTIONS = {"AND", "OR", "NOT", "ISBLANK", "ISNUMBER", "ISTEXT", "ISERROR", "ISNA", "EXACT", "TRUE", "FALSE"}
TEXT_FUNCTIONS = {"CONCATENATE", "CONCAT", "LEFT", "RIGHT", "MID", "TRIM", "UPPER", "LOWER", "PROPER", "SUBSTITUTE", "REPLACE", "REPT"}
DATE_FUNCTIONS = {"DATE", "EDATE", "EOMONTH", "TODAY", "NOW"}
ANY_FUNCTIONS = {"IF", "IFS", "IFERROR", "IFNA", "SWITCH", "NA"}
LOOKUPS = {"VLOOKUP", "XLOOKUP", "INDEX", "MATCH", "HLOOKUP", "LOOKUP"}


def field_key(column: int) -> str:
    """A provisional key for a table column. WP-12 maps these to the spec's real keys."""
    return f"col_{get_column_letter(column).lower()}"


@dataclass(frozen=True)
class Lookup:
    """A lookup into another sheet: `from_column` here matches `key_column` there."""

    from_column: int
    to_sheet: str
    key_column: int
    result_column: int


@dataclass
class Translation:
    expr: dict[str, Any] | None = None
    deps: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)  # Why it stays with the engine, if it does.
    functions: set[str] = field(default_factory=set)
    lookups: list[Lookup] = field(default_factory=list)


class _Untranslatable(Exception):
    pass


class _Translator:
    def __init__(self, sheet: str, row: int, columns: Mapping[int, str]) -> None:
        self.sheet = sheet
        self.row = row
        self.columns = columns
        self.deps: dict[str, None] = {}
        self.functions: set[str] = set()
        self.lookups: list[Lookup] = []

    def _field(self, column: int) -> dict[str, Any]:
        kind = self.columns.get(column)
        if kind is None:
            raise _Untranslatable("referenceOutsideTable")
        key = field_key(column)
        self.deps[key] = None
        return {"kind": "field", "valueType": kind, "field": key}

    def _own_row_columns(self, text: str) -> list[int]:
        reference = parse_reference(text)
        if reference is None:
            raise _Untranslatable("namedOrTableReference" if parse_columns(text) is None else "wholeColumn")
        if reference.sheet not in (None, self.sheet):
            raise _Untranslatable("otherSheet")
        if reference.top != self.row or reference.bottom != self.row:
            raise _Untranslatable("otherRow")
        return list(range(reference.left, reference.right + 1))

    def node(self, node: dict[str, Any]) -> dict[str, Any]:
        kind = node["node_type"]
        if kind == "Literal":
            return self._literal(node["value"])
        if kind == "Reference":
            columns = self._own_row_columns(node["reference"])
            if len(columns) != 1:
                raise _Untranslatable("rangeOutsideAggregate")
            return self._field(columns[0])
        if kind == "BinaryOp":
            op = BINARY.get(node["operator"])
            if op is None:
                raise _Untranslatable("operator")
            value_type = "text" if op == "concat" else "boolean" if op in ("eq", "ne", "lt", "le", "gt", "ge") else "number"
            return {"kind": "op", "valueType": value_type, "op": op, "args": [self.node(node["left"]), self.node(node["right"])]}
        if kind == "UnaryOp":
            operand = self.node(node["operand"])
            if node["operator"] == "+":
                return operand
            op = {"-": "neg", "%": "pct"}.get(node["operator"])
            if op is None:
                raise _Untranslatable("operator")
            return {"kind": "op", "valueType": "number", "op": op, "args": [operand]}
        if kind == "Function":
            return self._function(node["name"].upper(), node.get("args", []))
        raise _Untranslatable(f"node{kind}")

    @staticmethod
    def _literal(value: Any) -> dict[str, Any]:
        if isinstance(value, bool):
            return {"kind": "literal", "valueType": "boolean", "value": value}
        if isinstance(value, (int, float)):
            return {"kind": "literal", "valueType": "number", "value": value}
        if isinstance(value, str):
            return {"kind": "literal", "valueType": "text", "value": value}
        raise _Untranslatable("literal")

    def _function(self, name: str, args: list[dict[str, Any]]) -> dict[str, Any]:
        self.functions.add(name)
        if name in LOOKUPS:
            return self._lookup(name, args)
        if name not in TRANSLATABLE:
            raise _Untranslatable(f"function:{name}")
        if any(arg["node_type"] == "Omitted" for arg in args):
            raise _Untranslatable("omittedArgument")
        translated: list[dict[str, Any]] = []
        for arg in args:
            # An aggregate may take a span of the record's own row, as in SUM(B2:D2).
            if arg["node_type"] == "Reference" and name in ("SUM", "MIN", "MAX", "AVERAGE", "COUNT", "COUNTA", "PRODUCT"):
                translated.extend(self._field(column) for column in self._own_row_columns(arg["reference"]))
            else:
                translated.append(self.node(arg))
        return {"kind": "call", "valueType": _function_type(name), "fn": name, "args": translated}

    def _column_of(self, node: dict[str, Any]) -> tuple[str | None, int]:
        """The sheet and single column of a lookup's range argument."""
        if node["node_type"] != "Reference":
            raise _Untranslatable("lookupShape")
        text = node["reference"]
        whole = parse_columns(text)
        if whole is not None:
            return whole[0], whole[1]
        reference = parse_reference(text)
        if reference is None:
            raise _Untranslatable("namedOrTableReference")
        return reference.sheet, reference.left

    def _lookup(self, name: str, args: list[dict[str, Any]]) -> dict[str, Any]:
        found = _lookup_parts(name, args)
        if found is None:
            raise _Untranslatable(f"function:{name}")
        key, key_range, result_range, offset = found
        sheet, key_column = self._column_of(key_range)
        result_sheet, result_column = self._column_of(result_range)
        if sheet in (None, self.sheet) or result_sheet != sheet:
            raise _Untranslatable("lookupNotAnotherSheet")
        source = self.node(key)
        if source["kind"] != "field":
            raise _Untranslatable("lookupKeyNotAField")
        from_column = next(column for column in self.columns if field_key(column) == source["field"])
        target = result_column + offset
        self.lookups.append(Lookup(from_column, sheet, key_column, target))
        return {"kind": "related", "valueType": "any", "via": source["field"], "field": field_key(target)}


def _lookup_parts(
    name: str, args: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], int] | None:
    """(key, key range, result range, column offset) for an exact-match lookup, else None."""
    if name == "VLOOKUP" and len(args) == 4:
        index, exact = args[2], args[3]
        is_exact = exact["node_type"] == "Literal" and exact["value"] in (False, 0, 0.0)
        if is_exact and index["node_type"] == "Literal" and isinstance(index["value"], (int, float)):
            return args[0], args[1], args[1], int(index["value"]) - 1
        return None
    if name == "XLOOKUP" and len(args) == 3:
        return args[0], args[1], args[2], 0
    if name == "INDEX" and len(args) == 2 and args[1].get("name", "").upper() == "MATCH":
        match = args[1].get("args", [])
        if len(match) == 3 and match[2]["node_type"] == "Literal" and match[2]["value"] in (0, 0.0):
            return match[0], match[1], args[0], 0
    return None


def _function_type(name: str) -> str:
    if name in BOOLEAN_FUNCTIONS:
        return "boolean"
    if name in TEXT_FUNCTIONS:
        return "text"
    if name in DATE_FUNCTIONS:
        return "date"
    return "any" if name in ANY_FUNCTIONS else "number"


def collect_functions(node: Any, found: set[str]) -> None:
    if isinstance(node, dict):
        if node.get("node_type") == "Function":
            found.add(str(node["name"]).upper())
        for value in node.values():
            collect_functions(value, found)
    elif isinstance(node, list):
        for item in node:
            collect_functions(item, found)


def translate(formula: str, sheet: str, row: int, columns: Mapping[int, str]) -> Translation:
    """Translate one formula. `columns` maps each table column to its value type."""
    if formula.startswith("{"):
        return Translation(reasons=["arrayFormula"])
    try:
        ast = parse_formula(formula)
    except EngineError:
        return Translation(reasons=["unparsed"])
    functions: set[str] = set()
    collect_functions(ast, functions)
    translator = _Translator(sheet, row, columns)
    try:
        expr = translator.node(ast)
    except _Untranslatable as reason:
        return Translation(reasons=[str(reason)], functions=functions, lookups=_engine_lookups(ast, sheet, row, columns))
    return Translation(expr, list(translator.deps), [], functions, translator.lookups)


def _engine_lookups(node: Any, sheet: str, row: int, columns: Mapping[int, str]) -> list[Lookup]:
    """Lookups inside a formula that stays with the engine are still evidence of a relation (R-7)."""
    found: list[Lookup] = []
    if isinstance(node, dict):
        if node.get("node_type") == "Function" and str(node["name"]).upper() in LOOKUPS:
            translator = _Translator(sheet, row, columns)
            try:
                translator._lookup(str(node["name"]).upper(), node.get("args", []))
                found += translator.lookups
            except _Untranslatable:
                pass
        for value in node.values():
            found += _engine_lookups(value, sheet, row, columns)
    elif isinstance(node, list):
        for item in node:
            found += _engine_lookups(item, sheet, row, columns)
    return found
