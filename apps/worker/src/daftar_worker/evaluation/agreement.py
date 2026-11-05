"""How far two labellers agree, for the double-labelled share of WP-4.

Boundaries, headers, relations and monthly tabs use the same scoring as Daftar, with one labeller
read as the other's predictions: F1 doesn't care which one is which. Sheet kinds and field types
are categories, so they get Cohen's kappa, which discounts agreement expected by chance. Reports
hold counts only, never a cell, so they can be kept beside the code.
"""

from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from openpyxl.utils import range_boundaries

from daftar_worker.evaluation.labels import schema_problems
from daftar_worker.evaluation.metrics import (
    WorkbookScore,
    bootstrap,
    compute_metrics,
    score_workbook,
)
from daftar_worker.evaluation.predictions import label_as_predictions


METRICS = ("tables.exact.f1", "tables.near.f1", "headers.f1", "relations.f1", "periodTabs.f1")


@dataclass
class PairScore(WorkbookScore):
    kinds: Counter[tuple[str, str]] = field(default_factory=Counter)
    types: Counter[tuple[str, str]] = field(default_factory=Counter)
    fields_alone: int = 0


def cohen_kappa(pairs: Counter[tuple[str, str]]) -> float | None:
    """None with no pairs, or when chance alone predicts full agreement, where kappa says nothing."""
    total = sum(pairs.values())
    if not total:
        return None
    observed = sum(count for (left, right), count in pairs.items() if left == right) / total
    lefts: Counter[str] = Counter()
    rights: Counter[str] = Counter()
    for (left, right), count in pairs.items():
        lefts[left] += count
        rights[right] += count
    expected = sum(lefts[name] * rights[name] for name in lefts) / total**2
    return None if expected == 1 else (observed - expected) / (1 - expected)


def _fields(label: dict[str, Any]) -> list[tuple[str, str, int, int, str]]:
    out: list[tuple[str, str, int, int, str]] = []
    for sheet in label["sheets"]:
        for table in sheet["tables"]:
            _, low, _, high = range_boundaries(table["range"])
            out.extend((sheet["name"], item["column"], int(low), int(high), item["type"]) for item in table["fields"])
    return out


def _pair_fields(first: dict[str, Any], second: dict[str, Any]) -> tuple[Counter[tuple[str, str]], int]:
    """A field pairs with the same column on the same sheet whose rows overlap it most. Each is used once."""
    left, right = _fields(first), _fields(second)
    candidates = []
    for one, item in enumerate(left):
        for other, match in enumerate(right):
            if item[:2] == match[:2]:
                overlap = min(item[3], match[3]) - max(item[2], match[2]) + 1
                if overlap > 0:
                    candidates.append((-overlap, one, other))
    pairs: Counter[tuple[str, str]] = Counter()
    used_left: set[int] = set()
    used_right: set[int] = set()
    for _, one, other in sorted(candidates):
        if one not in used_left and other not in used_right:
            used_left.add(one)
            used_right.add(other)
            pairs[(left[one][4], right[other][4])] += 1
    alone = len(left) + len(right) - 2 * len(used_left)
    return pairs, alone


def compare_labels(workbook_id: str, first: dict[str, Any], second: dict[str, Any]) -> PairScore:
    scored = score_workbook(workbook_id, "", first, label_as_predictions(second), parity_ran=False)
    result = PairScore(workbook_id, "", False)
    result.tallies = scored.tallies
    result.confusion = scored.confusion
    other = {sheet["name"]: sheet["kind"] for sheet in second["sheets"]}
    for sheet in first["sheets"]:
        if sheet["name"] in other:
            result.kinds[(sheet["kind"], other[sheet["name"]])] += 1
    result.types, result.fields_alone = _pair_fields(first, second)
    return result


def agreement_metrics(scores: list[PairScore]) -> dict[str, float | None]:
    point = compute_metrics(scores)
    metrics = {name: point.get(name) for name in METRICS}
    kinds: Counter[tuple[str, str]] = Counter()
    types: Counter[tuple[str, str]] = Counter()
    alone = 0
    for score in scores:
        kinds.update(score.kinds)
        types.update(score.types)
        alone += score.fields_alone
    metrics["kind.kappa"] = cohen_kappa(kinds)
    metrics["type.kappa"] = cohen_kappa(types)
    paired = sum(types.values())
    metrics["type.shared"] = 2 * paired / (2 * paired + alone) if paired + alone else None
    return metrics


def compare_all(labels: dict[str, tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    scores = [compare_labels(workbook_id, first, second) for workbook_id, (first, second) in sorted(labels.items())]
    point = agreement_metrics(scores)
    intervals = bootstrap(scores, agreement_metrics) if scores else {}
    return {
        "workbooks": len(scores),
        "ids": [score.id for score in scores],
        "metrics": {name: {"value": value, "ci95": intervals.get(name)} for name, value in sorted(point.items())},
    }


def _read_folder(folder: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Drafts count here: disagreement between drafts is exactly what a person is asked to rule on."""
    labels: dict[str, dict[str, Any]] = {}
    refused: list[str] = []
    for path in sorted(folder.glob("*.json")):
        if path.name.count(".") > 1:  # Harness files such as `id.run.json` sit beside the labels.
            continue
        try:
            label = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            refused.append(path.stem)
            continue
        if schema_problems(label):
            refused.append(path.stem)
        else:
            labels[path.stem] = label
    return labels, refused


def compare_folders(first: Path, second: Path) -> dict[str, Any]:
    left, refused_left = _read_folder(first)
    right, refused_right = _read_folder(second)
    report = compare_all({name: (left[name], right[name]) for name in left.keys() & right.keys()})
    report["onlyFirst"] = sorted(left.keys() - right.keys())
    report["onlySecond"] = sorted(right.keys() - left.keys())
    report["refused"] = sorted({*refused_left, *refused_right})
    return report


def render_agreement(report: dict[str, Any]) -> str:
    lines = [f"# Labeller agreement on {report['workbooks']} workbooks", "", "| Measure | Value | 95% interval |", "|---|---|---|"]
    for name, item in report["metrics"].items():
        value = "n/a" if item["value"] is None else f"{item['value']:.3f}"
        interval = f"{item['ci95'][0]:.3f} to {item['ci95'][1]:.3f}" if item["ci95"] else "n/a"
        lines.append(f"| {name} | {value} | {interval} |")
    lines += ["", "`type.shared` is the share of fields both labellers marked; `type.kappa` covers only those."]
    for title, key in (("Only in the first folder", "onlyFirst"), ("Only in the second folder", "onlySecond"), ("Refused, not valid labels", "refused")):
        if report.get(key):
            lines += ["", f"{title}: {', '.join(report[key])}"]
    return "\n".join(lines) + "\n"


__all__ = ["cohen_kappa", "compare_all", "compare_folders", "compare_labels", "render_agreement"]
