"""Run a blind labelling agent on workbooks from the manifest, and compare it with human labels.

    uv run python eval/blind/run.py label --model sonnet --run 1 sb_2768 rp_ar_atelier
    uv run python eval/blind/run.py compare --tag sonnet-1 sb_2768
    uv run python eval/blind/run.py models sb_2768 rp_ar_atelier --tags opus-1 opus-2 sonnet-1 haiku-1
    uv run python eval/blind/run.py review sb_2768 rp_ar_atelier --tags opus-3 sonnet-3

Each run gets an empty folder outside the repository with only that workbook, the guide and the label
format. Its tools are limited to reading and writing there, and its log is checked afterwards. It never
sees the analyser, its guesses, or a person's labels. Results stay in eval/private/agent/<model>-<run>/.
"""

import argparse
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import json
from pathlib import Path
import subprocess
from typing import Any

from openpyxl.utils import range_boundaries

from daftar_worker.analyser import analyze_snapshot
from daftar_worker.evaluation.labels import (
    ManifestRow,
    check_against_workbook,
    read_manifest,
    schema_problems,
)
from daftar_worker.evaluation.metrics import compute_metrics, score_workbook
from daftar_worker.evaluation.predictions import (
    Predictions,
    from_analysis,
    label_as_predictions,
)
from daftar_worker.evaluation.run import draft_label, workbook_path
from daftar_worker.reader import read_file


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "eval" / "manifest.csv"
RESULTS = ROOT / "eval" / "private" / "agent"
WORK = Path.home() / ".cache" / "daftar" / "blind"
TIMEOUT_SECONDS = 1500
METRICS = (
    "tables.exact.f1",
    "tables.near.f1",
    "headers.f1",
    "type.macroAccuracy",
    "kind.accuracy",
    "relations.f1",
    "periodTabs.f1",
)

TASK = """You are labelling one spreadsheet workbook by hand, for a dataset of labelled workbooks.

Files in this folder, all you need:
- workbook.txt: every sheet and every non-empty cell of the workbook. It may be long, so read all of it.
- GUIDE.md: the labelling rules. Follow them exactly.
- label.schema.json: the format. See "$defs/sheet" and "$defs/relation".
- skeleton.json: the sheet names to start from.

Decide what the workbook really contains, as a careful person would. Then write ./label.json:

{"sheets": [...], "relations": [...], "notes": "...", "unsure": ["..."]}

- "sheets" has one entry per sheet in skeleton.json, in the format of the schema, with "name", "kind", "regions" and "tables". A notConverted sheet also needs "reason".
- A table's "range" includes its header and total rows. Give a field for each column, with "column", "name" and "type". Use the header text as the name.
- "notes" says briefly what the workbook is. "unsure" lists each decision you weren't sure about, one short line per decision, naming the sheet and cell or column.

Use only the files in this folder. Write label.json once you've decided, then stop.
"""


def row_of(workbook_id: str) -> ManifestRow:
    return next(row for row in read_manifest(MANIFEST) if row.id == workbook_id)


def snapshot_of(row: ManifestRow) -> dict[str, Any]:
    path = workbook_path(MANIFEST, row)
    if path is None:
        raise SystemExit(f"{row.id}: no file here")
    return read_file(path)


def render(snapshot: dict[str, Any]) -> str:
    lines: list[str] = []
    for sheet in snapshot["sheets"]:
        lines.append(
            f"\n=== SHEET {sheet['name']!r} state={sheet['state']} used={sheet['dimension']} rightToLeft={sheet['rtl']}"
        )
        for key, label in (
            ("merges", "merged"),
            ("hiddenRows", "hidden rows"),
            ("hiddenColumns", "hidden columns"),
        ):
            if sheet[key]:
                lines.append(f"{label}: {sheet[key]}")
        for item in sheet["validations"]:
            lines.append(
                f"validation: {item['ranges']} type={item['type']} source={item.get('formula1')}"
            )
        for item in sheet["conditionalFormats"]:
            lines.append(f"conditional format: {item['ranges']} type={item['type']}")
        for cell in sheet["cells"]:
            style = cell.get("style") or {}
            if cell.get("v") is None and not cell.get("f") and not cell.get("comment"):
                continue
            parts = [cell["ref"], repr(cell.get("v"))]
            if cell.get("f"):
                parts.append(f"formula {cell['f']}")
            if cell.get("fmt"):
                parts.append(f"format {cell['fmt']}")
            if style.get("fill"):
                parts.append(f"fill {style['fill']}")
            if style.get("bold"):
                parts.append("bold")
            if cell.get("comment"):
                parts.append(f"comment {cell['comment']!r}")
            lines.append(" | ".join(parts))
    if snapshot.get("unsupported"):
        lines.append(
            "\n=== NOT SHOWN ABOVE: "
            + ", ".join(sorted({f"{item['kind']}" for item in snapshot["unsupported"]}))
        )
    return "\n".join(lines) + "\n"


def english_guide() -> str:
    text = (ROOT / "eval" / "LABELLING.md").read_text(encoding="utf-8")
    start, end = text.index("## English"), text.index("## Français")
    return text[start:end].replace("---", "").strip() + "\n"


def prepare(workbook_id: str, snapshot: dict[str, Any], tag: str) -> Path:
    folder = WORK / tag / workbook_id
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():
        old.unlink()
    (folder / "workbook.txt").write_text(render(snapshot), encoding="utf-8")
    (folder / "GUIDE.md").write_text(english_guide(), encoding="utf-8")
    schema = ROOT / "apps/worker/src/daftar_worker/evaluation/label.schema.json"
    (folder / "label.schema.json").write_text(schema.read_text(encoding="utf-8"), encoding="utf-8")
    names = [{"name": sheet["name"]} for sheet in snapshot["sheets"]]
    (folder / "skeleton.json").write_text(
        json.dumps({"sheets": names}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return folder


def outside_paths(log: str, folder: Path) -> list[str]:
    """Every tool call that named something outside the folder, or wasn't a read or a write."""
    bad = []
    for line in log.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            target = str((block.get("input") or {}).get("file_path", ""))
            inside = Path(target).resolve().is_relative_to(folder.resolve()) if target else False
            if block.get("name") not in ("Read", "Write") or not inside:
                bad.append(f"{block.get('name')} {target}")
    return bad


def lines_read(log: str, total: int) -> int:
    """How many lines of workbook.txt the run actually got back, so a partial read can't pass unnoticed."""
    calls: dict[str, dict[str, Any]] = {}
    seen: set[int] = set()
    for line in log.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and str(
                (block.get("input") or {}).get("file_path", "")
            ).endswith("workbook.txt"):
                calls[str(block.get("id"))] = block["input"]
            if (
                block.get("type") == "tool_result"
                and str(block.get("tool_use_id")) in calls
                and not block.get("is_error")
            ):
                asked = calls[str(block.get("tool_use_id"))]
                start = int(asked.get("offset") or 1)
                seen.update(
                    range(start, min(total, start + int(asked.get("limit") or 2000) - 1) + 1)
                )
    return len(seen)


def final_event(log: str) -> dict[str, Any]:
    for line in reversed(log.splitlines()):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            return dict(event)
    return {}


def model_used(log: str) -> str | None:
    for line in log.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            return str(event.get("model"))
    return None


def ask_agent(folder: Path, model: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "claude",
            "-p",
            TASK,
            "--model",
            model,
            "--tools",
            "Read,Write",
            "--allowedTools",
            "Read(./**)",
            "Edit(./**)",
            "--permission-mode",
            "dontAsk",
            "--strict-mcp-config",
            "--setting-sources",
            "project",
            "--output-format",
            "stream-json",
            "--verbose",
        ],
        cwd=folder,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
        stdin=subprocess.DEVNULL,
    )


def label(workbook_id: str, model: str, run: int) -> None:
    tag = f"{model}-{run}"
    row = row_of(workbook_id)
    snapshot = snapshot_of(row)
    folder = prepare(row.id, snapshot, tag)
    out = RESULTS / tag
    out.mkdir(parents=True, exist_ok=True)
    try:
        done = ask_agent(folder, model)
    except subprocess.TimeoutExpired:
        print(f"{tag} {workbook_id}: timed out")
        return
    (out / f"{workbook_id}.log.jsonl").write_text(done.stdout, encoding="utf-8")
    final = final_event(done.stdout)
    total = len((folder / "workbook.txt").read_text(encoding="utf-8").splitlines())
    facts: dict[str, Any] = {
        "model": model_used(done.stdout),
        "costUsd": final.get("total_cost_usd"),
        "seconds": round(float(final.get("duration_ms") or 0) / 1000),
        "lines": total,
        "linesRead": lines_read(done.stdout, total),
        "outcome": "ok",
    }
    answer_path = folder / "label.json"
    bad = outside_paths(done.stdout, folder)
    if bad:
        facts["outcome"] = f"NOT BLIND, discarded: {bad[:5]}"
    elif not answer_path.exists():
        facts["outcome"] = f"no label (exit {done.returncode})"
    else:
        try:
            answer = json.loads(answer_path.read_text(encoding="utf-8"))
            built = draft_label(row, snapshot, None)
            built.update(
                sheets=answer["sheets"],
                relations=answer.get("relations", []),
                labelledBy=[f"blind-agent:{tag}"],
            )
            built["workbook"] = {**built["workbook"], "notes": str(answer.get("notes", ""))[:2000]}
            problems = schema_problems(built)
            warnings: list[Any] = []
            if not problems:
                problems, warnings = check_against_workbook(built, snapshot)
            facts.update(problems=problems, warnings=len(warnings), unsure=answer.get("unsure", []))
            if problems:
                facts["outcome"] = "invalid"
            (out / f"{workbook_id}.json").write_text(
                json.dumps(built, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
            )
        except (ValueError, KeyError, TypeError) as error:
            facts["outcome"] = f"unreadable: {error}"
    (out / f"{workbook_id}.run.json").write_text(
        json.dumps(facts, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(
        f"{tag} {workbook_id}: {facts['outcome']}, read {facts['linesRead']}/{total}, ${facts['costUsd']}, {facts['seconds']}s",
        flush=True,
    )


def differences(gold: dict[str, Any], other: Predictions) -> list[str]:
    lines = []
    for sheet in gold["sheets"]:
        name = sheet["name"]
        if other.outcomes.get(name) != sheet["kind"]:
            lines.append(f"{name}: kind {sheet['kind']} vs {other.outcomes.get(name)}")
        ours, theirs = (
            {table["range"] for table in sheet["tables"]},
            set(other.tables.get(name, [])),
        )
        if ours != theirs:
            lines.append(f"{name}: tables {sorted(ours)} vs {sorted(theirs)}")
        heads = {row for table in sheet["tables"] for row in table["headerRows"]}
        their_heads = {row for owner, row in other.header_rows if owner == name}
        if heads != their_heads:
            lines.append(f"{name}: header rows {sorted(heads)} vs {sorted(their_heads)}")
        for table in sheet["tables"]:
            _, low, _, high = range_boundaries(table["range"])
            for item in table["fields"]:
                found = [
                    p
                    for p in other.fields
                    if p.sheet == name
                    and p.column == item["column"]
                    and p.low_row <= int(high)
                    and p.high_row >= int(low)
                ]
                if found and found[0].type != item["type"]:
                    lines.append(
                        f"{name}!{item['column']} ({item['name'][:24]}): type {item['type']} vs {found[0].type}"
                    )
    ours_rel = {
        (i["from"]["sheet"], i["from"]["column"], i["to"]["sheet"], i["to"]["column"])
        for i in gold["relations"]
    }
    for item in sorted(ours_rel - other.relations):
        lines.append(f"relation only in the human label: {item}")
    for item in sorted(other.relations - ours_rel):
        lines.append(f"relation only in the other: {item}")
    return lines


def stored(tag: str, workbook_id: str) -> dict[str, Any] | None:
    """A run's label, if it was written and passed the checks."""
    path, facts = RESULTS / tag / f"{workbook_id}.json", RESULTS / tag / f"{workbook_id}.run.json"
    if not path.exists() or (
        facts.exists() and json.loads(facts.read_text(encoding="utf-8"))["outcome"] != "ok"
    ):
        return None
    return dict(json.loads(path.read_text(encoding="utf-8")))


def human_label(workbook_id: str) -> dict[str, Any] | None:
    path = ROOT / "eval" / "labels" / f"{workbook_id}.json"
    found = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return dict(found) if found and found["status"] == "reviewed" else None


def scores(row: ManifestRow, key: dict[str, Any], other: Predictions) -> dict[str, float | None]:
    metrics = compute_metrics([score_workbook(row.id, row.stratum, key, other, False)])
    return {
        name.replace(".f1", "").replace(".macroAccuracy", "").replace(".accuracy", ""): metrics.get(
            name
        )
        for name in METRICS
    }


def compare(workbook_id: str, tag: str) -> None:
    row = row_of(workbook_id)
    agent, human = stored(tag, workbook_id), human_label(workbook_id)
    print(f"\n##### {workbook_id}  {tag}  human label: {'reviewed' if human else 'none'}")
    if agent:
        print("agent notes:", agent["workbook"].get("notes", "")[:300])
    daftar = from_analysis(analyze_snapshot(snapshot_of(row)))
    if human is None:
        if agent:
            print("AGENT vs DAFTAR (agent as the key):")
            print(*differences(agent, daftar) or ["  no differences"], sep="\n  ")
        return
    for name, predictions in (
        ("agent", label_as_predictions(agent) if agent else None),
        ("daftar", daftar),
    ):
        if predictions is not None:
            print(
                f"{name} vs human:",
                {
                    key: None if value is None else round(value, 2)
                    for key, value in scores(row, human, predictions).items()
                },
            )
    if agent:
        print("HUMAN vs AGENT:")
        print(*differences(human, label_as_predictions(agent)) or ["  no differences"], sep="\n  ")


def table(title: str, rows: list[tuple[str, list[dict[str, float | None]]]]) -> None:
    columns = ("tables.exact", "headers", "type", "kind", "relations")
    print(
        f"\n{title}\n{'':<26}"
        + "".join(f"{column:>14}" for column in columns)
        + f"{'workbooks':>11}"
    )
    for name, results in rows:
        cells = []
        for column in columns:
            values = [value for item in results if (value := item[column]) is not None]
            cells.append(f"{sum(values) / len(values):>14.2f}" if values else f"{'-':>14}")
        print(f"{name:<26}" + "".join(cells) + f"{len(results):>11}")


def models(ids: list[str], tags: list[str]) -> None:
    """Every run against the people's labels and against other runs, plus what each run cost."""
    rows = {item: row_of(item) for item in ids}
    print(
        f"{'run':<12}{'model':<28}{'ok':>6}{'cost $':>9}{'seconds':>9}{'read all':>10}{'unsure':>8}"
    )
    for tag in tags:
        facts = [
            json.loads((RESULTS / tag / f"{item}.run.json").read_text(encoding="utf-8"))
            for item in ids
            if (RESULTS / tag / f"{item}.run.json").exists()
        ]
        fine = [item for item in facts if item["outcome"] == "ok"]
        print(
            f"{tag:<12}{str(facts[0]['model'] if facts else '-'):<28}{f'{len(fine)}/{len(ids)}':>6}"
            f"{sum(float(item['costUsd'] or 0) for item in facts):>9.2f}{sum(item['seconds'] for item in facts):>9}"
            f"{sum(item['linesRead'] >= item['lines'] for item in facts):>10}{sum(len(item.get('unsure', [])) for item in fine):>8}"
        )
        for item, fact in zip(
            [i for i in ids if (RESULTS / tag / f"{i}.run.json").exists()], facts, strict=True
        ):
            if fact["outcome"] != "ok":
                print(f"   {item}: {fact['outcome']} {str(fact.get('problems', ''))[:300]}")

    def against(
        key_of: Callable[[str], dict[str, Any] | None], tag: str
    ) -> list[dict[str, float | None]]:
        results = []
        for item in ids:
            key, other = key_of(item), stored(tag, item)
            if key is not None and other is not None:
                results.append(scores(rows[item], key, label_as_predictions(other)))
        return results

    table("AGAINST YOUR REVIEWED LABELS", [(tag, against(human_label, tag)) for tag in tags])
    daftar_rows = []
    for item in ids:
        key = human_label(item)
        if key is not None:
            daftar_rows.append(
                scores(rows[item], key, from_analysis(analyze_snapshot(snapshot_of(rows[item]))))
            )
    table("DAFTAR AGAINST YOUR REVIEWED LABELS", [("daftar", daftar_rows)])

    pairs = [(a, b) for index, a in enumerate(tags) for b in tags[index + 1 :]]
    table(
        "RUNS AGAINST EACH OTHER",
        [(f"{a} / {b}", against(partial(stored, a), b)) for a, b in pairs],
    )
    print("\nPER WORKBOOK, against the first run:")
    for tag in tags[1:]:
        for item in ids:
            key, other = stored(tags[0], item), stored(tag, item)
            if key and other:
                print(
                    f"  {tag:<10}{item:<22}",
                    {
                        name: None if value is None else round(value, 2)
                        for name, value in scores(rows[item], key, label_as_predictions(other)).items()
                        if name in ("tables.exact", "headers", "type", "kind", "relations")
                    },
                )


def review(ids: list[str], first: str, second: str) -> None:
    """Write what a person has to rule on. It names no model, so the choice isn't swayed by which one said it."""
    lines = [f"# To rule on: A is {first}'s label, B is {second}'s\n"]
    for item in ids:
        a, b = stored(first, item), stored(second, item)
        lines.append(f"\n## {item}\n")
        if a is None or b is None:
            lines.append(
                f"- A run has no usable label, so label again: A {'ok' if a else 'missing'}, B {'ok' if b else 'missing'}\n"
            )
            continue
        found = list(dict.fromkeys(differences(a, label_as_predictions(b))))
        lines.extend(
            f"- A vs B: {text.replace('human label', 'A').replace('the other', 'B')}\n"
            for text in found
        )
        facts = json.loads((RESULTS / first / f"{item}.run.json").read_text(encoding="utf-8"))
        lines.extend(f"- A unsure: {text}\n" for text in facts.get("unsure", []))
        if not found:
            lines.append("- A and B agree\n")
    out = RESULTS / f"review-{first}-{second}.md"
    out.write_text("".join(lines), encoding="utf-8")
    print(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("label")
    run.add_argument("--model", default="opus")
    run.add_argument("--run", type=int, default=1)
    run.add_argument("--workers", type=int, default=4)
    run.add_argument("ids", nargs="+")
    one = commands.add_parser("compare")
    one.add_argument("--tag", default="opus-1")
    one.add_argument("ids", nargs="+")
    many = commands.add_parser("models")
    many.add_argument("--tags", nargs="+", required=True)
    many.add_argument("ids", nargs="+")
    rule = commands.add_parser("review")
    rule.add_argument("--tags", nargs=2, required=True)
    rule.add_argument("ids", nargs="+")
    args = parser.parse_args()
    if args.command == "label":
        with ThreadPoolExecutor(args.workers) as pool:
            list(pool.map(lambda item: label(item, args.model, args.run), args.ids))
    elif args.command == "compare":
        for item in args.ids:
            compare(item, args.tag)
    elif args.command == "review":
        review(args.ids, *args.tags)
    else:
        models(args.ids, args.tags)


if __name__ == "__main__":
    main()
