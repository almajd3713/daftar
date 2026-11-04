"""R-7: relations from validation lists and value inclusion, under a snowflake constraint.

Lookup formulas give their relations in formula_findings.py, and they're high confidence. Inclusion
between key columns is only ever medium: shared values can be a coincidence.
"""

from dataclasses import dataclass
import re
from typing import Any

from openpyxl.utils import get_column_letter
from rapidfuzz import fuzz

from daftar_worker.analyser import explain
from daftar_worker.analyser.regions import Table
from daftar_worker.analyser.workbook_view import SheetView
from daftar_worker.sheet.grid import a1_range, text_of
from daftar_worker.sheet.names import fingerprint


INCLUSION = 0.95
MIN_KEYS = 3
MIN_KEYS_UNNAMED = 5
SAME_NAME = 0.8
COPY_OF_TABLE = 80
MAX_MEDIUM = 0.84
KEY_TYPES = {"text", "integer", "choice", "phone", "email"}
ID_HINT = re.compile(r"\b(id|code|n°|no|num|numéro|réf|ref|matricule|رقم|الرقم|رمز)\b", re.IGNORECASE)


@dataclass
class Profile:
    sheet: str
    table: Table
    column: int
    label: str
    kind: str
    values: list[str]

    @property
    def distinct(self) -> set[str]:
        return set(self.values)

    @property
    def is_unique(self) -> bool:
        return len(self.values) >= MIN_KEYS and len(self.distinct) == len(self.values)


def _profiles(views: list[SheetView]) -> list[Profile]:
    found = []
    for view in views:
        if view.outcome == "notConverted":
            continue
        for table, labels, guesses in zip(view.layout.tables, view.labels, view.guesses, strict=True):
            for column, guess in guesses.items():
                if guess.type not in KEY_TYPES:
                    continue
                values = []
                for row in table.data_rows():
                    cell = view.grid.get(row, column)
                    if cell is not None:
                        values.append(fingerprint(text_of(cell)))
                if values:
                    found.append(Profile(view.grid.name, table, column, labels.get(column, ""), guess.type, values))
    return found


def _looks_like_a_counter(profile: Profile) -> bool:
    """1, 2, 3... matches any other numbered list, so it needs its name to back it up."""
    if profile.kind != "integer":
        return False
    return not ID_HINT.search(profile.label)


def _name_similarity(source: Profile, target: Profile) -> float:
    if not source.label or not target.label:
        return 0.0
    return fuzz.ratio(fingerprint(source.label), fingerprint(target.label)) / 100


def _could_be_key(source: Profile, target: Profile, labels: dict[tuple[str, Any], list[str]]) -> bool:
    """Shared values alone are weak evidence. The target must look like a key, and not a copy."""
    if len(source.distinct) < MIN_KEYS_UNNAMED and _name_similarity(source, target) < SAME_NAME:
        return False
    own = labels.get((source.sheet, source.table.rect), [])
    other = labels.get((target.sheet, target.table.rect), [])
    # "Result I got" and "Result I expected": one table twice isn't a relation.
    if own and other and fuzz.token_sort_ratio(" ".join(own), " ".join(other)) >= COPY_OF_TABLE:
        return False
    is_first_column = target.column == target.table.rect.left
    return is_first_column or bool(ID_HINT.search(target.label)) or _name_similarity(source, target) >= SAME_NAME


def _score(source: Profile, target: Profile, inclusion: float) -> float:
    score = 0.6
    if inclusion == 1.0:
        score += 0.08
    score += 0.16 * _name_similarity(source, target)
    return min(score, MAX_MEDIUM)


def _creates_cycle(edges: list[tuple[str, str]], source: str, target: str) -> bool:
    """A snowflake has no loops: following links from `target` must not lead back to `source`."""
    pending, seen = [target], set()
    while pending:
        node = pending.pop()
        if node == source:
            return True
        if node not in seen:
            seen.add(node)
            pending.extend(to for frm, to in edges if frm == node)
    return False


def relation_findings(
    make: Any, views: list[SheetView], existing: list[dict[str, Any]], periods: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    series: dict[str, int] = {}
    for number, period in enumerate(periods):
        for tab in period["proposal"]["tabs"]:
            series[tab["sheet"]] = number
    # What's already known, from lookups, counts first: inclusion must not contradict it.
    taken = {
        (item["proposal"]["from"]["sheet"], item["proposal"]["from"]["column"]): item["proposal"]["to"]
        for item in existing
        if item["kind"] == "relation"
    }
    edges = [(item["proposal"]["from"]["sheet"], item["proposal"]["to"]["sheet"]) for item in existing if item["kind"] == "relation"]

    # A validation list drawn from another sheet says what the column may hold.
    for view in views:
        if view.outcome == "notConverted":
            continue
        for table, guesses in zip(view.layout.tables, view.guesses, strict=True):
            for column, guess in sorted(guesses.items()):
                if guess.target is None:
                    continue
                letter = get_column_letter(column)
                if (view.grid.name, letter) in taken:
                    continue
                taken[(view.grid.name, letter)] = guess.target
                edges.append((view.grid.name, guess.target["sheet"]))
                findings.append(
                    make(
                        "relation",
                        view.grid.name,
                        [a1_range(table.data_top, column, table.data_bottom, column)],
                        {"from": {"sheet": view.grid.name, "column": letter}, "to": dict(guess.target), "evidence": "validationList"},
                        0.9,
                        explain.relation_from_validation(view.grid.name, letter, guess.target["sheet"], guess.target["column"]),
                        extra=f"{guess.target['sheet']}!{guess.target['column']}",
                    )
                )

    profiles = _profiles(views)
    table_labels = {
        (view.grid.name, table.rect): [fingerprint(label) for _, label in sorted(labels.items())]
        for view in views
        for table, labels in zip(view.layout.tables, view.labels, strict=True)
    }
    candidates: list[tuple[float, Profile, Profile, float]] = []
    for source in profiles:
        keys = source.distinct
        if len(keys) < MIN_KEYS or _looks_like_a_counter(source):
            continue
        for target in profiles:
            if target.sheet == source.sheet or not target.is_unique or len(target.distinct) < len(keys):
                continue
            # January's ids are all in March too, but those tabs are one table split by month.
            if source.sheet in series and series[source.sheet] == series.get(target.sheet):
                continue
            if _looks_like_a_counter(target):
                continue
            inclusion = len(keys & target.distinct) / len(keys)
            if inclusion >= INCLUSION and _could_be_key(source, target, table_labels):
                candidates.append((_score(source, target, inclusion), source, target, inclusion))

    # Highest scores choose first; each column links to one target and the graph stays loop-free.
    candidates.sort(key=lambda item: (-item[0], item[1].sheet, item[1].column, item[2].sheet, item[2].column))
    for score, source, target, inclusion in candidates:
        letter = get_column_letter(source.column)
        if (source.sheet, letter) in taken or _creates_cycle(edges, source.sheet, target.sheet):
            continue
        target_letter = get_column_letter(target.column)
        taken[(source.sheet, letter)] = {"sheet": target.sheet, "column": target_letter}
        edges.append((source.sheet, target.sheet))
        findings.append(
            make(
                "relation",
                source.sheet,
                [a1_range(source.table.data_top, source.column, source.table.data_bottom, source.column)],
                {"from": {"sheet": source.sheet, "column": letter}, "to": {"sheet": target.sheet, "column": target_letter}, "evidence": "keyInclusion", "inclusion": round(inclusion, 3)},
                score,
                explain.relation_from_inclusion(source.sheet, letter, target.sheet, target_letter, inclusion),
                extra=f"{target.sheet}!{target_letter}",
            )
        )
    return findings
