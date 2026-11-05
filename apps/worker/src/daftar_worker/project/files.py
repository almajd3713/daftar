"""A project on disk: source, snapshot, analysis, then the generated spec and seed. Never in the repo."""

import json
from pathlib import Path
import shutil
from typing import Any

from daftar_worker.analyser import analyze
from daftar_worker.formulas.parity import run_parity
from daftar_worker.project.decisions import accept_high_confidence, decide, reapply
from daftar_worker.project.generate import Generator, write_project_outputs
from daftar_worker.reader import read_file


ANSWERS = "answers.json"


class ProjectError(ValueError):
    pass


def _write(path: Path, data: Any) -> None:
    # Whole or not at all: a crash halfway must not leave a person's decisions unreadable.
    partial = path.with_name(f"{path.name}.partial")
    partial.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    partial.replace(path)


def _read(path: Path) -> Any:
    if not path.exists():
        raise ProjectError(f"{path} doesn't exist: run `daftar project init` first")
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_source(file: Path, folder: Path) -> Path:
    target = folder / f"source{file.suffix.lower()}"
    for old in folder.glob("source.*"):
        old.unlink()
    shutil.copyfile(file, target)
    return target


def _source_of(folder: Path) -> Path:
    found = sorted(folder.glob("source.*"))
    if not found:
        raise ProjectError(f"no source workbook in {folder}")
    return found[0]


def project_init(file: Path, folder: Path, settings: Any = None, file_name: str | None = None) -> dict[str, Any]:
    snapshot = read_file(file, file_name)
    analysis = analyze(snapshot, settings)
    folder.mkdir(parents=True, exist_ok=True)
    _copy_source(file, folder)
    _write(folder / "snapshot.json", snapshot)
    _write(folder / "analysis.json", analysis)
    return {"findings": len(analysis["findings"]), "sheets": len(analysis["sheets"])}


def project_decide(folder: Path, accept: list[str], reject: list[str], accept_high: bool, by: str) -> dict[str, Any]:
    analysis = _read(folder / "analysis.json")
    by_id = {finding["id"]: finding for finding in analysis["findings"]}
    unknown = [item for item in [*accept, *reject] if item not in by_id]
    if unknown:
        raise ProjectError(f"unknown findings: {', '.join(unknown)}")
    accepted = accept_high_confidence(analysis, by) if accept_high else 0
    for item in accept:
        decide(by_id[item], "accepted", by)
    for item in reject:
        decide(by_id[item], "rejected", by)
    _write(folder / "analysis.json", analysis)
    return {
        "acceptedHigh": accepted,
        "accepted": sum(finding["decision"]["status"] == "accepted" for finding in analysis["findings"]),
        "rejected": sum(finding["decision"]["status"] == "rejected" for finding in analysis["findings"]),
        "pending": sum(finding["decision"]["status"] == "pending" for finding in analysis["findings"]),
    }


def project_reanalyze(folder: Path, file: Path | None, settings: Any = None, file_name: str | None = None) -> dict[str, Any]:
    """R-15: rerun, on the same workbook or an updated one, and carry the decisions over."""
    old = _read(folder / "analysis.json")
    # Read first: a file that can't be read must not replace the workbook this project is about.
    snapshot = read_file(file, file_name) if file else read_file(_source_of(folder), _read(folder / "snapshot.json")["source"]["fileName"])
    if file:
        _copy_source(file, folder)
    new = analyze(snapshot, settings)
    outcome = reapply(old, new)
    _write(folder / "snapshot.json", snapshot)
    _write(folder / "analysis.json", new)
    _write(folder / "conflicts.json", outcome["conflicts"])
    return {"applied": outcome["applied"], "moved": outcome["moved"], "conflicts": len(outcome["conflicts"])}


def project_answer(folder: Path, answer: dict[str, Any]) -> dict[str, Any]:
    """A reply to one of the generator's questions. It's kept apart from the analysis, which a rerun replaces."""
    path = folder / ANSWERS
    answers: dict[str, Any] = _read(path) if path.exists() else {"periodYears": {}, "retention": {}}
    if answer["kind"] == "periodYear":
        answers["periodYears"][answer["sheet"]] = answer["year"]
    else:
        answers["retention"][answer["entity"]] = answer["months"]
    _write(path, answers)
    return answers


def project_generate(folder: Path) -> dict[str, Any]:
    analysis = _read(folder / "analysis.json")
    snapshot = _read(folder / "snapshot.json")
    source = _source_of(folder)
    # R-19: a formula the engine gets wrong can't become a computed field. Only Excel's results judge.
    parity = run_parity(source, snapshot) if snapshot["source"]["resultsFrom"] == "excel" else None
    answers = _read(folder / ANSWERS) if (folder / ANSWERS).exists() else None
    spec, seed, report = Generator(analysis, snapshot, parity, answers).generate()
    write_project_outputs(folder, spec, seed, report)
    return {
        "entities": report.entities,
        "rows": dict(report.rows),
        "badValues": len(report.bad_values),
        "parityFailures": len(report.parity_failures),
        "questions": report.questions,
    }
