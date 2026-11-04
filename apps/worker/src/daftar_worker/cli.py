"""The `daftar` command (C-5). Exit codes: 0 ok, 2 unreadable input, 3 validation error."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from daftar_worker.analyser import analyze
from daftar_worker.census import iter_files, render_markdown, run_census
from daftar_worker.errors import MESSAGES, WorkerError
from daftar_worker.evaluation.labels import EvalError, freeze_test_split, read_manifest
from daftar_worker.evaluation.run import render_report, run_evaluation, write_drafts
from daftar_worker.formulas.parity import aggregate_parity, render_parity, run_parity
from daftar_worker.llm.client import settings_from_env
from daftar_worker.project.bundle import BundleError, build_bundle
from daftar_worker.project.files import (
    ProjectError,
    project_decide,
    project_generate,
    project_init,
    project_reanalyze,
)
from daftar_worker.project.generate import GenerationError
from daftar_worker.reader import read_file


EXIT_UNREADABLE = 2
EXIT_VALIDATION = 3


def _write_atomic(path: Path, text: str) -> None:
    """Write through a temporary file, so a failure never leaves a partial output behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def _read(args: argparse.Namespace) -> int:
    try:
        snapshot = read_file(args.file)
    except WorkerError as error:
        message = MESSAGES[error.code]
        print(f"{error.code}: {message['fr']}\n{message['ar']}", file=sys.stderr)
        return EXIT_UNREADABLE
    _write_atomic(Path(args.output), _dump(snapshot))
    return 0


def _analyze(args: argparse.Namespace) -> int:
    try:
        snapshot = read_file(args.file)
    except WorkerError as error:
        message = MESSAGES[error.code]
        print(f"{error.code}: {message['fr']}\n{message['ar']}", file=sys.stderr)
        return EXIT_UNREADABLE
    settings = None if args.no_llm else settings_from_env()
    _write_atomic(Path(args.output), _dump(analyze(snapshot, settings)))
    return 0


def _census(args: argparse.Namespace) -> int:
    missing = [path for path in args.paths if not Path(path).exists()]
    if missing:
        print(f"not found: {', '.join(missing)}", file=sys.stderr)
        return EXIT_UNREADABLE
    census = run_census(args.paths)
    output = Path(args.output)
    _write_atomic(output, _dump(census))
    _write_atomic(output.with_suffix(".md"), render_markdown(census))
    return 0


def _project(args: argparse.Namespace) -> int:
    folder = Path(args.folder)
    action = args.action
    try:
        if action == "init":
            result = project_init(Path(args.file), folder, None if args.no_llm else settings_from_env())
        elif action == "decide":
            result = project_decide(folder, args.accept or [], args.reject or [], args.accept_high, args.by)
        elif action == "reanalyze":
            result = project_reanalyze(folder, Path(args.file) if args.file else None, None if args.no_llm else settings_from_env())
        else:
            result = project_generate(folder)
    except WorkerError as error:
        message = MESSAGES[error.code]
        print(f"{error.code}: {message['fr']}\n{message['ar']}", file=sys.stderr)
        return EXIT_UNREADABLE
    except (GenerationError, ProjectError) as error:
        print(error, file=sys.stderr)
        return EXIT_VALIDATION
    print(_dump(result), end="")
    return 0


def _bundle(args: argparse.Namespace) -> int:
    try:
        result = build_bundle(Path(args.project), Path(args.output), args.tag, Path(args.images) if args.images else None)
    except BundleError as error:
        print(error, file=sys.stderr)
        return EXIT_VALIDATION
    print(_dump(result), end="")
    return 0


def _parity(args: argparse.Namespace) -> int:
    missing = [path for path in args.paths if not Path(path).exists()]
    if missing:
        print(f"not found: {', '.join(missing)}", file=sys.stderr)
        return EXIT_UNREADABLE
    records = []
    skipped = {"notExcel": 0, "noFormulas": 0, "unreadable": 0}
    seen: set[str] = set()
    for path in iter_files(args.paths):
        try:
            snapshot = read_file(path)
        except WorkerError:
            skipped["unreadable"] += 1
            continue
        sha256 = snapshot["source"]["sha256"]
        if sha256 in seen:
            continue
        seen.add(sha256)
        results_from = snapshot["source"]["resultsFrom"]
        if results_from != "excel":
            skipped["noFormulas" if results_from == "none" else "notExcel"] += 1
            continue
        record = run_parity(path, snapshot)
        record.pop("results")  # Cell values: the report keeps counts and function names only.
        record.pop("mismatches", None)
        records.append({"file": str(path), **record})
    report = aggregate_parity(records)
    output = Path(args.output)
    _write_atomic(output / "parity.json", _dump({"aggregate": report, "skipped": skipped, "workbooks": records}))
    _write_atomic(output / "parity.md", render_parity(report, skipped))
    return 0


def _eval_command(args: argparse.Namespace) -> int:
    labels = Path(args.labels)
    manifest = Path(args.manifest) if args.manifest else labels.parent / "manifest.csv"
    output = Path(args.output)
    analyses = Path(args.analyses) if args.analyses else None
    if args.freeze:
        if args.split != "test":
            raise EvalError("only the test split can be frozen")
        print(f"froze {freeze_test_split(read_manifest(manifest), manifest)} test workbooks")
        return 0
    if args.prelabel:
        outcome = write_drafts(labels, manifest, args.split, analyses, output)
        print(_dump(outcome), end="")
        return 0
    settings = None if args.no_llm else settings_from_env()
    report = run_evaluation(labels, manifest, args.split, analyses, settings)
    _write_atomic(output / "report.json", _dump(report))
    _write_atomic(output / "report.md", render_report(report))
    return 0


def _eval(args: argparse.Namespace) -> int:
    try:
        return _eval_command(args)
    except EvalError as error:
        print(error, file=sys.stderr)
        return EXIT_VALIDATION


def _label(args: argparse.Namespace) -> int:
    import uvicorn

    from daftar_worker.evaluation.label_screen import HOST, create_label_app

    labels = Path(args.labels)
    manifest = Path(args.manifest) if args.manifest else labels.parent / "manifest.csv"
    app = create_label_app(labels, manifest, args.who, args.port)
    print(f"open http://{HOST}:{args.port}", file=sys.stderr)
    uvicorn.run(app, host=HOST, port=args.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daftar")
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("read", help="read a workbook into a snapshot")
    read.add_argument("file")
    read.add_argument("-o", "--output", required=True)
    read.set_defaults(run=_read)
    analyze = commands.add_parser("analyze", help="understand a workbook")
    analyze.add_argument("file")
    analyze.add_argument("--no-llm", action="store_true", help="rules only")
    analyze.add_argument("-o", "--output", required=True)
    analyze.set_defaults(run=_analyze)
    census = commands.add_parser("census", help="count workbook features over files and folders")
    census.add_argument("paths", nargs="+", metavar="PATH")
    census.add_argument("-o", "--output", required=True)
    census.set_defaults(run=_census)
    project = commands.add_parser("project", help="a conversion project: decisions, then a spec")
    project.add_argument("action", choices=("init", "decide", "reanalyze", "generate"))
    project.add_argument("folder")
    project.add_argument("--file", help="the workbook, for init and reanalyze")
    project.add_argument("--accept", action="append", metavar="ID")
    project.add_argument("--reject", action="append", metavar="ID")
    project.add_argument("--accept-high", action="store_true", help="accept what the analyser is sure of")
    project.add_argument("--by", default="operator")
    project.add_argument("--no-llm", action="store_true")
    project.set_defaults(run=_project)
    bundle = commands.add_parser("bundle", help="a deployable folder for one client (C-8)")
    bundle.add_argument("project")
    bundle.add_argument("-o", "--output", required=True)
    bundle.add_argument("--tag", help="the image tag to pin, by default this version")
    bundle.add_argument("--images", help="a file from deploy/build-images.sh to put in the folder")
    bundle.set_defaults(run=_bundle)
    parity = commands.add_parser("parity", help="compare recomputed formulas with Excel's results")
    parity.add_argument("paths", nargs="+", metavar="PATH")
    parity.add_argument("-o", "--output", required=True, metavar="DIR")
    parity.set_defaults(run=_parity)
    evaluate = commands.add_parser("eval", help="score analyses against labels")
    evaluate.add_argument("--labels", required=True, metavar="DIR")
    evaluate.add_argument("--split", required=True, choices=("dev", "test"))
    evaluate.add_argument("-o", "--output", required=True, metavar="DIR")
    evaluate.add_argument("--analyses", metavar="DIR", help="existing C-2 analyses, <id>.json; default: run the analyser")
    evaluate.add_argument("--manifest", help="default: manifest.csv beside the labels folder")
    evaluate.add_argument("--prelabel", action="store_true", help="write draft labels to -o")
    evaluate.add_argument("--no-llm", action="store_true", help="rules only, even if a model is set")
    evaluate.add_argument("--freeze", action="store_true", help="record the test split as frozen")
    evaluate.set_defaults(run=_eval)
    label = commands.add_parser("label", help="correct labels in a screen on this machine")
    label.add_argument("--labels", required=True, metavar="DIR")
    label.add_argument("--who", required=True, help="the labeller's name, recorded on each review")
    label.add_argument("--manifest", help="default: manifest.csv beside the labels folder")
    label.add_argument("--port", type=int, default=8790)
    label.set_defaults(run=_label)
    args = parser.parse_args(argv)
    code: int = args.run(args)
    return code


if __name__ == "__main__":
    sys.exit(main())
