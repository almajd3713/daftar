"""Findings about formulas: computed fields, calculators, lookups as relations, and odd cells."""

from typing import Any

from openpyxl.utils import get_column_letter

from daftar_worker.analyser import explain
from daftar_worker.analyser.regions import Table
from daftar_worker.analyser.types import TypeGuess
from daftar_worker.formulas.calculators import Port, find_model, port_key
from daftar_worker.formulas.computed import MAX_LISTED_CELLS, ComputedColumn, find_computed
from daftar_worker.formulas.translate import field_key
from daftar_worker.sheet.grid import Grid, a1, a1_range


CELL_TYPES = {"percent": "percent", "decimal": "decimal", "date": "date", "boolean": "boolean", "text": "text"}
MAX_EVIDENCE = 40


def _score(column: ComputedColumn) -> float:
    if column.missing_functions:
        return 0.3  # The engine can't run it either: R-19 says flag it, never guess.
    coverage = column.matching / column.total
    base = 0.95 if column.expr is not None and column.checked else 0.8
    return round(base - (1 - coverage) * 1.0, 3)


def _computed_proposal(table: Table, column: ComputedColumn, label: str, guess: TypeGuess | None) -> dict[str, Any]:
    proposal: dict[str, Any] = {
        "table": table.rect.a1,
        "column": get_column_letter(column.column),
        "key": field_key(column.column),
        "name": label or get_column_letter(column.column),
        "excel": column.formula,
        "deps": column.deps,
        "store": True,
        "eval": "translated" if column.expr is not None else "engine",
        "coverage": {"matching": column.matching, "total": column.total},
        "functions": sorted(column.functions),
        "check": {"checked": column.checked, "agreed": column.agreed},
        "engineSupported": not column.missing_functions,
    }
    if column.expr is not None:
        proposal["expr"] = column.expr
    if column.reasons:
        proposal["reasons"] = column.reasons
    if column.missing_functions:
        proposal["missingFunctions"] = column.missing_functions
    if guess is not None and guess.result_type:
        proposal["resultType"] = guess.result_type
    return proposal


def table_formula_findings(
    make: Any,
    grid: Grid,
    table: Table,
    labels: dict[int, str],
    guesses: dict[int, TypeGuess],
    verify: bool,
) -> list[dict[str, Any]]:
    """`make` builds a finding, so C-2's shape stays in one place."""
    findings: list[dict[str, Any]] = []
    rows = table.data_rows()
    lookups: dict[tuple[int, str, int], set[int]] = {}
    for column in range(table.rect.left, table.rect.right + 1):
        found = find_computed(grid, column, rows, guesses, table.rect.left, table.rect.right, verify)
        if found is None:
            continue
        label = labels.get(column, "")
        letter = get_column_letter(column)
        evidence = a1_range(table.data_top, column, table.data_bottom, column)
        findings.append(
            make(
                "computedField",
                grid.name,
                [evidence],
                _computed_proposal(table, found, label, guesses.get(column)),
                _score(found),
                explain.computed_field(label, letter, found.formula, found.matching, found.total, found.expr is not None, found.missing_functions),
            )
        )
        if found.outliers:
            cells = found.outliers[:MAX_LISTED_CELLS]
            findings.append(
                make(
                    "anomaly",
                    grid.name,
                    cells,
                    {"kind": "inconsistentFormula", "table": table.rect.a1, "column": letter, "cells": cells, "count": len(found.outliers)},
                    0.7,
                    explain.inconsistent_formula(label, letter, cells, len(found.outliers)),
                    extra=letter,
                )
            )
        for lookup in found.lookups:
            lookups.setdefault((lookup.from_column, lookup.to_sheet, lookup.key_column), set()).add(lookup.result_column)
    for (from_column, to_sheet, key_column), results in sorted(lookups.items()):
        source = get_column_letter(from_column)
        target = get_column_letter(key_column)
        findings.append(
            make(
                "relation",
                grid.name,
                [a1_range(table.data_top, from_column, table.data_bottom, from_column)],
                {
                    "from": {"sheet": grid.name, "column": source},
                    "to": {"sheet": to_sheet, "column": target},
                    "evidence": "lookupFormula",
                    "resultColumns": sorted(get_column_letter(column) for column in results),
                },
                0.9,
                explain.relation_from_lookup(grid.name, source, to_sheet, target),
                extra=f"{to_sheet}!{target}",
            )
        )
    return findings


def _port(prefix: str, port: Port, input_port: bool) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "key": port_key(prefix, port),
        "name": port.label or a1(port.row, port.column),
        "type": CELL_TYPES.get(port.kind, "text"),
        "sheet": port.sheet,
        "cell": a1(port.row, port.column),
    }
    if input_port:
        entry["default"] = port.value
    return entry


def calculator_findings(make: Any, grid: Grid, grids: dict[str, Grid], verify: bool) -> list[dict[str, Any]]:
    model = find_model(grid, grids)
    if model is None:
        return []
    ports = [a1(port.row, port.column) for port in [*model.inputs, *model.outputs]]
    proposal: dict[str, Any] = {
        "inputs": [_port("input", port, True) for port in model.inputs],
        "outputs": [_port("output", port, False) for port in model.outputs],
        "cells": [
            {"sheet": sheet, "ref": a1(row, column), **({"f": formula} if formula is not None else {"v": value})}
            for sheet, row, column, value, formula in model.cells
        ],
        "testCases": [],
    }
    if verify:
        # What Excel stored for these inputs: the case the calculator must reproduce.
        proposal["testCases"] = [
            {
                "inputs": {port_key("input", port): port.value for port in model.inputs},
                "outputs": {port_key("output", port): port.value for port in model.outputs},
            }
        ]
    labelled = sum(1 for port in [*model.inputs, *model.outputs] if port.label)
    score = 0.55 + 0.35 * labelled / max(len(ports), 1)
    return [
        make(
            "calculator",
            grid.name,
            ports[:MAX_EVIDENCE],
            proposal,
            score,
            explain.calculator(grid.name, [port.label or a1(port.row, port.column) for port in model.inputs], [port.label or a1(port.row, port.column) for port in model.outputs]),
        )
    ]
