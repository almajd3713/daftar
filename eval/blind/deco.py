"""Check blind agents and Daftar against DECO's human table and header labels.

    uv run python eval/blind/deco.py sample
    uv run python eval/blind/deco.py label --model opus
    uv run python eval/blind/deco.py score --tags opus sonnet
    uv run python eval/blind/deco.py rules --split tune

Rule changes are tuned on the "tune" split only. "holdout" holds a fixed share of DECO plus the agents'
30 workbooks, and is measured to report progress, never to choose a rule.

DECO has no licence file (OQ-5), and its Enron workbooks can hold personal data, so everything stays in
eval/private/deco/. Output is counts only, with no cell text. Workbooks that look personal are skipped
before an agent sees them, and DECO's annotation sheets are removed from what the agent and Daftar read.
"""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import pickle
import random
import re
import subprocess
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import range_boundaries
from run import as_predictions, ask_agent, final_event, lines_read, outside_paths, prepare, render

from daftar_worker.analyser import analyze_snapshot
from daftar_worker.evaluation.labels import schema_problems
from daftar_worker.evaluation.metrics import compute_metrics, match_tables, score_workbook
from daftar_worker.evaluation.predictions import Predictions, from_analysis
from daftar_worker.reader import read_file


ROOT = Path(__file__).resolve().parents[2]
DECO = ROOT / "eval" / "private" / "deco"
SAMPLE = DECO / "sample.json"
ANNOTATION_SHEETS = {"Usage_Log", "Range_Annotations_Data", "Annotation_Status_Data"}
PERSONAL = re.compile(
    r"\b\d{3}-\d{2}-\d{4}\b|\bssn\b|social security|birth|\bdob\b|passport|salar|@", re.IGNORECASE
)
MAX_LINES = 900
SEED = 20261104
HOLDOUT_SHARE = 77  # of 256, about 30%
QUOTAS = {"completed": 20, "not_applicable/form_template": 5, "not_applicable/report_balance": 5}
Gold = dict[str, Any]


def clean_snapshot(path: Path) -> dict[str, Any]:
    snapshot = read_file(path)
    snapshot["sheets"] = [s for s in snapshot["sheets"] if s["name"] not in ANNOTATION_SHEETS]
    return snapshot


def rows_of(book: Any, name: str) -> list[tuple[Any, ...]]:
    return list(book[name].iter_rows(values_only=True)) if name in book.sheetnames else []


def gold_of(path: Path) -> Gold:
    """Per sheet: status from DECO, and its tables with their header rows."""
    book = load_workbook(path)
    status_rows = rows_of(book, "Annotation_Status_Data")
    statuses: dict[str, str] = {}
    for row in status_rows[1:]:
        marks = dict(zip(status_rows[0], row, strict=True))
        if str(marks.get("Completed")).lower() == "true":
            statuses[str(marks["Name"])] = "completed"
        elif str(marks.get("Form/Template")).lower() == "true":
            statuses[str(marks["Name"])] = "form"
        elif str(marks.get("Report/Balance")).lower() == "true":
            statuses[str(marks["Name"])] = "report"
    annotation_rows = rows_of(book, "Range_Annotations_Data")
    tables: dict[str, dict[str, Any]] = {}
    heads: list[tuple[str, str]] = []
    for row in annotation_rows[1:]:
        marks = dict(zip(annotation_rows[0], row, strict=True))
        if marks["Annotation.Label"] == "Table":
            tables[str(marks["Annotation.Name"])] = {
                "sheet": str(marks["Sheet.Name"]),
                "range": str(marks["Annotation.Range"]).replace("$", ""),
                "headerRows": [],
            }
        if marks["Annotation.Label"] == "Header":
            heads.append(
                (str(marks["Annotation.Parent"]), str(marks["Annotation.Range"]).replace("$", ""))
            )
    for parent, cells in heads:
        if parent in tables:
            left, first, right, last = (int(value or 0) for value in range_boundaries(cells))
            # A tall, thin header is DECO's label column down the side, not a header row.
            if right - left + 1 >= last - first + 1:
                tables[parent]["headerRows"].extend(range(first, last + 1))
    sheets: dict[str, Any] = {}
    for name, status in statuses.items():
        sheets[name] = {
            "status": status,
            "tables": [t for t in tables.values() if t["sheet"] == name],
        }
    return sheets


def sample() -> None:
    picked: list[dict[str, Any]] = []
    skipped = {"personal": 0, "long": 0, "unreadable": 0, "noStatus": 0}
    generator = random.Random(SEED)
    for folder, quota in QUOTAS.items():
        files = sorted((DECO / "x" / folder).glob("*.xlsx"))
        generator.shuffle(files)
        chosen = 0
        for path in files:
            if chosen == quota:
                break
            try:
                snapshot = clean_snapshot(path)
                gold = gold_of(path)
            except Exception:  # noqa: BLE001 - a file we can't read is simply not sampled
                skipped["unreadable"] += 1
                continue
            text = render(snapshot)
            if PERSONAL.search(text) or PERSONAL.search(
                " ".join(s["name"] for s in snapshot["sheets"])
            ):
                skipped["personal"] += 1
            elif len(text.splitlines()) > MAX_LINES:
                skipped["long"] += 1
            elif not set(gold) & {s["name"] for s in snapshot["sheets"]}:
                skipped["noStatus"] += 1
            else:
                picked.append(
                    {
                        "id": f"deco_{len(picked):03d}",
                        "group": folder,
                        "path": str(path.relative_to(DECO)),
                    }
                )
                chosen += 1
    SAMPLE.write_text(json.dumps(picked, indent=1) + "\n", encoding="utf-8")
    print(f"picked {len(picked)}, skipped {skipped}")


def split_of(path: Path, sampled: set[str]) -> str:
    """Fixed by file name, so a workbook never changes side."""
    if str(path.relative_to(DECO)) in sampled:
        return "holdout"
    return "holdout" if hashlib.sha256(path.name.encode()).digest()[0] < HOLDOUT_SHARE else "tune"


def snapshot_cached(path: Path) -> dict[str, Any]:
    cached = DECO / "cache" / (hashlib.sha256(path.name.encode()).hexdigest() + ".pickle")
    if cached.exists():
        return dict(pickle.loads(cached.read_bytes()))  # noqa: S301 - written by this script, private folder
    snapshot = clean_snapshot(path)
    cached.parent.mkdir(exist_ok=True)
    cached.write_bytes(pickle.dumps(snapshot))
    return snapshot


def rule_result(path: Path) -> dict[str, Any] | None:
    """One workbook's tables and headers against DECO's. Ranges and counts only, no cell text."""
    try:
        gold, snapshot = gold_of(path), snapshot_cached(path)
        found = from_analysis(analyze_snapshot(snapshot))
    except Exception as error:  # noqa: BLE001 - counted and reported, not hidden
        return {"file": path.name, "failed": type(error).__name__}
    names = {sheet["name"] for sheet in snapshot["sheets"]}
    sheets = []
    for name, sheet in gold.items():
        if name in names:
            sheets.append(
                {
                    "name": name,
                    "status": sheet["status"],
                    "gold": [t["range"] for t in sheet["tables"]],
                    "goldHeaders": sorted(
                        {row for t in sheet["tables"] for row in t["headerRows"]}
                    ),
                    "found": found.tables.get(name, []),
                    "foundHeaders": sorted(
                        row for owner, row in found.header_rows if owner == name
                    ),
                    "outcome": found.outcomes.get(name),
                }
            )
    return {"file": path.name, "sheets": sheets}


def error_class(sheet: dict[str, Any]) -> str:
    gold, found = sheet["gold"], sheet["found"]
    if sorted(gold) == sorted(found):
        return "exact"
    if match_tables(gold, found, 2) == len(gold) == len(found):
        return "near"
    if not found:
        return "none found"
    if len(found) > len(gold):
        return "too many"
    if len(found) < len(gold):
        return "too few"
    return "same count, wrong ranges"


def rules(split: str, write: Path | None) -> None:
    sampled = {item["path"] for item in json.loads(SAMPLE.read_text(encoding="utf-8"))}
    paths = [
        path
        for folder in ("completed", "not_applicable/form_template", "not_applicable/report_balance")
        for path in sorted((DECO / "x" / folder).glob("*.xlsx"))
        if split_of(path, sampled) == split
    ]
    with ProcessPoolExecutor() as pool:
        results = [item for item in pool.map(rule_result, paths, chunksize=4) if item is not None]
    failed = [item for item in results if "failed" in item]
    sheets = [sheet for item in results if "sheets" in item for sheet in item["sheets"]]
    done = [sheet for sheet in sheets if sheet["status"] == "completed"]
    tallies = {"tp": 0, "fp": 0, "fn": 0, "exactTp": 0, "hTp": 0, "hFp": 0, "hFn": 0}
    for sheet in done:
        near, exact = (
            match_tables(sheet["gold"], sheet["found"], 2),
            match_tables(sheet["gold"], sheet["found"], 0),
        )
        tallies["tp"] += near
        tallies["exactTp"] += exact
        tallies["fp"] += len(sheet["found"]) - near
        tallies["fn"] += len(sheet["gold"]) - near
        gold_rows, found_rows = set(sheet["goldHeaders"]), set(sheet["foundHeaders"])
        tallies["hTp"] += len(gold_rows & found_rows)
        tallies["hFp"] += len(found_rows - gold_rows)
        tallies["hFn"] += len(gold_rows - found_rows)
    gold_total = tallies["tp"] + tallies["fn"]
    found_total = tallies["tp"] + tallies["fp"]
    print(f"{split}: {len(paths)} workbooks, {len(failed)} failed, {len(done)} table sheets")
    print(f"tables near f1 {2 * tallies['tp'] / max(1, gold_total + found_total):.3f}")
    print(f"tables exact f1 {2 * tallies['exactTp'] / max(1, gold_total + found_total):.3f}")
    header_total = 2 * tallies["hTp"] + tallies["hFp"] + tallies["hFn"]
    print(f"headers f1 {2 * tallies['hTp'] / max(1, header_total):.3f}")
    print("sheets by result:", dict(Counter(error_class(sheet) for sheet in done).most_common()))
    print(
        "sheet outcome when no table found:",
        dict(Counter(sheet["outcome"] for sheet in done if not sheet["found"]).most_common()),
    )
    aside = [sheet for sheet in sheets if sheet["status"] != "completed"]
    print(
        f"set-aside sheets left with no table: {sum(not sheet['found'] for sheet in aside)}/{len(aside)}"
    )
    if write:
        write.write_text(json.dumps(results, ensure_ascii=False) + "\n", encoding="utf-8")


def label_one(item: dict[str, Any], model: str) -> str:
    tag = f"deco-{model}"
    out = DECO / "runs" / model
    out.mkdir(parents=True, exist_ok=True)
    folder = prepare(item["id"], clean_snapshot(DECO / item["path"]), tag)
    try:
        done = ask_agent(folder, model)
    except subprocess.TimeoutExpired:
        return "timed out"
    final = final_event(done.stdout)
    total = len((folder / "workbook.txt").read_text(encoding="utf-8").splitlines())
    facts: dict[str, Any] = {
        "costUsd": final.get("total_cost_usd"),
        "seconds": round(float(final.get("duration_ms") or 0) / 1000),
        "fullRead": lines_read(done.stdout, total) >= total,
        "outcome": "ok",
    }
    answer_path = folder / "label.json"
    if outside_paths(done.stdout, folder):
        facts["outcome"] = "not blind"
    elif not answer_path.exists():
        facts["outcome"] = "no label"
    else:
        answer = json.loads(answer_path.read_text(encoding="utf-8"))
        built = {
            "labelVersion": 1,
            "id": item["id"],
            "workbookSha256": "0" * 64,
            "status": "draft",
            "resultsFrom": "none",
            "sheets": answer.get("sheets", []),
            "relations": answer.get("relations", []),
            "formulas": [],
        }
        if schema_problems(built):
            facts["outcome"] = "invalid"
        else:
            (out / f"{item['id']}.json").write_text(
                json.dumps(built, ensure_ascii=False) + "\n", encoding="utf-8"
            )
    (out / f"{item['id']}.run.json").write_text(json.dumps(facts) + "\n", encoding="utf-8")
    return str(facts["outcome"])


def only_scored(predictions: Predictions, names: set[str]) -> Predictions:
    kept = Predictions()
    kept.tables = {name: ranges for name, ranges in predictions.tables.items() if name in names}
    kept.outcomes = {name: kind for name, kind in predictions.outcomes.items() if name in names}
    kept.header_rows = {(name, row) for name, row in predictions.header_rows if name in names}
    return kept


def pseudo_label(item_id: str, sheets: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item_id,
        "resultsFrom": "none",
        "relations": [],
        "formulas": [],
        "sheets": [
            {
                "name": name,
                "kind": "register",
                "tables": [
                    {"range": t["range"], "headerRows": t["headerRows"], "fields": []}
                    for t in sheet["tables"]
                ],
            }
            for name, sheet in sheets.items()
        ],
    }


def tally(picked: list[dict[str, Any]], read: Any) -> None:
    """Tables and headers on sheets DECO's people completed; form and report calls on those they set aside."""
    scored, right, total = [], 0, 0
    for item in picked:
        gold = gold_of(DECO / item["path"])
        other = read(item)
        if other is None:
            continue
        done = {name: sheet for name, sheet in gold.items() if sheet["status"] == "completed"}
        if done:
            scored.append(
                score_workbook(
                    item["id"],
                    "deco",
                    pseudo_label(item["id"], done),
                    only_scored(other, set(done)),
                    False,
                )
            )
        for name, sheet in gold.items():
            if sheet["status"] != "completed":
                total += 1
                right += not other.tables.get(name)
    metrics = compute_metrics(scored)
    shown = {
        key: round(float(metrics[key] or 0), 2)
        for key in ("tables.exact.f1", "tables.near.f1", "headers.f1")
    }
    print(f"  {shown}  no table on set-aside sheets: {right}/{total}, workbooks {len(scored)}")


def stored(model: str, item: dict[str, Any]) -> Predictions | None:
    path = DECO / "runs" / model / f"{item['id']}.json"
    return as_predictions(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else None


def score(tags: list[str]) -> None:
    picked = json.loads(SAMPLE.read_text(encoding="utf-8"))
    for tag in tags:
        facts = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in (DECO / "runs" / tag).glob("*.run.json")
        ]
        print(
            f"{tag}: ok {sum(f['outcome'] == 'ok' for f in facts)}/{len(facts)}, "
            f"full read {sum(f['fullRead'] for f in facts)}, "
            f"${sum(float(f['costUsd'] or 0) for f in facts):.2f}, {sum(f['seconds'] for f in facts)} s"
        )
        tally(picked, lambda item, tag=tag: stored(tag, item))
    print("daftar:")
    tally(picked, lambda item: from_analysis(analyze_snapshot(clean_snapshot(DECO / item["path"]))))
    if len(tags) >= 2:
        agree_right = agree_wrong = split_first_right = split_second_right = split_total = 0
        for item in picked:
            gold = gold_of(DECO / item["path"])
            a, b = stored(tags[0], item), stored(tags[1], item)
            if a is None or b is None:
                continue
            for name, sheet in gold.items():
                if sheet["status"] != "completed":
                    continue
                key = [t["range"] for t in sheet["tables"]]
                first, second = a.tables.get(name, []), b.tables.get(name, [])

                def fits(found: list[str], key: list[str] = key) -> bool:
                    return match_tables(key, found, 2) == len(key) == len(found)

                if sorted(first) == sorted(second):
                    agree_right += fits(first)
                    agree_wrong += not fits(first)
                else:
                    split_total += 1
                    split_first_right += fits(first)
                    split_second_right += fits(second)
        print(
            f"sheets where {tags[0]} and {tags[1]} marked the same tables: {agree_right + agree_wrong}, "
            f"of which matching DECO within 2 cells: {agree_right}"
        )
        print(
            f"sheets where they differ: {split_total}, "
            f"{tags[0]} matched DECO on {split_first_right}, {tags[1]} on {split_second_right}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sample")
    run = commands.add_parser("label")
    run.add_argument("--model", required=True)
    run.add_argument("--workers", type=int, default=4)
    report = commands.add_parser("score")
    report.add_argument("--tags", nargs="+", required=True)
    check = commands.add_parser("rules")
    check.add_argument("--split", choices=("tune", "holdout"), required=True)
    check.add_argument("--write", type=Path)
    args = parser.parse_args()
    if args.command == "sample":
        sample()
    elif args.command == "label":
        picked = json.loads(SAMPLE.read_text(encoding="utf-8"))
        with ThreadPoolExecutor(args.workers) as pool:
            outcomes = list(pool.map(lambda item: label_one(item, args.model), picked))
        print({outcome: outcomes.count(outcome) for outcome in set(outcomes)})
    elif args.command == "rules":
        rules(args.split, args.write)
    else:
        score(args.tags)


if __name__ == "__main__":
    main()
