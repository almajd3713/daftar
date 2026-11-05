"""Read what an analysis claims. This is the one place that knows the C-2 finding shapes.

Rejected findings don't count. Everything else does, whatever its confidence: the score measures
what the analyser proposes, before a person reviews it.
"""

from dataclasses import dataclass, field
import re
from typing import Any

from openpyxl.utils import range_boundaries


COLUMN = re.compile(r"^[A-Z]{1,3}")


@dataclass(frozen=True)
class PredictedField:
    sheet: str
    column: str
    low_row: int
    high_row: int
    type: str


@dataclass
class Predictions:
    outcomes: dict[str, str] = field(default_factory=dict)
    tables: dict[str, list[str]] = field(default_factory=dict)
    header_rows: set[tuple[str, int]] = field(default_factory=set)
    fields: list[PredictedField] = field(default_factory=list)
    relations: set[tuple[str, str, str, str]] = field(default_factory=set)
    period_pairs: set[tuple[str, str]] = field(default_factory=set)
    # Sheet and cell to the value it evaluated to, for the formula metric.
    results: dict[tuple[str, str], Any] = field(default_factory=dict)


def sheet_pairs(names: list[str]) -> set[tuple[str, str]]:
    """Sheets grouped as one table, as pairs, so a partly right group gets partial credit."""
    return {(left, right) for index, left in enumerate(names) for right in names[index + 1 :]}


def _is_rejected(finding: dict[str, Any]) -> bool:
    return bool(finding.get("decision", {}).get("status") == "rejected")


def from_analysis(analysis: dict[str, Any], parity: dict[str, Any] | None = None) -> Predictions:
    predictions = Predictions()
    for sheet in analysis.get("sheets", []):
        predictions.outcomes[sheet["name"]] = sheet["outcome"]
    for finding in analysis.get("findings", []):
        if _is_rejected(finding):
            continue
        kind = finding["kind"]
        sheet = finding.get("sheet", "")
        evidence = finding.get("evidence", [])
        proposal = finding.get("proposal") or {}
        if kind == "table" and evidence:
            predictions.tables.setdefault(sheet, []).append(evidence[0])
        elif kind == "header":
            for item in evidence:
                _, low, _, high = range_boundaries(item)
                predictions.header_rows.update((sheet, row) for row in range(int(low), int(high) + 1))
        elif kind == "fieldType" and evidence:
            low_column, low, _, high = range_boundaries(evidence[0])
            match = COLUMN.match(evidence[0])
            predictions.fields.append(
                PredictedField(
                    sheet,
                    match.group(0) if match else str(low_column),
                    int(low),
                    int(high),
                    proposal.get("type", ""),
                )
            )
        elif kind == "relation":
            source, target = proposal.get("from", {}), proposal.get("to", {})
            predictions.relations.add(
                (source.get("sheet"), source.get("column"), target.get("sheet"), target.get("column"))
            )
        elif kind == "periodUnion":
            names = sorted(tab["sheet"] for tab in proposal.get("tabs", []))
            predictions.period_pairs.update(sheet_pairs(names))
    for result in (parity or {}).get("results", []):
        predictions.results[(result["sheet"], result["ref"])] = result["value"]
    return predictions


def label_as_predictions(label: dict[str, Any]) -> Predictions:
    """Read a label as if it were a prediction, so one labeller is scored the way Daftar is."""
    out = Predictions()
    groups: dict[str, list[str]] = {}
    for sheet in label["sheets"]:
        name = sheet["name"]
        out.outcomes[name] = sheet["kind"]
        if sheet.get("periodGroup"):
            groups.setdefault(sheet["periodGroup"], []).append(name)
        if sheet["tables"]:
            out.tables[name] = [table["range"] for table in sheet["tables"]]
        for table in sheet["tables"]:
            _, low, _, high = range_boundaries(table["range"])
            out.header_rows.update((name, number) for number in table["headerRows"])
            out.fields.extend(PredictedField(name, item["column"], int(low), int(high), item["type"]) for item in table["fields"])
    for names in groups.values():
        out.period_pairs.update(sheet_pairs(sorted(names)))
    for item in label["relations"]:
        out.relations.add((item["from"]["sheet"], item["from"]["column"], item["to"]["sheet"], item["to"]["column"]))
    return out
