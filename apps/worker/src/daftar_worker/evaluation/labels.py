"""Load and check the manifest and labels (C-6), and enforce the dev/test split."""

import csv
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any, cast

from jsonschema import Draft202012Validator


COLUMNS = ["id", "source", "licence", "language", "stratum", "split", "consent", "sha256"]
SPLITS = ("dev", "test")
LANGUAGES = ("fr", "ar", "mixed", "en")
STRATA = ("register", "ledger", "formulaModel", "tracker", "distractor", "stress")
# Reported only under its own name: oversampled rare features would bend the headline.
SEPARATE_STRATA = ("stress",)
SHA256 = re.compile(r"^[0-9a-f]{64}\Z")
WORKBOOK_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}\Z")


class EvalError(ValueError):
    """The evaluation set breaks a rule. Every problem is listed, one per line."""


@dataclass(frozen=True)
class ManifestRow:
    id: str
    source: str
    licence: str
    language: str
    stratum: str
    split: str
    consent: str
    sha256: str


@lru_cache(maxsize=1)
def _label_validator() -> Draft202012Validator:
    schema = json.loads(Path(__file__).with_name("label.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def read_manifest(path: Path) -> list[ManifestRow]:
    if not path.exists():
        raise EvalError(f"no manifest at {path}")
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != COLUMNS:
            raise EvalError(f"{path}: columns must be {','.join(COLUMNS)}")
        rows = [ManifestRow(**cast(dict[str, str], row)) for row in reader]
    problems: list[str] = []
    ids: set[str] = set()
    splits_by_sha: dict[str, set[str]] = {}
    for number, row in enumerate(rows, start=2):
        where = f"{path.name} line {number}"
        if not WORKBOOK_ID.match(row.id):
            problems.append(f"{where}: bad id {row.id!r}")
        if row.id in ids:
            problems.append(f"{where}: duplicate id {row.id}")
        ids.add(row.id)
        if row.split not in SPLITS:
            problems.append(f"{where}: split must be one of {SPLITS}")
        if row.stratum not in STRATA:
            problems.append(f"{where}: stratum must be one of {STRATA}")
        if row.language not in LANGUAGES:
            problems.append(f"{where}: language must be one of {LANGUAGES}")
        if not SHA256.match(row.sha256):
            problems.append(f"{where}: sha256 must be 64 lowercase hex digits")
        if not row.licence.strip():
            problems.append(f"{where}: licence is required")
        splits_by_sha.setdefault(row.sha256, set()).add(row.split)
    for sha256, splits in sorted(splits_by_sha.items()):
        if len(splits) > 1:
            problems.append(f"{sha256[:12]}: the same workbook is in both splits, which leaks test data")
    if problems:
        raise EvalError("\n".join(problems))
    return rows


def freeze_path(manifest_path: Path) -> Path:
    return manifest_path.with_name("test-frozen.json")


def check_frozen(rows: list[ManifestRow], manifest_path: Path) -> bool:
    """Once frozen, the test split changes only by adding files. Returns whether it's frozen."""
    path = freeze_path(manifest_path)
    if not path.exists():
        return False
    frozen: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))["test"]
    current = {row.id: row for row in rows}
    problems = []
    for workbook_id, sha256 in sorted(frozen.items()):
        row = current.get(workbook_id)
        if row is None:
            problems.append(f"{workbook_id}: frozen test workbook was removed")
        elif row.split != "test":
            problems.append(f"{workbook_id}: frozen test workbook moved to {row.split}")
        elif row.sha256 != sha256:
            problems.append(f"{workbook_id}: frozen test workbook changed")
    if problems:
        raise EvalError("\n".join(problems))
    return True


def freeze_test_split(rows: list[ManifestRow], manifest_path: Path) -> int:
    """Record the current test split. Adds to an existing freeze; it can't drop anything."""
    check_frozen(rows, manifest_path)
    test = {row.id: row.sha256 for row in rows if row.split == "test"}
    if not test:
        raise EvalError("the test split is empty, so there's nothing to freeze")
    text = json.dumps({"test": dict(sorted(test.items()))}, indent=1) + "\n"
    freeze_path(manifest_path).write_text(text, encoding="utf-8")
    return len(test)


def check_label(label: Any, row: ManifestRow) -> list[str]:
    """Return every problem with one label, as `id: path: message`."""
    problems = []
    for error in sorted(_label_validator().iter_errors(label), key=lambda item: list(map(str, item.absolute_path))):
        path = "/".join(str(part) for part in error.absolute_path) or "(root)"
        problems.append(f"{row.id}: {path}: {error.message}")
    if problems:
        return problems
    if label["id"] != row.id:
        problems.append(f"{row.id}: id says {label['id']}")
    if label["workbookSha256"] != row.sha256:
        problems.append(f"{row.id}: workbookSha256 doesn't match the manifest")
    if label["status"] != "reviewed":
        problems.append(f"{row.id}: still a draft; a person must correct it and mark it reviewed")
    names = [sheet["name"] for sheet in label["sheets"]]
    if len(names) != len(set(names)):
        problems.append(f"{row.id}: duplicate sheet names")
    return problems


def load_labels(labels_dir: Path, rows: list[ManifestRow]) -> dict[str, dict[str, Any]]:
    labels: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for row in rows:
        path = labels_dir / f"{row.id}.json"
        if not path.exists():
            problems.append(f"{row.id}: no label at {path}")
            continue
        try:
            label = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            problems.append(f"{row.id}: not valid JSON: {error}")
            continue
        found = check_label(label, row)
        problems.extend(found)
        if not found:
            labels[row.id] = label
    if problems:
        raise EvalError("\n".join(problems))
    return labels
