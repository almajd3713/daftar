"""Run an evaluation, write its report, and write draft labels."""

from collections import defaultdict
import json
from pathlib import Path
import subprocess
from typing import Any

from openpyxl.utils import range_boundaries

from daftar_worker.analyser import analyze_snapshot
from daftar_worker.errors import WorkerError
from daftar_worker.evaluation.labels import (
    SEPARATE_STRATA,
    EvalError,
    ManifestRow,
    check_frozen,
    load_labels,
    read_manifest,
)
from daftar_worker.evaluation.metrics import WorkbookScore, score_workbook, summarise
from daftar_worker.evaluation.predictions import Predictions, from_analysis
from daftar_worker.reader import read_file


METRIC_NAMES = {
    "tables.exact.precision": "Tables, exact: precision",
    "tables.exact.recall": "Tables, exact: recall",
    "tables.near.precision": "Tables, within 2 cells: precision",
    "tables.near.recall": "Tables, within 2 cells: recall",
    "headers.f1": "Header rows: F1",
    "type.macroAccuracy": "Field types: macro accuracy",
    "relations.precision": "Relations: precision",
    "relations.recall": "Relations: recall",
    "relations.f1": "Relations: F1",
    "periodTabs.f1": "Monthly tabs grouped: F1",
    "kind.accuracy": "Sheet kind: accuracy",
    "parity.share": "Formulas equal to Excel",
}


def git_state(cwd: Path | None = None) -> dict[str, Any]:
    """The commit that produced a report. `dirty` flags a working tree that doesn't match it."""

    def run(*args: str) -> str | None:
        try:
            done = subprocess.run(
                ["git", *args], capture_output=True, text=True, check=True, cwd=cwd, timeout=20
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout.strip()

    sha = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {"sha": sha, "dirty": bool(status) if status is not None else None}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise EvalError(f"{path}: not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise EvalError(f"{path}: expected a JSON object")
    return data


def _engine_stamp(engines: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Each engine value seen. More than one means a mixed run, and the report shows it."""
    stamp: dict[str, set[str]] = defaultdict(set)
    for engine in engines:
        for key in ("rulesVersion", "model", "quant"):
            if engine.get(key) is not None:
                stamp[key].add(str(engine[key]))
    return {key: sorted(stamp[key]) for key in ("rulesVersion", "model", "quant")}


def _analyse_workbook(
    manifest_path: Path, row: ManifestRow
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Run the analyser and the engine on a workbook from the set. None if it can't be read."""
    # Imported here because the parity module reads this package's metrics.
    from daftar_worker.formulas.parity import run_parity

    path = workbook_path(manifest_path, row)
    if path is None:
        return None, None
    try:
        snapshot = read_file(path)
    except WorkerError:
        return None, None
    return analyze_snapshot(snapshot), run_parity(path, snapshot)


def run_evaluation(
    labels_dir: Path, manifest_path: Path, split: str, analyses_dir: Path | None
) -> dict[str, Any]:
    all_rows = read_manifest(manifest_path)
    frozen = check_frozen(all_rows, manifest_path)
    rows = [row for row in all_rows if row.split == split]
    if not rows:
        raise EvalError(f"the {split} split has no workbooks")
    labels = load_labels(labels_dir, rows)

    scores: list[WorkbookScore] = []
    missing: list[str] = []
    parity_not_run: list[str] = []
    engines: list[dict[str, Any]] = []
    for row in rows:
        if analyses_dir is None:
            analysis, parity = _analyse_workbook(manifest_path, row)
        else:
            analysis = _read_json(analyses_dir / f"{row.id}.json")
            parity = _read_json(analyses_dir / f"{row.id}.parity.json")
        # No formula engine ran at all, which says nothing about whether it would get them right.
        # A formula missing from a results file that does exist still counts as wrong.
        parity_ran = parity is not None or analysis is None
        if not parity_ran and labels[row.id]["resultsFrom"] == "excel":
            parity_not_run.append(row.id)
        if analysis is None:
            missing.append(row.id)
            predictions = Predictions()
        else:
            if analysis.get("snapshotSha256") != row.sha256:
                raise EvalError(f"{row.id}: the analysis is of a different workbook")
            engines.append(analysis.get("engine") or {})
            predictions = from_analysis(analysis, parity)
        scores.append(score_workbook(row.id, row.stratum, labels[row.id], predictions, parity_ran))

    headline = [score for score in scores if score.stratum not in SEPARATE_STRATA]
    strata: dict[str, list[WorkbookScore]] = defaultdict(list)
    for score in scores:
        strata[score.stratum].append(score)

    report: dict[str, Any] = {
        "reportVersion": 1,
        "split": split,
        "testSplitFrozen": frozen,
        "git": git_state(),
        "engine": _engine_stamp(engines),
        "workbooks": len(scores),
        "missingAnalyses": missing,
        "excludedFromParity": sorted(
            row.id for row in rows if labels[row.id]["resultsFrom"] != "excel"
        ),
        "parityNotRun": parity_not_run,
        "excludedFromHeadline": sorted(s.id for s in scores if s.stratum in SEPARATE_STRATA),
        "overall": summarise(headline),
        "byStratum": {name: summarise(strata[name]) for name in sorted(strata)},
    }
    if split == "dev":
        # Never for the test split: per-workbook scores would invite tuning against it.
        report["perWorkbook"] = {
            score.id: {key: count for key, count in sorted(score.tallies.items())} for score in scores
        }
    return report


def _format_metric(entry: dict[str, Any] | None) -> tuple[str, str]:
    if entry is None or entry["value"] is None:
        return "n/a", "n/a"
    interval = entry["ci95"]
    ci = f"{interval[0] * 100:.1f}–{interval[1] * 100:.1f}" if interval else "n/a"
    return f"{entry['value'] * 100:.1f}", ci


def render_report(report: dict[str, Any]) -> str:
    git = report["git"]
    engine = report["engine"]
    lines = [
        f"# Evaluation report: {report['split']} split",
        "",
        f"- Workbooks: **{report['workbooks']}**, of which {report['overall']['workbooks']} count toward the headline",
        f"- Git: `{git['sha']}`{' (uncommitted changes)' if git['dirty'] else ''}",
        f"- Rules: {engine['rulesVersion'] or 'unknown'}",
        f"- Model: {engine['model'] or 'none (rules only)'}",
        f"- Quantisation: {engine['quant'] or 'none'}",
        f"- Test split frozen: {'yes' if report['testSplitFrozen'] else 'no'}",
        f"- No analysis, scored as wrong: {', '.join(report['missingAnalyses']) or 'none'}",
        f"- Left out of formula parity (results not from Excel): {', '.join(report['excludedFromParity']) or 'none'}",
        f"- Left out of formula parity (no formula engine run): {', '.join(report['parityNotRun']) or 'none'}",
        f"- Reported only under their stratum: {', '.join(report['excludedFromHeadline']) or 'none'}",
        "",
        "## Headline",
        "",
        "Percentages with workbook-level bootstrap 95% confidence intervals.",
        "",
        "| Metric | % | 95% CI |",
        "|---|---:|---:|",
    ]
    overall = report["overall"]["metrics"]
    for name, title in METRIC_NAMES.items():
        value, interval = _format_metric(overall.get(name))
        lines.append(f"| {title} | {value} | {interval} |")

    categories = sorted(name for name in overall if name.startswith("parity.category."))
    if categories:
        lines += ["", "## Formula parity by function category", "", "| Category | % | 95% CI |", "|---|---:|---:|"]
        for name in categories:
            value, interval = _format_metric(overall[name])
            title = name.removeprefix("parity.category.").removesuffix(".share")
            lines.append(f"| {title} | {value} | {interval} |")

    lines += ["", "## Sheet kind confusion", "", "| Labelled | Predicted | Sheets |", "|---|---|---:|"]
    for gold, row in report["overall"]["kindConfusion"].items():
        for predicted, count in row.items():
            lines.append(f"| {gold} | {predicted} | {count} |")

    lines += ["", "## By stratum", ""]
    strata = report["byStratum"]
    names = list(strata)
    lines.append("| Metric | " + " | ".join(f"{name} (n={strata[name]['workbooks']})" for name in names) + " |")
    lines.append("|---|" + "---:|" * len(names))
    for metric, title in METRIC_NAMES.items():
        cells = []
        for name in names:
            value, interval = _format_metric(strata[name]["metrics"].get(metric))
            cells.append(value if value == "n/a" else f"{value} ({interval})")
        lines.append(f"| {title} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def workbook_path(manifest_path: Path, row: ManifestRow) -> Path | None:
    """Find a workbook by id: published ones first, then private ones."""
    root = manifest_path.parent
    for folder in ("workbooks", "private"):
        found = sorted((root / folder).glob(f"{row.id}.*"))
        if found:
            return found[0]
    return None


def draft_label(row: ManifestRow, snapshot: dict[str, Any], analysis: dict[str, Any] | None) -> dict[str, Any]:
    """Build a draft for a person to correct. Formula results come from the original file."""
    predictions = from_analysis(analysis) if analysis else Predictions()
    sheets = []
    for sheet in snapshot["sheets"]:
        name = sheet["name"]
        tables = []
        for table_range in predictions.tables.get(name, []):
            _, low, _, high = range_boundaries(table_range)
            header_rows = sorted(
                number
                for owner, number in predictions.header_rows
                if owner == name and int(low) <= number <= int(high)
            )
            fields = [
                {"column": item.column, "name": item.column, "type": item.type or "text"}
                for item in predictions.fields
                if item.sheet == name and item.low_row <= int(high) and item.high_row >= int(low)
            ]
            tables.append({"range": table_range, "headerRows": header_rows, "fields": fields})
        kind = predictions.outcomes.get(name, "notConverted")
        entry: dict[str, Any] = {
            "name": name,
            "kind": kind,
            "hidden": sheet["state"] != "visible",
            "regions": [],
            "tables": tables,
        }
        if kind == "notConverted":
            entry["reason"] = "outOfScope"
        sheets.append(entry)
    kinds = {item["kind"] for item in snapshot["unsupported"]}
    return {
        "labelVersion": 1,
        "id": row.id,
        "workbookSha256": row.sha256,
        "status": "draft",
        "resultsFrom": snapshot["source"]["resultsFrom"],
        "workbook": {"hasMacros": "macro" in kinds, "hasExternalLinks": "externalLink" in kinds},
        "sheets": sheets,
        "relations": [
            {"from": {"sheet": a, "column": b}, "to": {"sheet": c, "column": d}}
            for a, b, c, d in sorted(predictions.relations)
        ],
        "formulas": [
            {"sheet": sheet["name"], "ref": cell["ref"], "f": cell["f"], "result": cell["v"], "t": cell["t"]}
            for sheet in snapshot["sheets"]
            for cell in sheet["cells"]
            if "f" in cell
        ],
    }


def write_drafts(
    labels_dir: Path, manifest_path: Path, split: str, analyses_dir: Path | None, output: Path
) -> dict[str, list[str]]:
    """Write a draft for each workbook with no label yet. Nothing existing is overwritten."""
    rows = [row for row in read_manifest(manifest_path) if row.split == split]
    if not rows:
        raise EvalError(f"the {split} split has no workbooks")
    outcome: dict[str, list[str]] = {"written": [], "alreadyLabelled": [], "missingWorkbook": [], "unreadable": []}
    output.mkdir(parents=True, exist_ok=True)
    for row in rows:
        target = output / f"{row.id}.json"
        if (labels_dir / f"{row.id}.json").exists() or target.exists():
            outcome["alreadyLabelled"].append(row.id)
            continue
        path = workbook_path(manifest_path, row)
        if path is None:
            outcome["missingWorkbook"].append(row.id)
            continue
        try:
            snapshot = read_file(path)
        except WorkerError:
            outcome["unreadable"].append(row.id)
            continue
        if snapshot["source"]["sha256"] != row.sha256:
            raise EvalError(f"{row.id}: the file doesn't match the sha256 in the manifest")
        analysis = _read_json(analyses_dir / f"{row.id}.json") if analyses_dir else None
        draft = draft_label(row, snapshot, analysis)
        target.write_text(json.dumps(draft, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        outcome["written"].append(row.id)
    return outcome
