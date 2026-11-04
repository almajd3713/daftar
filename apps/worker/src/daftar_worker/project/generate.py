"""Turn accepted findings into a C-3 spec and seed data. Nothing else reaches the spec (R-12)."""

from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any
import unicodedata

from openpyxl.utils import column_index_from_string, get_column_letter, range_boundaries

from daftar_spec import format_errors, validate_spec
from daftar_worker.analyser.periods import MONTHS, YEAR
from daftar_worker.sheet.grid import Grid, text_of
from daftar_worker.sheet.names import fingerprint
from daftar_worker.sheet.values import convert_value


SPEC_VERSION = "1.0.0"
ACCEPTED = ("accepted", "edited")
KIND_TO_ENTITY = {"register": "register", "ledger": "ledger", "tracker": "tracker", "referenceList": "reference"}
SENSITIVE = re.compile(r"\b(co[ûu]ts?|marges?|achats?|b[ée]n[ée]fices?|cost|margin|profit)\b|تكلفة|هامش|ربح|شراء", re.IGNORECASE)
PERSONAL = re.compile(
    r"\b(noms?|pr[ée]noms?|parents?|clients?|[ée]l[èe]ves?|adresses?|naissance|employ[ée]s?|contacts?)\b"
    r"|اسم|الاسم|لقب|زبون|الزبون|ولي|عنوان|ميلاد",
    re.IGNORECASE,
)
ID_HINT = re.compile(r"\b(id|code|n°|no|num|numéro|réf|ref|matricule|reçu)\b|رقم|رمز", re.IGNORECASE)
DEFAULT_RETENTION_MONTHS = 36
RETENTION_BASIS = {
    "fr": "Durée proposée par défaut : à confirmer avec le responsable du traitement.",
    "ar": "مدة مقترحة افتراضيا: يجب تأكيدها مع المسؤول عن المعالجة.",
}
ROLE_LABELS = {
    "owner": {"fr": "Propriétaire", "ar": "المالك"},
    "staff": {"fr": "Employé", "ar": "موظف"},
    "accountant": {"fr": "Comptable", "ar": "محاسب"},
    "viewer": {"fr": "Lecteur", "ar": "قارئ"},
}
ROLE_ACTIONS = {
    "owner": ["read", "create", "update", "delete", "export", "import", "revert"],
    "staff": ["read", "create", "update"],
    "accountant": ["read", "export"],
    "viewer": ["read"],
}
ROLE_LEVEL = {"owner": 1, "staff": 0, "accountant": 1, "viewer": 0}
STATE_COLOURS = ("#6B7280", "#E0A030", "#3B82F6", "#2F9E60", "#D64545", "#8B5CF6")
MAX_KEY = 63


class GenerationError(ValueError):
    """Accepted findings that can't make a valid spec. Each problem is on its own line."""


def slug(text: str, fallback: str) -> str:
    """A key: `^[a-z][a-z0-9_]{0,62}$`, the only source of database identifiers. Never raw text."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    plain = re.sub(r"[^a-z0-9]+", "_", plain).strip("_")
    if not plain or not plain[0].isalpha():
        plain = f"{fallback}_{plain}".strip("_") if plain else fallback
    return plain[:MAX_KEY].rstrip("_")


def _unique(key: str, taken: set[str]) -> str:
    candidate = key
    number = 2
    while candidate in taken:
        suffix = f"_{number}"
        candidate = key[: MAX_KEY - len(suffix)] + suffix
        number += 1
    taken.add(candidate)
    return candidate


def _two(label: dict[str, str] | None, name: str) -> dict[str, str]:
    """R-11: with no model's names, the cleaned header stands in for both languages."""
    if label:
        return {"fr": label["fr"], "ar": label["ar"]}
    clean = " ".join(name.split()) or "?"
    return {"fr": clean, "ar": clean}


def _accepted(finding: dict[str, Any]) -> bool:
    return bool(finding["decision"]["status"] in ACCEPTED)


def _proposal(finding: dict[str, Any]) -> dict[str, Any]:
    """What a person decided: an edit's values win over what the analyser proposed."""
    proposal = dict(finding["proposal"])
    value = finding["decision"].get("value")
    if finding["decision"]["status"] == "edited" and isinstance(value, dict):
        proposal.update(value)
    return proposal


def _provenance(finding: dict[str, Any], sha256: str) -> dict[str, Any] | None:
    evidence = finding.get("evidence") or []
    if not evidence or not finding.get("sheet"):
        return None
    decision = finding["decision"]
    return {
        "workbookSha256": sha256,
        "sheet": finding["sheet"],
        "range": evidence[0],
        "detector": finding["kind"],
        "confidence": {"level": finding["confidence"]["level"], "score": finding["confidence"]["score"]},
        "decision": decision["status"],
        "decidedBy": decision.get("by") or "unknown",
        "decidedAt": decision.get("at") or "1970-01-01T00:00:00+00:00",
    }


@dataclass
class TableInfo:
    sheet: str
    table: dict[str, Any]
    entity_key: str
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)  # Column letter to spec field.


@dataclass
class Report:
    """What the generator had to do about, for a person to see before anything is delivered."""

    entities: int = 0
    rows: Counter[str] = field(default_factory=Counter)
    bad_values: list[dict[str, Any]] = field(default_factory=list)
    parity_failures: list[dict[str, Any]] = field(default_factory=list)
    questions: list[dict[str, Any]] = field(default_factory=list)


def _level_of(name: str) -> int:
    return 1 if SENSITIVE.search(name) else 0


def _choices(values: list[dict[str, Any]], colours: dict[str, str], taken: set[str] | None = None) -> list[dict[str, Any]]:
    used = taken if taken is not None else set()
    out = []
    for position, item in enumerate(values):
        text = str(item["value"])
        choice: dict[str, Any] = {
            "key": _unique(slug(text, f"choice_{position + 1}"), used),
            "label": {"fr": text, "ar": text},
            "source": text,
        }
        if text in colours:
            choice["colour"] = colours[text]
        out.append(choice)
    return out


def _rename_expr(expr: Any, keys: dict[str, str]) -> Any:
    """`col_b` to the spec's key, in an expression tree."""
    if isinstance(expr, list):
        return [_rename_expr(item, keys) for item in expr]
    if not isinstance(expr, dict):
        return expr
    out = {name: _rename_expr(value, keys) for name, value in expr.items()}
    if out.get("kind") == "field":
        out["field"] = keys.get(out["field"], out["field"])
    return out


def _uses_related(expr: Any) -> bool:
    if isinstance(expr, dict):
        return expr.get("kind") == "related" or any(_uses_related(value) for value in expr.values())
    if isinstance(expr, list):
        return any(_uses_related(item) for item in expr)
    return False


def _base_field(key: str, label: dict[str, str], name: str) -> dict[str, Any]:
    entry: dict[str, Any] = {"key": key, "label": label}
    if _level_of(name):
        entry["level"] = 1
    return entry


class Generator:
    def __init__(self, analysis: dict[str, Any], snapshot: dict[str, Any], parity: dict[str, Any] | None = None) -> None:
        self.analysis = analysis
        self.snapshot = snapshot
        self.parity = parity or {}
        self.sha256 = snapshot["source"]["sha256"]
        self.grids = {sheet["name"]: Grid(sheet) for sheet in snapshot["sheets"]}
        self.accepted = [finding for finding in analysis["findings"] if _accepted(finding)]
        self.report = Report()
        self.entity_keys: set[str] = set()
        self.entities: list[dict[str, Any]] = []
        self.mappings: list[dict[str, Any]] = []
        self.infos: dict[tuple[str, str], TableInfo] = {}
        self.seed: dict[str, list[dict[str, Any]]] = {}
        self.workflows: list[dict[str, Any]] = []
        self.relation_ends: set[tuple[str, str]] = set()

    def _of_kind(self, kind: str, sheet: str | None = None) -> list[dict[str, Any]]:
        return [item for item in self.accepted if item["kind"] == kind and (sheet is None or item["sheet"] == sheet)]

    def _period_tabs(self) -> dict[str, dict[str, Any]]:
        """Each accepted series, by the sheet name of every tab in it."""
        tabs: dict[str, dict[str, Any]] = {}
        for finding in self._of_kind("periodUnion"):
            proposal = _proposal(finding)
            for tab in proposal["tabs"]:
                tabs[tab["sheet"]] = finding
        return tabs

    def _outcome(self, sheet: str) -> str | None:
        for finding in self._of_kind("sheetKind", sheet):
            return str(_proposal(finding)["outcome"])
        return None

    def _colours_of(self, sheet: str, table: str, column: str) -> dict[str, str]:
        for finding in self._of_kind("statusColours", sheet):
            proposal = _proposal(finding)
            if proposal["table"] == table and proposal["column"] == column:
                return {str(item["value"]): item["colour"] for item in proposal["choices"] if item["value"] is not None}
        return {}

    def _choice_finding(self, sheet: str, table: str, column: str) -> dict[str, Any] | None:
        for finding in self._of_kind("choiceList", sheet):
            proposal = _proposal(finding)
            if proposal["table"] == table and proposal["column"] == column:
                return proposal
        return None

    def _computed_finding(self, sheet: str, table: str, column: str) -> dict[str, Any] | None:
        for finding in self._of_kind("computedField", sheet):
            proposal = _proposal(finding)
            if proposal["table"] == table and proposal["column"] == column:
                return finding
        return None

    def _failed_parity(self, sheet: str, evidence: str) -> list[str]:
        """R-19: cells where the engine disagrees with Excel. This column can't be a computed field."""
        results = self.parity.get("mismatches", {})
        left, top, _, bottom = (int(part) for part in range_boundaries(evidence))
        letter = get_column_letter(left)
        return [
            ref
            for ref in results.get(sheet, [])
            if ref.startswith(letter) and ref[len(letter) :].isdigit() and top <= int(ref[len(letter) :]) <= bottom
        ]

    def _field(self, sheet: str, table_proposal: dict[str, Any], finding: dict[str, Any], taken: set[str]) -> dict[str, Any] | None:
        proposal = _proposal(finding)
        letter = proposal["column"]
        table = table_proposal["range"]
        name = proposal["name"]
        key = _unique(slug(name, f"col_{letter.lower()}"), taken)
        label = _two(proposal.get("label"), name)
        entry = _base_field(key, label, name)
        kind = proposal["type"]
        provenance = _provenance(finding, self.sha256)
        if provenance:
            entry["provenance"] = provenance
        if kind == "computed":
            return self._computed_or_value(sheet, table, letter, finding, entry, proposal)
        if kind in ("choice", "multichoice"):
            choices = self._choice_finding(sheet, table, letter)
            if choices is None or not choices["values"]:
                entry["type"] = "text"
                return entry
            entry["type"] = kind
            entry["choices"] = _choices(choices["values"], self._colours_of(sheet, table, letter))
            return entry
        if kind == "link":
            entry["type"] = "text"  # A relation finding makes it a link, if that was accepted too.
            return entry
        entry["type"] = kind
        if kind in ("money", "decimal"):
            entry["precision"] = 2
        return entry

    def _computed_or_value(
        self, sheet: str, table: str, letter: str, finding: dict[str, Any], entry: dict[str, Any], proposal: dict[str, Any]
    ) -> dict[str, Any]:
        result_type = proposal.get("resultType") or "decimal"
        computed = self._computed_finding(sheet, table, letter)
        plain = {"integer": "integer", "decimal": "decimal", "money": "money", "percent": "percent", "text": "text", "date": "date", "datetime": "datetime", "boolean": "boolean"}[result_type]
        if computed is None:
            # Not accepted as a formula: its stored values become plain data, which is honest.
            entry["type"] = plain
            return entry
        evidence = computed["evidence"][0]
        wrong = self._failed_parity(sheet, evidence)
        details = _proposal(computed)
        if wrong or details.get("engineSupported") is False:
            self.report.parity_failures.append(
                {
                    "sheet": sheet,
                    "column": letter,
                    "formula": details["excel"],
                    "cells": wrong[:20],
                    "count": len(wrong),
                    "missingFunctions": details.get("missingFunctions", []),
                }
            )
            entry["type"] = plain  # R-19: keep Excel's own results as data, never a wrong formula.
            return entry
        entry["type"] = "computed"
        entry["resultType"] = result_type
        entry["computed"] = {"eval": details["eval"], "excel": details["excel"], "deps": details["deps"], "store": True}
        if details["eval"] == "translated":
            entry["computed"]["expr"] = details["expr"]
        return entry

    def _key_columns(self, fields: list[dict[str, Any]], letters: dict[str, str], unique: set[str]) -> list[str]:
        inputs = [item for item in fields if item["type"] != "computed"]
        named = [item["key"] for item in inputs if ID_HINT.search(item["label"]["fr"]) and item["key"] in unique]
        if named:
            return named[:1]
        only = [item["key"] for item in inputs if item["key"] in unique]
        if only:
            return only[:1]
        return [item["key"] for item in inputs][:2] or [fields[0]["key"]]

    def _build_entity(self, sheet: str, table_finding: dict[str, Any], series: dict[str, Any] | None) -> None:
        proposal = _proposal(table_finding)
        table = proposal["range"]
        fields_found = [
            item
            for item in self._of_kind("fieldType", sheet)
            if _proposal(item)["table"] == table
        ]
        if not fields_found:
            return
        title = proposal.get("entityLabel")
        name = title["fr"] if title else (self._series_name(sheet, proposal) if series else sheet)
        base = name
        key = _unique(slug(base, "entity"), self.entity_keys)
        taken: set[str] = set()
        specs: list[dict[str, Any]] = []
        letters: dict[str, str] = {}
        by_letter: dict[str, dict[str, Any]] = {}
        for finding in fields_found:
            entry = self._field(sheet, proposal, finding, taken)
            if entry is None:
                continue
            letter = _proposal(finding)["column"]
            specs.append(entry)
            letters[letter] = entry["key"]
            by_letter[letter] = entry
        provisional = {f"col_{letter.lower()}": item for letter, item in letters.items()}
        for entry in specs:
            computed = entry.get("computed")
            if not computed:
                continue
            computed["deps"] = [provisional[dep] for dep in computed["deps"] if dep in provisional]
            if computed["eval"] == "translated":
                if _uses_related(computed["expr"]):
                    # A lookup needs its relation, which isn't resolved yet: the engine runs it.
                    computed["eval"] = "engine"
                    del computed["expr"]
                else:
                    computed["expr"] = _rename_expr(computed["expr"], provisional)

        outcome = self._outcome(sheet) or "register"
        entity_kind = KIND_TO_ENTITY.get(outcome, "register")
        personal = any(
            item["type"] in ("phone", "email") or PERSONAL.search(item["label"]["fr"]) or PERSONAL.search(item["label"]["ar"])
            for item in specs
        )
        for item in specs:
            if item["type"] in ("phone", "email") or PERSONAL.search(item["label"]["fr"]) or PERSONAL.search(item["label"]["ar"]):
                item["personalData"] = True

        grid = self.grids[sheet]
        unique = {
            entry["key"]
            for letter, entry in by_letter.items()
            if self._is_unique(grid, proposal, letter)
        }
        keys = self._key_columns(specs, letters, unique)
        text_fields = [item["key"] for item in specs if item["type"] in ("text", "longtext")]
        title_field = text_fields[0] if text_fields else specs[0]["key"]
        entity: dict[str, Any] = {
            "key": key,
            "label": _two(title, name),
            "kind": entity_kind,
            "naming": {"type": "autonumber", "prefix": slug(key, "r")[:12].upper().replace("_", "-") + "-"},
            "titleField": title_field,
            "searchFields": text_fields[:3] or [title_field],
            "personalData": personal,
            "fields": specs,
        }
        if personal:
            entity["retention"] = {"months": DEFAULT_RETENTION_MONTHS, "basis": dict(RETENTION_BASIS)}
            self.report.questions.append({"kind": "confirmRetention", "entity": key, "months": DEFAULT_RETENTION_MONTHS})
        provenance = _provenance(table_finding, self.sha256)
        if provenance:
            entity["provenance"] = provenance

        tabs = _proposal(series)["tabs"] if series else [{"sheet": sheet, "table": table}]
        sources: list[dict[str, Any]] = []
        if series:
            period_key = _unique("period", taken)
            granularity = _proposal(series)["granularity"]
            specs.insert(0, {"key": period_key, "label": {"fr": "Période", "ar": "الفترة"}, "type": "date", "required": True})
            entity["period"] = {"field": period_key, "granularity": granularity}
            keys = [period_key, *keys]
        else:
            period_key = None
        rows: list[dict[str, Any]] = []
        for tab in tabs:
            source: dict[str, Any] = {"sheet": tab["sheet"], "range": tab["table"]}
            period_date = None
            if series:
                period_date = self._period_date(tab)
                if period_date is None:
                    continue
                # "--01" says only "January": the mapping needs the year the owner gave it.
                source["period"] = period_date[:7] if tab["period"].startswith("-") else tab["period"]
            sources.append(source)
            rows += self._seed_rows(key, tab["sheet"], tab["table"], by_letter, period_key, period_date)
        if not sources:
            return

        # Each column keeps its letter: a rejected column mustn't shift what formulas read.
        columns = [
            {"header": self._names_of(fields_found, letter), "field": letters[letter], "column": letter}
            for letter in sorted(letters, key=column_index_from_string)
        ]
        mapping: dict[str, Any] = {
            "entity": key,
            "sources": sources,
            "headerRow": (proposal["headerRows"] or [int(range_boundaries(table)[1]) - 1])[-1] or 1,
            "columns": columns,
            "keyColumns": [item for item in keys if item != period_key] or keys,
        }
        totals = self._totals_of(sheet, table, letters)
        if totals:
            mapping["totals"] = totals
        self.entities.append(entity)
        self.mappings.append(mapping)
        self.seed[key] = rows
        self.report.rows[key] = len(rows)
        self.infos[(sheet, table)] = TableInfo(sheet, proposal, key, by_letter)
        for tab in tabs:
            self.infos[(tab["sheet"], tab["table"])] = TableInfo(tab["sheet"], proposal, key, by_letter)
        self._add_workflow(entity, outcome)

    def _series_name(self, sheet: str, table: dict[str, Any]) -> str:
        """A series isn't "Janvier 2026". Its title above the table, minus the period, says what it is."""
        grid = self.grids[sheet]
        left, top, right, _ = (int(part) for part in range_boundaries(table["range"]))
        for row in range(max(1, top - 3), top):
            cells = grid.row_cells(row, 1, right)
            if len(cells) == 1 and cells[0].is_text:
                words = [word for word in text_of(cells[0]).split() if not _is_period_word(word)]
                if words:
                    return " ".join(words)
        words = [word for word in sheet.split() if not _is_period_word(word)]
        return " ".join(words) or "Suivi par période"

    def _names_of(self, fields_found: list[dict[str, Any]], letter: str) -> str:
        for item in fields_found:
            if _proposal(item)["column"] == letter:
                return str(_proposal(item)["name"])
        return letter

    def _totals_of(self, sheet: str, table: str, letters: dict[str, str]) -> list[dict[str, str]]:
        found: dict[str, str] = {}
        for finding in self._of_kind("totalRow", sheet):
            proposal = _proposal(finding)
            if proposal["table"] != table:
                continue
            for item in proposal["aggregates"]:
                if item["column"] in letters:
                    found[letters[item["column"]]] = item["function"]
        return [{"field": key, "function": function} for key, function in found.items()]

    def _is_unique(self, grid: Grid, table: dict[str, Any], letter: str) -> bool:
        left, top, _, bottom = (int(part) for part in range_boundaries(table["dataRange"]))
        column = column_index_from_string(letter)
        values = [text_of(cell) for cell in grid.column_cells(column, top, bottom)]
        return len(values) >= 2 and len(values) == len(set(values))

    def _period_date(self, tab: dict[str, Any]) -> str | None:
        period = tab["period"]
        if period.startswith("-"):
            year = tab.get("year")
            if not year:
                self.report.questions.append({"kind": "periodYear", "sheet": tab["sheet"], "period": period})
                return None
            period = f"{year}{period[1:]}"
        if "Q" in period:
            year, quarter = period.split("-Q")
            return f"{year}-{(int(quarter) - 1) * 3 + 1:02d}-01"
        if "-" in period:
            return f"{period}-01"
        return f"{period}-01-01"

    def _seed_rows(
        self, entity: str, sheet: str, table: str, by_letter: dict[str, dict[str, Any]], period_key: str | None, period_date: str | None
    ) -> list[dict[str, Any]]:
        grid = self.grids[sheet]
        info = next((item for item in self._of_kind("table", sheet) if _proposal(item)["range"] == table), None)
        if info is None:
            return []
        proposal = _proposal(info)
        left, top, _, bottom = (int(part) for part in range_boundaries(proposal["dataRange"]))
        skipped = {*proposal["totalRows"], *proposal["noteRows"]}
        rows = []
        for row in range(top, int(range_boundaries(proposal["range"])[3]) + 1):
            if row in skipped:
                continue
            record: dict[str, Any] = {}
            filled = False
            for letter, entry in by_letter.items():
                if entry["type"] == "computed":
                    continue
                cell = grid.get(row, column_index_from_string(letter))
                if cell is None:
                    continue
                value = self._convert(entry, cell, sheet, letter, row)
                if value is not None:
                    record[entry["key"]] = value
                    filled = True
            if filled:
                if period_key:
                    record[period_key] = period_date
                rows.append(record)
        return rows

    def _convert(self, entry: dict[str, Any], cell: Any, sheet: str, letter: str, row: int) -> Any:
        value = convert_value(entry, cell)
        if value is None and cell.value is not None:
            self.report.bad_values.append({"sheet": sheet, "cell": f"{letter}{row}", "field": entry["key"], "type": entry["type"]})
        return value

    def _add_workflow(self, entity: dict[str, Any], outcome: str) -> None:
        """A tracker's status column becomes its workflow, one step at a time, either way."""
        if outcome != "tracker":
            return
        status = next(
            (item for item in entity["fields"] if item["type"] == "choice" and re.search(r"statut|[ée]tat|status|الحالة|حالة", item["label"]["fr"] + item["label"]["ar"], re.I)),
            next((item for item in entity["fields"] if item["type"] == "choice" and any("colour" in choice for choice in item["choices"])), None),
        )
        if status is None:
            return
        keys = [choice["key"] for choice in status["choices"]]
        for index, choice in enumerate(status["choices"]):
            choice.setdefault("colour", STATE_COLOURS[index % len(STATE_COLOURS)])
        transitions = []
        for index in range(len(keys) - 1):
            forward, back = status["choices"][index + 1], status["choices"][index]
            transitions.append(
                {"key": f"to_{forward['key']}"[:63], "label": dict(forward["label"]), "from": [keys[index]], "to": keys[index + 1], "roles": ["owner", "staff"]}
            )
            transitions.append(
                {"key": f"back_to_{back['key']}"[:63], "label": dict(back["label"]), "from": [keys[index + 1]], "to": keys[index], "roles": ["owner", "staff"]}
            )
        self.workflows.append(
            {
                "key": f"{entity['key']}_flow"[:63],
                "label": dict(entity["label"]),
                "entity": entity["key"],
                "stateField": status["key"],
                "initialState": keys[0],
                "states": [{"key": choice["key"], "label": dict(choice["label"]), "colour": choice["colour"]} for choice in status["choices"]],
                "transitions": transitions,
            }
        )

    def _apply_relations(self) -> None:
        for finding in self._of_kind("relation"):
            proposal = _proposal(finding)
            source = self._info_for(proposal["from"]["sheet"], proposal["from"]["column"])
            target = self._info_for(proposal["to"]["sheet"], proposal["to"]["column"])
            if source is None or target is None or source.entity_key == target.entity_key:
                continue
            self.relation_ends.update(
                {
                    (proposal["from"]["sheet"], proposal["from"]["column"]),
                    (proposal["to"]["sheet"], proposal["to"]["column"]),
                }
            )
            entry = source.fields.get(proposal["from"]["column"])
            target_field = target.fields.get(proposal["to"]["column"])
            if entry is None or target_field is None or entry["type"] == "computed":
                continue
            self._make_link(source.entity_key, entry, target.entity_key, target_field["key"])

    def _info_for(self, sheet: str, column: str) -> TableInfo | None:
        for (name, _), info in self.infos.items():
            if name == sheet and column in info.fields:
                return info
        return None

    def _make_link(self, entity_key: str, entry: dict[str, Any], target: str, target_key: str) -> None:
        for extra in ("choices", "precision"):
            entry.pop(extra, None)
        entry["type"] = "link"
        entry["target"] = target
        entry["onDelete"] = "restrict"
        # Seed rows name the target by its key's value; the loader finds the record.
        for row in self.seed.get(entity_key, []):
            value = row.get(entry["key"])
            # Each tab of a series reports the same relation, so this can run more than once.
            if value is not None and not (isinstance(value, dict) and "$ref" in value):
                row[entry["key"]] = {"$ref": {"field": target_key, "value": value}}

    def _apply_entity_merges(self) -> None:
        """An accepted retyped name becomes its own list, with one record per spelling group."""
        for finding in self._of_kind("entityMerge"):
            proposal = _proposal(finding)
            columns = proposal["columns"]
            infos = [(self._info_for(item["sheet"], item["column"]), item) for item in columns]
            found = [(info, item) for info, item in infos if info is not None]
            # A key that a relation already points at is an entity's own column. Making it a list
            # too would turn a student's matricule into a table of matricules.
            if not found or any((item["sheet"], item["column"]) in self.relation_ends for item in columns):
                continue
            canonical = {}
            for cluster in proposal["clusters"]:
                for variant in cluster["variants"]:
                    canonical[fingerprint(str(variant["value"]))] = cluster["canonical"]
            name = str(proposal.get("name") or "liste")
            key = _unique(slug(name, "liste"), self.entity_keys)
            label = _two(proposal.get("label"), name)
            field_key = "nom"
            values: dict[str, str] = {}
            for info, item in found:
                entry = info.fields.get(item["column"])
                if entry is None:
                    continue
                for row in self.seed.get(info.entity_key, []):
                    raw = row.get(entry["key"])
                    if isinstance(raw, str):
                        chosen = canonical.get(fingerprint(raw), raw)
                        values[fingerprint(chosen)] = chosen
                        row[entry["key"]] = chosen
            if not values:
                continue
            personal = bool(PERSONAL.search(name))
            entity: dict[str, Any] = {
                "key": key,
                "label": label,
                "kind": "reference",
                "naming": {"type": "field", "field": field_key},
                "titleField": field_key,
                "searchFields": [field_key],
                "personalData": personal,
                "fields": [{"key": field_key, "label": {"fr": "Nom", "ar": "الاسم"}, "type": "text", "required": True, "unique": True, **({"personalData": True} if personal else {})}],
            }
            if personal:
                entity["retention"] = {"months": DEFAULT_RETENTION_MONTHS, "basis": dict(RETENTION_BASIS)}
            self.entities.append(entity)
            self.seed[key] = [{field_key: value} for value in sorted(values.values())]
            self.report.rows[key] = len(values)
            self.mappings.append(
                {
                    "entity": key,
                    "sources": [{"sheet": name[:31]}],
                    "headerRow": 1,
                    "columns": [{"header": name, "field": field_key}],
                    "keyColumns": [field_key],
                }
            )
            for info, item in found:
                entry = info.fields.get(item["column"])
                if entry is not None and entry["type"] != "computed":
                    self._make_link(info.entity_key, entry, key, field_key)

    def _calculators(self) -> list[dict[str, Any]]:
        out = []
        used: set[str] = set()
        types = {"percent": "percent", "decimal": "decimal", "date": "date", "boolean": "boolean", "text": "text"}
        for finding in self._of_kind("calculator"):
            proposal = _proposal(finding)
            sheet = finding["sheet"]
            def port(item: dict[str, Any]) -> dict[str, Any]:
                return {
                    "key": item["key"],
                    "label": _two(item.get("label"), item["name"]),
                    "type": types.get(item["type"], "decimal"),
                    "sheet": item["sheet"],
                    "cell": item["cell"],
                    **({"default": item["default"]} if "default" in item else {}),
                }

            calculator: dict[str, Any] = {
                "key": _unique(slug(sheet, "calcul"), used),
                "label": _two(proposal.get("label"), sheet),
                "inputs": [port(item) for item in proposal["inputs"]],
                "outputs": [port(item) | {} for item in proposal["outputs"]],
                "cells": [{key: value for key, value in cell.items() if value is not None or key == "v"} for cell in proposal["cells"]],
                "testCases": proposal["testCases"],
            }
            for output in calculator["outputs"]:
                output.pop("default", None)
            provenance = _provenance(finding, self.sha256)
            if provenance:
                calculator["provenance"] = provenance
            out.append(calculator)
        return out

    def _views_forms_dashboards(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        views: list[dict[str, Any]] = []
        forms: list[dict[str, Any]] = []
        widgets: list[dict[str, Any]] = []
        for entity in self.entities:
            key = entity["key"]
            fields = entity["fields"]
            numeric = [item for item in fields if (item.get("resultType") or item["type"]) in ("money", "decimal", "integer") and not item.get("level")]
            money = [item for item in numeric if (item.get("resultType") or item["type"]) == "money"]
            view: dict[str, Any] = {
                "key": f"{key}_all"[:63],
                "label": dict(entity["label"]),
                "entity": key,
                "type": "list",
                "columns": [item["key"] for item in fields if item["type"] != "longtext"][:8],
            }
            totals = [item["key"] for item in money]
            if totals:
                view["totals"] = totals
            views.append(view)
            workflow = next((item for item in self.workflows if item["entity"] == key), None)
            if workflow:
                views.append(
                    {
                        "key": f"{key}_board"[:63],
                        "label": dict(entity["label"]),
                        "entity": key,
                        "type": "board",
                        "workflow": workflow["key"],
                        "cardFields": [entity["titleField"]],
                    }
                )
            writable = [item["key"] for item in fields if item["type"] != "computed"]
            if workflow:
                writable = [item for item in writable if item != workflow["stateField"]]
            if writable:
                forms.append(
                    {
                        "key": f"{key}_form"[:63],
                        "label": dict(entity["label"]),
                        "entity": key,
                        "sections": [{"key": "main", "label": dict(entity["label"]), "fields": writable}],
                    }
                )
            widgets.append(
                {"key": f"{key}_count"[:63], "label": dict(entity["label"]), "type": "kpi", "entity": key, "aggregate": "count"}
            )
            for item in money[:1]:
                widgets.append(
                    {"key": f"{key}_{item['key']}_sum"[:63], "label": dict(item["label"]), "type": "kpi", "entity": key, "aggregate": "sum", "field": item["key"]}
                )
        dashboards = [{"key": "overview", "label": {"fr": "Vue d'ensemble", "ar": "نظرة عامة"}, "widgets": widgets}] if widgets else []
        return views, forms, dashboards

    def generate(self) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], Report]:
        series_by_tab = self._period_tabs()
        done_series: set[str] = set()
        for finding in self._of_kind("table"):
            sheet = finding["sheet"]
            outcome = self._outcome(sheet)
            if outcome is None or outcome in ("notConverted", "formulaModel"):
                continue
            series = series_by_tab.get(sheet)
            if series is not None:
                if series["id"] in done_series:
                    continue
                done_series.add(series["id"])
                first = _proposal(series)["tabs"][0]
                if sheet != first["sheet"]:
                    finding = next((item for item in self._of_kind("table", first["sheet"])), finding)
                    sheet = first["sheet"]
            self._build_entity(sheet, finding, series)
        self._apply_relations()
        self._apply_entity_merges()
        calculators = self._calculators()
        views, forms, dashboards = self._views_forms_dashboards()
        roles = [
            {
                "key": role,
                "label": ROLE_LABELS[role],
                "fieldLevel": ROLE_LEVEL[role],
                "permissions": [{"entity": entity["key"], "actions": ROLE_ACTIONS[role], "rowScope": "all"} for entity in self.entities],
            }
            for role in ROLE_ACTIONS
        ]
        file_name = Path(self.snapshot["source"]["fileName"]).stem
        spec: dict[str, Any] = {
            "specVersion": SPEC_VERSION,
            "app": {
                "name": {"fr": file_name, "ar": file_name},
                "locales": ["fr-DZ", "ar-DZ"],
                "defaultLocale": "fr-DZ",
                "currency": "DZD",
                "timezone": "Africa/Algiers",
            },
            "entities": self.entities,
            "calculators": calculators,
            "views": views,
            "forms": forms,
            "dashboards": dashboards,
            "roles": roles,
            "workflows": self.workflows,
            "reminders": [],
            "history": {},
            "mapping": self.mappings,
        }
        self.report.entities = len(self.entities)
        errors = validate_spec(spec)
        if errors:
            raise GenerationError(format_errors(errors))
        return spec, self.seed, self.report


def _is_period_word(word: str) -> bool:
    return fingerprint(word) in MONTHS or YEAR.fullmatch(word) is not None


def write_project_outputs(output: Path, spec: dict[str, Any], seed: dict[str, list[dict[str, Any]]], report: Report) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "daftar.spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    seed_dir = output / "seed"
    seed_dir.mkdir(exist_ok=True)
    for key, rows in seed.items():
        lines = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        (seed_dir / f"{key}.jsonl").write_text(lines, encoding="utf-8")
    (output / "generation-report.json").write_text(
        json.dumps(
            {
                "entities": report.entities,
                "rows": dict(report.rows),
                "badValues": report.bad_values,
                "parityFailures": report.parity_failures,
                "questions": report.questions,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
