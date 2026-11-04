"""Score one workbook, pool workbooks into metrics, and bootstrap over workbooks.

Tables, fields and formulas cluster inside a workbook, so the workbook is the unit we resample.
"""

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
import math
import random
from typing import Any

from openpyxl.utils import range_boundaries

from daftar_worker.census import analyse_formula
from daftar_worker.evaluation.predictions import Predictions, sheet_pairs


BOOTSTRAP_REPS = 2000
BOOTSTRAP_SEED = 20261103
RELATIVE_TOLERANCE = 1e-9  # R-19.
NO_PREDICTION = "(none)"

CATEGORIES: dict[str, set[str]] = {
    "math": {"SUM", "SUMIF", "SUMIFS", "SUMPRODUCT", "ROUND", "ROUNDUP", "ROUNDDOWN", "ABS", "SUBTOTAL",
             "INT", "MOD", "MROUND", "CEILING", "FLOOR", "POWER", "SQRT", "PRODUCT", "AGGREGATE"},
    "statistical": {"AVERAGE", "AVERAGEIF", "AVERAGEIFS", "COUNT", "COUNTA", "COUNTBLANK", "COUNTIF",
                    "COUNTIFS", "MIN", "MAX", "MINIFS", "MAXIFS", "SMALL", "LARGE", "MEDIAN", "RANK"},
    "logical": {"IF", "IFS", "AND", "OR", "NOT", "IFERROR", "IFNA", "SWITCH", "TRUE", "FALSE"},
    "lookup": {"VLOOKUP", "HLOOKUP", "XLOOKUP", "LOOKUP", "INDEX", "MATCH", "XMATCH", "OFFSET", "INDIRECT",
               "CHOOSE", "ROW", "ROWS", "COLUMN", "COLUMNS"},
    "text": {"CONCATENATE", "CONCAT", "TEXTJOIN", "LEFT", "RIGHT", "MID", "LEN", "TRIM", "UPPER", "LOWER",
             "PROPER", "SUBSTITUTE", "REPLACE", "FIND", "SEARCH", "TEXT", "VALUE", "EXACT", "REPT"},
    "date": {"DATE", "DAY", "MONTH", "YEAR", "TODAY", "NOW", "EDATE", "EOMONTH", "WEEKDAY", "DATEDIF",
             "DAYS", "NETWORKDAYS", "WORKDAY", "HOUR", "MINUTE", "SECOND", "TIME", "DATEVALUE"},
    "information": {"ISBLANK", "ISNUMBER", "ISTEXT", "ISERROR", "ISNA", "CELL", "INFO", "NA"},
}  # fmt: skip


def function_categories(formula: str) -> set[str]:
    """The categories a formula touches. A formula with no function call is "operators"."""
    try:
        functions = analyse_formula(formula)["functions"]
    except Exception:
        return {"unparsed"}
    if not functions:
        return {"operators"}
    found = set()
    for name in functions:
        category = next((key for key, names in CATEGORIES.items() if name in names), "other")
        found.add(category)
    return found


def results_match(expected: Any, actual: Any) -> bool:
    """Numbers within the relative tolerance of R-19; anything else must be exactly equal."""
    expected_number = isinstance(expected, (int, float)) and not isinstance(expected, bool)
    actual_number = isinstance(actual, (int, float)) and not isinstance(actual, bool)
    if expected_number and actual_number:
        return math.isclose(expected, actual, rel_tol=RELATIVE_TOLERANCE, abs_tol=0.0)
    if isinstance(expected, bool) != isinstance(actual, bool) or expected_number != actual_number:
        return False
    return bool(expected == actual)


def error_of_boundary(gold: str, predicted: str) -> int:
    """TableSense's EoB: the largest offset of any of the four edges."""
    gold_edges = range_boundaries(gold)
    predicted_edges = range_boundaries(predicted)
    return max(abs(int(a) - int(b)) for a, b in zip(gold_edges, predicted_edges, strict=True))


def match_tables(gold: Sequence[str], predicted: Sequence[str], tolerance: int) -> int:
    """How many tables pair up one-to-one within the tolerance, closest pairs first."""
    pairs = sorted(
        (error, gold_index, predicted_index)
        for gold_index, gold_range in enumerate(gold)
        for predicted_index, predicted_range in enumerate(predicted)
        if (error := error_of_boundary(gold_range, predicted_range)) <= tolerance
    )
    used_gold: set[int] = set()
    used_predicted: set[int] = set()
    for _, gold_index, predicted_index in pairs:
        if gold_index not in used_gold and predicted_index not in used_predicted:
            used_gold.add(gold_index)
            used_predicted.add(predicted_index)
    return len(used_gold)


@dataclass
class WorkbookScore:
    """Raw tallies for one workbook. Metrics pool these, so they re-pool cheaply in a bootstrap."""

    id: str
    stratum: str
    in_parity: bool
    tallies: Counter[str] = field(default_factory=Counter)
    confusion: Counter[tuple[str, str]] = field(default_factory=Counter)


def _set_tallies(tallies: Counter[str], name: str, gold: set[Any], predicted: set[Any]) -> None:
    tallies[f"{name}.tp"] += len(gold & predicted)
    tallies[f"{name}.fp"] += len(predicted - gold)
    tallies[f"{name}.fn"] += len(gold - predicted)


def _score_fields(tallies: Counter[str], label: dict[str, Any], predictions: Predictions) -> None:
    for sheet in label["sheets"]:
        for table in sheet["tables"]:
            _, low_row, _, high_row = range_boundaries(table["range"])
            for gold in table["fields"]:
                candidates = [
                    item
                    for item in predictions.fields
                    if item.sheet == sheet["name"] and item.column == gold["column"]
                ]
                # Stacked tables share column letters, so take the prediction with most rows here.
                best, best_overlap = None, 0
                for item in candidates:
                    overlap = min(int(high_row), item.high_row) - max(int(low_row), item.low_row) + 1
                    if overlap > best_overlap:
                        best, best_overlap = item, overlap
                tallies[f"type.{gold['type']}.total"] += 1
                if best is not None and best.type == gold["type"]:
                    tallies[f"type.{gold['type']}.correct"] += 1


def _score_parity(
    tallies: Counter[str], label: dict[str, Any], results: dict[tuple[str, str], Any]
) -> None:
    for formula in label["formulas"]:
        key = (formula["sheet"], formula["ref"])
        # A formula with no result counts as wrong: it was not computed correctly.
        equal = key in results and results_match(formula["result"], results[key])
        tallies["parity.total"] += 1
        tallies["parity.equal"] += equal
        for category in function_categories(formula["f"]):
            tallies[f"parity.category.{category}.total"] += 1
            tallies[f"parity.category.{category}.equal"] += equal


def score_workbook(
    workbook_id: str,
    stratum: str,
    label: dict[str, Any],
    predictions: Predictions,
    parity_ran: bool = True,
) -> WorkbookScore:
    in_parity = label["resultsFrom"] == "excel" and parity_ran
    score = WorkbookScore(workbook_id, stratum, in_parity)
    tallies = score.tallies
    sheet_names = {sheet["name"] for sheet in label["sheets"]}

    for sheet in label["sheets"]:
        name = sheet["name"]
        gold_tables = [table["range"] for table in sheet["tables"]]
        predicted_tables = predictions.tables.get(name, [])
        for tag, tolerance in (("tables.exact", 0), ("tables.near", 2)):
            matched = match_tables(gold_tables, predicted_tables, tolerance)
            tallies[f"{tag}.tp"] += matched
            tallies[f"{tag}.fp"] += len(predicted_tables) - matched
            tallies[f"{tag}.fn"] += len(gold_tables) - matched

        predicted_kind = predictions.outcomes.get(name, NO_PREDICTION)
        score.confusion[(sheet["kind"], predicted_kind)] += 1
        tallies["kind.total"] += 1
        tallies["kind.correct"] += predicted_kind == sheet["kind"]

    # A table or header on a sheet that doesn't exist in the labels is still a false positive.
    for name, ranges in predictions.tables.items():
        if name not in sheet_names:
            tallies["tables.exact.fp"] += len(ranges)
            tallies["tables.near.fp"] += len(ranges)

    gold_headers = {
        (sheet["name"], row)
        for sheet in label["sheets"]
        for table in sheet["tables"]
        for row in table["headerRows"]
    }
    _set_tallies(tallies, "headers", gold_headers, predictions.header_rows)

    gold_relations = {
        (item["from"]["sheet"], item["from"]["column"], item["to"]["sheet"], item["to"]["column"])
        for item in label["relations"]
    }
    _set_tallies(tallies, "relations", gold_relations, predictions.relations)

    groups: dict[str, list[str]] = {}
    for sheet in label["sheets"]:
        if sheet.get("periodGroup"):
            groups.setdefault(sheet["periodGroup"], []).append(sheet["name"])
    gold_pairs = {pair for names in groups.values() for pair in sheet_pairs(sorted(names))}
    _set_tallies(tallies, "periodTabs", gold_pairs, predictions.period_pairs)

    _score_fields(tallies, label, predictions)
    if in_parity:
        _score_parity(tallies, label, predictions.results)
    return score


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _precision_recall_f1(tallies: Counter[str], name: str) -> dict[str, float | None]:
    tp, fp, fn = tallies[f"{name}.tp"], tallies[f"{name}.fp"], tallies[f"{name}.fn"]
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = _ratio(2 * tp, 2 * tp + fp + fn)
    return {f"{name}.precision": precision, f"{name}.recall": recall, f"{name}.f1": f1}


def compute_metrics(scores: Iterable[WorkbookScore]) -> dict[str, float | None]:
    """Pool the tallies, then compute. Pooling weights a workbook by how much it holds."""
    tallies: Counter[str] = Counter()
    for score in scores:
        tallies.update(score.tallies)
    metrics: dict[str, float | None] = {}
    for name in ("tables.exact", "tables.near", "headers", "relations", "periodTabs"):
        metrics.update(_precision_recall_f1(tallies, name))
    per_type = [
        tallies[name.replace(".total", ".correct")] / count
        for name, count in tallies.items()
        if name.startswith("type.") and name.endswith(".total") and count
    ]
    metrics["type.macroAccuracy"] = sum(per_type) / len(per_type) if per_type else None
    metrics["kind.accuracy"] = _ratio(tallies["kind.correct"], tallies["kind.total"])
    metrics["parity.share"] = _ratio(tallies["parity.equal"], tallies["parity.total"])
    for name, count in tallies.items():
        if name.startswith("parity.category.") and name.endswith(".total") and count:
            category = name.removesuffix(".total")
            metrics[f"{category}.share"] = tallies[f"{category}.equal"] / count
    return metrics


def percentile_interval(values: list[float], low: float = 0.025, high: float = 0.975) -> list[float]:
    ordered = sorted(values)
    last = len(ordered) - 1
    return [ordered[math.floor(low * last)], ordered[math.ceil(high * last)]]


def bootstrap(
    scores: list[WorkbookScore],
    compute: Callable[[list[WorkbookScore]], dict[str, float | None]] = compute_metrics,
    reps: int = BOOTSTRAP_REPS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, list[float]]:
    """A 95% percentile interval per metric, resampling whole workbooks with replacement."""
    if not scores:
        return {}
    rng = random.Random(seed)
    samples: dict[str, list[float]] = {}
    for _ in range(reps):
        drawn = rng.choices(scores, k=len(scores))
        for name, value in compute(drawn).items():
            if value is not None:  # Undefined in this draw, such as precision with no predictions.
                samples.setdefault(name, []).append(value)
    return {name: percentile_interval(values) for name, values in samples.items()}


def summarise(scores: list[WorkbookScore]) -> dict[str, Any]:
    point = compute_metrics(scores)
    intervals = bootstrap(scores)
    confusion: Counter[tuple[str, str]] = Counter()
    for score in scores:
        confusion.update(score.confusion)
    matrix: dict[str, dict[str, int]] = {}
    for (gold, predicted), count in sorted(confusion.items()):
        matrix.setdefault(gold, {})[predicted] = count
    return {
        "workbooks": len(scores),
        "metrics": {
            name: {"value": value, "ci95": intervals.get(name)}
            for name, value in sorted(point.items())
        },
        "kindConfusion": matrix,
    }
