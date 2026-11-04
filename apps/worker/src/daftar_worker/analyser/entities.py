"""R-6: one name retyped across rows or sheets. This proposes an entity; it never merges anything."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from openpyxl.utils import get_column_letter
from rapidfuzz import fuzz

from daftar_worker.analyser import explain
from daftar_worker.analyser.kinds import STATUS_HINT
from daftar_worker.analyser.regions import Table
from daftar_worker.analyser.workbook_view import SheetView
from daftar_worker.sheet.grid import a1_range, text_of
from daftar_worker.sheet.names import digits_in, fingerprint, same_with_initial, tokens


SIMILAR = 88
VERY_SIMILAR = 93
MIN_FUZZY_LENGTH = 5
MAX_FUZZY_NAMES = 2000
MIN_ROWS = 4
SHARED_COLUMN = 0.5
MIN_SHARED = 3
FUNCTIONAL = 0.95


@dataclass
class ColumnValues:
    sheet: str
    table: Table
    column: int
    label: str
    values: list[tuple[int, str]]  # row, text


def _candidates(views: list[SheetView]) -> list[ColumnValues]:
    found = []
    for view in views:
        if view.outcome == "notConverted":
            continue
        for table, labels, guesses in zip(view.layout.tables, view.labels, view.guesses, strict=True):
            for column, guess in guesses.items():
                if guess.type not in ("text", "choice") or guess.choice_source == "validationList":
                    continue
                label = labels.get(column, "")
                if STATUS_HINT.search(label):
                    continue
                values = []
                for row in table.data_rows():
                    cell = view.grid.get(row, column)
                    if cell is not None and cell.is_text:
                        values.append((row, text_of(cell)))
                # Similar addresses are different people, whatever their spelling distance.
                if sum("@" in text for _, text in values) * 2 > len(values):
                    continue
                if len(values) >= MIN_ROWS:
                    found.append(ColumnValues(view.grid.name, table, column, label, values))
    return found


def _group_columns(columns: list[ColumnValues]) -> list[list[ColumnValues]]:
    """Columns on different sheets that share most of their names hold the same thing."""
    keys = [{fingerprint(text) for _, text in column.values} for column in columns]
    parent = list(range(len(columns)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for left in range(len(columns)):
        for right in range(left + 1, len(columns)):
            if columns[left].sheet == columns[right].sheet:
                continue
            shared = len(keys[left] & keys[right])
            smaller = min(len(keys[left]), len(keys[right]))
            if shared >= MIN_SHARED and shared / smaller >= SHARED_COLUMN:
                parent[find(left)] = find(right)
    groups: dict[int, list[ColumnValues]] = defaultdict(list)
    for index, column in enumerate(columns):
        groups[find(index)].append(column)
    return list(groups.values())


def _close(left: str, right: str) -> float:
    """How alike two normalised names are, 0-100. Numbers must match: Client 1 isn't Client 2."""
    if digits_in(left) != digits_in(right):
        return 0.0
    if same_with_initial(left.split(), right.split()):
        return 88.0
    if min(len(left), len(right)) < MIN_FUZZY_LENGTH:
        return 0.0
    return float(fuzz.token_sort_ratio(left, right))


def cluster_names(names: Counter[str]) -> list[dict[str, Any]]:
    """Group spellings of one name. Returns clusters with two or more spellings."""
    by_key: dict[str, Counter[str]] = defaultdict(Counter)
    for name, count in names.items():
        by_key[fingerprint(name)][name] += count
    keys = sorted(by_key)
    parent = {key: key for key in keys}

    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    closeness: dict[tuple[str, str], float] = {}
    if len(keys) <= MAX_FUZZY_NAMES:
        blocks: dict[str, list[str]] = defaultdict(list)
        for key in keys:
            for word in key.split():
                blocks[word[:3]].append(key)
        for block in blocks.values():
            for index, left in enumerate(block):
                for right in block[index + 1 :]:
                    score = _close(left, right)
                    if score >= SIMILAR:
                        closeness[(min(left, right), max(left, right))] = score
                        parent[find(left)] = find(right)

    members: dict[str, list[str]] = defaultdict(list)
    for key in keys:
        members[find(key)].append(key)
    clusters = []
    for group in members.values():
        spellings: Counter[str] = Counter()
        for key in group:
            spellings.update(by_key[key])
        if len(spellings) < 2:
            continue
        ordered = sorted(spellings.items(), key=lambda item: (-item[1], item[0]))
        scores = [score for pair, score in closeness.items() if pair[0] in group and pair[1] in group]
        lowest = min(scores, default=100.0)
        clusters.append(
            {
                "canonical": ordered[0][0],
                "variants": [{"value": value, "count": count} for value, count in ordered],
                "match": "normalised" if len(group) == 1 else ("close" if lowest >= VERY_SIMILAR else "possible"),
            }
        )
    return sorted(clusters, key=lambda item: item["canonical"])


def _attributes(view: SheetView, table: Table, column: ColumnValues, guesses: dict[int, Any], labels: dict[int, str]) -> list[dict[str, str]]:
    """Other columns a retyped name determines: name to phone is the sign of a separate entity."""
    keys = {row: fingerprint(text) for row, text in column.values}
    found = []
    for other, guess in sorted(guesses.items()):
        if other == column.column or guess.type == "computed":
            continue
        seen: dict[str, Counter[str]] = defaultdict(Counter)
        for row, key in keys.items():
            cell = view.grid.get(row, other)
            if cell is not None:
                seen[key][text_of(cell)] += 1
        repeated = {key: values for key, values in seen.items() if sum(values.values()) >= 2}
        if not repeated:
            continue
        consistent = sum(values.most_common(1)[0][1] for values in repeated.values())
        total = sum(sum(values.values()) for values in repeated.values())
        all_values = {value for values in seen.values() for value in values}
        if consistent / total >= FUNCTIONAL and len(all_values) >= 2:
            found.append({"column": get_column_letter(other), "name": labels.get(other) or get_column_letter(other)})
    return found


def entity_findings(make: Any, views: list[SheetView]) -> list[dict[str, Any]]:
    by_sheet = {view.grid.name: view for view in views}
    findings = []
    for group in _group_columns(_candidates(views)):
        names: Counter[str] = Counter(text for column in group for _, text in column.values)
        distinct = len(names)
        total = sum(names.values())
        clusters = cluster_names(names)
        repeated = total > distinct
        attributes: list[dict[str, str]] = []
        if repeated:
            first = group[0]
            view = by_sheet[first.sheet]
            index = view.layout.tables.index(first.table)
            attributes = _attributes(view, first.table, first, view.guesses[index], view.labels[index])
        across_sheets = len({column.sheet for column in group}) > 1
        # R-6 is about one name retyped. What a column determines backs that up, but alone it fires
        # on any two columns that happen to move together, such as a weekday and its neighbour.
        if not (clusters or across_sheets):
            continue
        matches = {cluster["match"] for cluster in clusters}
        score = 0.65 if "possible" in matches else (0.75 if "close" in matches else 0.86)
        if not clusters:
            score = 0.7
        first = group[0]
        evidence = [
            a1_range(column.table.data_top, column.column, column.table.data_bottom, column.column)
            for column in group
            if column.sheet == first.sheet
        ]
        columns = [
            {"sheet": column.sheet, "column": get_column_letter(column.column), "name": column.label or get_column_letter(column.column)}
            for column in group
        ]
        findings.append(
            make(
                "entityMerge",
                first.sheet,
                evidence,
                {"name": first.label or get_column_letter(first.column), "columns": columns, "distinct": distinct, "rows": total, "clusters": clusters, "attributes": attributes},
                score,
                explain.entity_merge(first.label or get_column_letter(first.column), [column["sheet"] for column in columns], distinct, clusters),
                extra="|".join(sorted(f"{item['sheet']}!{item['column']}" for item in columns)),
            )
        )
    return findings


__all__ = ["cluster_names", "entity_findings", "tokens"]
