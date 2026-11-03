"""The rules-only analyser: turn a C-1 snapshot into a C-2 analysis."""

from collections import Counter
from collections.abc import Callable
import hashlib
from typing import Any

from openpyxl.utils import get_column_letter

from daftar_worker.analyser import explain
from daftar_worker.analyser.grid import Grid, a1_range
from daftar_worker.analyser.kinds import referenced_sheets, resolve_validation, score_sheet
from daftar_worker.analyser.regions import SheetLayout, Table, detect_layout, flatten_headers
from daftar_worker.analyser.types import TypeGuess, infer_type


RULES_VERSION = "1"
# D-18's starting points; WP-8 tunes them on the dev pool.
HIGH_CONFIDENCE = 0.85
LOW_CONFIDENCE = 0.6
TOTAL_ROW_SCORES = {"formula": 0.95, "keyword": 0.8, "arithmetic": 0.7, "afterTotal": 0.65}
KIND_ORDER = ("sheetKind", "table", "header", "totalRow", "fieldType", "choiceList", "unsupported")
ProgressCallback = Callable[[float], None]


def confidence_level(score: float) -> str:
    if score >= HIGH_CONFIDENCE:
        return "high"
    return "low" if score < LOW_CONFIDENCE else "medium"


def finding_id(kind: str, sheet: str | None, evidence: list[str], extra: str = "") -> str:
    """Stable across reruns: a hash of the kind and normalised evidence (R-15)."""
    normal = "|".join(sorted(item.replace("$", "").upper() for item in evidence))
    return hashlib.sha256(f"{kind}\0{sheet or ''}\0{normal}\0{extra}".encode()).hexdigest()[:24]


def _finding(
    kind: str,
    sheet: str | None,
    evidence: list[str],
    proposal: dict[str, Any],
    score: float,
    explanation: dict[str, str],
    alternatives: list[dict[str, Any]] | None = None,
    extra: str = "",
) -> dict[str, Any]:
    score = round(score, 3)
    return {
        "id": finding_id(kind, sheet, evidence, extra),
        "kind": kind,
        "sheet": sheet,
        "evidence": evidence,
        "proposal": proposal,
        "alternatives": alternatives or [],
        "confidence": {"level": confidence_level(score), "score": score, "source": "rules"},
        "explanation": explanation,
        "decision": {"status": "pending"},
    }


def _field_cells(grid: Grid, table: Table, column: int) -> list[Any]:
    found = (grid.get(row, column) for row in table.data_rows())
    return [cell for cell in found if cell is not None]


def _table_guesses(
    grid: Grid,
    table: Table,
    labels: dict[int, str],
    grids: dict[str, Grid],
    defined: dict[str, str],
) -> dict[int, TypeGuess]:
    guesses: dict[int, TypeGuess] = {}
    for column in range(table.rect.left, table.rect.right + 1):
        validation = resolve_validation(
            grid.sheet["validations"], column, table.data_top, table.data_bottom, grids, defined, grid.name
        )
        guess = infer_type(_field_cells(grid, table, column), labels.get(column, ""), validation)
        if guess is not None:
            guesses[column] = guess
    return guesses


def _table_findings(
    grid: Grid, table: Table, labels: dict[int, str], guesses: dict[int, TypeGuess]
) -> list[dict[str, Any]]:
    name = grid.name
    rect = table.rect
    findings = [
        _finding(
            "table",
            name,
            [rect.a1],
            {
                "range": rect.a1,
                "dataRange": table.data_range,
                "headerRows": table.header_rows,
                "totalRows": [item.row for item in table.total_rows],
                "titleRows": table.title_rows,
                "noteRows": table.note_rows,
            },
            # A table with no header is a guess, and it should be reviewed first.
            0.9 if table.header_rows else 0.55,
            explain.table(name, rect.a1, len(table.data_rows()), rect.width),
        )
    ]
    if table.header_rows:
        evidence = a1_range(table.header_rows[0], rect.left, table.header_rows[-1], rect.right)
        findings.append(
            _finding(
                "header",
                name,
                [evidence],
                {
                    "table": rect.a1,
                    "rows": table.header_rows,
                    "labels": [
                        {"column": get_column_letter(column), "label": label}
                        for column, label in sorted(labels.items())
                    ],
                },
                table.header_confidence,
                explain.header(name, table.header_rows, len(labels)),
            )
        )
    for total in table.total_rows:
        findings.append(
            _finding(
                "totalRow",
                name,
                [a1_range(total.row, rect.left, total.row, rect.right)],
                {
                    "table": rect.a1,
                    "row": total.row,
                    "source": total.source,
                    "aggregates": [
                        {"column": get_column_letter(column), "function": function}
                        for column, function in total.aggregates
                    ],
                },
                TOTAL_ROW_SCORES[total.source],
                explain.total_row(name, total.row, total.source, len(total.aggregates)),
            )
        )
    for column, guess in sorted(guesses.items()):
        letter = get_column_letter(column)
        evidence = a1_range(table.data_top, column, table.data_bottom, column)
        label = labels.get(column, "")
        proposal: dict[str, Any] = {
            "table": rect.a1,
            "column": letter,
            "name": label or letter,
            "type": guess.type,
        }
        if guess.result_type:
            proposal["resultType"] = guess.result_type
        if guess.target:
            proposal["target"] = guess.target
        if column in grid.hidden_columns:
            proposal["hidden"] = True
        findings.append(
            _finding(
                "fieldType",
                name,
                [evidence],
                proposal,
                guess.score,
                explain.field_type(label, letter, guess.type, guess.reason, guess.matched, guess.total),
                guess.alternatives,
            )
        )
        if guess.choices:
            source = guess.choice_source or "values"
            findings.append(
                _finding(
                    "choiceList",
                    name,
                    [evidence],
                    {
                        "table": rect.a1,
                        "column": letter,
                        "source": source,
                        "multiple": guess.type == "multichoice",
                        "values": guess.choices,
                    },
                    guess.score,
                    explain.choice_list(label, letter, guess.choices, source),
                )
            )
    return findings


def _sheet_findings(
    grid: Grid,
    layout: SheetLayout,
    grids: dict[str, Grid],
    defined: dict[str, str],
    unsupported: list[dict[str, Any]],
    references: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    labels_by_table = [flatten_headers(grid, table) for table in layout.tables]
    guesses_by_table = [
        _table_guesses(grid, table, labels, grids, defined)
        for table, labels in zip(layout.tables, labels_by_table, strict=True)
    ]
    kind = score_sheet(grid, layout, guesses_by_table, labels_by_table, unsupported, references)
    dimension = grid.sheet["dimension"]
    proposal: dict[str, Any] = {"outcome": kind.outcome}
    if kind.reason:
        proposal["reason"] = kind.reason
    alternatives = [
        {"outcome": name, "score": round(value, 3)}
        for name, value in sorted(kind.scores.items(), key=lambda item: (-item[1], item[0]))
        if name != kind.outcome and value > 0
    ]
    findings = [
        _finding(
            "sheetKind",
            grid.name,
            [dimension] if dimension else [],
            proposal,
            kind.score,
            explain.sheet_kind(grid.name, kind.outcome, kind.reason, kind.facts),
            alternatives,
        )
    ]
    # Sheets we won't convert get no table findings: there would be nothing to act on.
    if kind.outcome != "notConverted":
        for table, labels, guesses in zip(layout.tables, labels_by_table, guesses_by_table, strict=True):
            findings += _table_findings(grid, table, labels, guesses)
    entry: dict[str, Any] = {
        "name": grid.name,
        "outcome": kind.outcome,
        "findingIds": [item["id"] for item in findings],
    }
    if kind.reason:
        entry["reason"] = kind.reason
    return entry, findings


def _unsupported_findings(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    counts = Counter(
        (item["kind"], item.get("sheet"), item.get("ref")) for item in snapshot["unsupported"]
    )
    findings = []
    for (kind, sheet, ref), count in sorted(counts.items(), key=lambda item: tuple(map(str, item[0]))):
        findings.append(
            _finding(
                "unsupported",
                sheet,
                [ref] if ref else [],
                {"kind": kind, "count": count},
                0.99,
                explain.unsupported(kind, sheet, ref, count),
                extra=kind,
            )
        )
    return findings


def analyze_snapshot(
    snapshot: dict[str, Any], progress: ProgressCallback | None = None
) -> dict[str, Any]:
    """Rules only (R-11). The same snapshot always gives the same analysis."""
    grids = {sheet["name"]: Grid(sheet) for sheet in snapshot["sheets"]}
    defined = {item["name"]: item["ref"] for item in snapshot["definedNames"] if "scope" not in item}
    references = referenced_sheets(snapshot)
    sheets: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    total = max(len(grids), 1)
    for position, grid in enumerate(grids.values(), start=1):
        entry, sheet_findings = _sheet_findings(
            grid,
            detect_layout(grid),
            grids,
            defined,
            snapshot["unsupported"],
            references.get(grid.name, 0),
        )
        sheets.append(entry)
        findings += sheet_findings
        if progress:
            progress(position / total)
    findings += _unsupported_findings(snapshot)
    by_sheet = {name: index for index, name in enumerate(grids)}
    findings.sort(
        key=lambda item: (
            by_sheet.get(item["sheet"], len(by_sheet)),
            KIND_ORDER.index(item["kind"]),
            item["evidence"],
            item["id"],
        )
    )
    return {
        "analysisVersion": 1,
        "snapshotSha256": snapshot["source"]["sha256"],
        "engine": {"rulesVersion": RULES_VERSION},
        "sheets": sheets,
        "findings": findings,
    }


__all__ = ["RULES_VERSION", "analyze_snapshot", "confidence_level", "finding_id"]
