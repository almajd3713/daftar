"""Two labellers compared, against values worked out by hand."""

from collections import Counter
import json
from pathlib import Path
from typing import Any

import pytest

from daftar_worker.cli import main
from daftar_worker.evaluation.agreement import cohen_kappa, compare_all, compare_folders


def label(sheets: list[dict[str, Any]], relations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "labelVersion": 1,
        "id": "x",
        "workbookSha256": "0" * 64,
        "status": "draft",
        "resultsFrom": "none",
        "workbook": {},
        "sheets": sheets,
        "relations": relations or [],
        "formulas": [],
        "labelledBy": ["someone"],
    }


def sheet(name: str, kind: str, tables: list[dict[str, Any]], group: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"name": name, "kind": kind, "regions": [], "tables": tables}
    if group:
        out["periodGroup"] = group
    return out


def table(rng: str, header: int, fields: dict[str, str]) -> dict[str, Any]:
    return {
        "range": rng,
        "headerRows": [header],
        "totalRows": [],
        "fields": [{"column": column, "name": column, "type": kind} for column, kind in fields.items()],
    }


def test_kappa_by_hand() -> None:
    pairs = Counter({("a", "a"): 20, ("a", "b"): 5, ("b", "a"): 10, ("b", "b"): 15})
    observed = 35 / 50
    expected = (25 / 50) * (30 / 50) + (25 / 50) * (20 / 50)
    assert cohen_kappa(pairs) == pytest.approx((observed - expected) / (1 - expected))
    assert cohen_kappa(pairs) == pytest.approx(0.4)


def test_kappa_says_nothing_when_only_one_category_exists() -> None:
    assert cohen_kappa(Counter({("a", "a"): 9})) is None
    assert cohen_kappa(Counter()) is None


def test_same_labels_agree_fully() -> None:
    one = label([sheet("A", "register", [table("A1:B9", 1, {"A": "text", "B": "date"})]), sheet("B", "ledger", [table("A1:B9", 1, {"A": "text", "B": "money"})])])
    metrics = compare_all({"w": (one, one)})["metrics"]
    for name in ("tables.exact.f1", "tables.near.f1", "headers.f1", "kind.kappa", "type.kappa", "type.shared"):
        assert metrics[name]["value"] == 1.0, name


def test_differences_by_hand() -> None:
    first = label(
        [
            sheet("A", "register", [table("A1:B9", 1, {"A": "text", "B": "date"})]),
            sheet("B", "ledger", [table("A1:C9", 2, {"A": "text", "B": "money", "C": "text"})]),
        ]
    )
    second = label(
        [
            sheet("A", "register", [table("A1:B9", 1, {"A": "text", "B": "text"})]),
            sheet("B", "register", [table("A1:C12", 2, {"A": "text", "B": "money"})]),
        ]
    )
    metrics = compare_all({"w": (first, second)})["metrics"]
    # One of two tables is exact; the other is 3 rows off, so outside the 2-cell tolerance too.
    assert metrics["tables.exact.f1"]["value"] == pytest.approx(0.5)
    assert metrics["tables.near.f1"]["value"] == pytest.approx(0.5)
    assert metrics["headers.f1"]["value"] == pytest.approx(1.0)
    # Kinds: (reg, reg) and (ledger, reg). Observed .5, expected .5 * 1 = .5, so kappa is 0.
    assert metrics["kind.kappa"]["value"] == pytest.approx(0.0)
    # Fields: 4 paired of 5 in the first and 4 in the second, so 8 of 9.
    assert metrics["type.shared"]["value"] == pytest.approx(8 / 9)
    # Types: (text, text) x2, (date, text), (money, money). Observed .75.
    # first: text 2, date 1, money 1; second: text 3, money 1. Expected (2*3 + 1*1) / 16.
    assert metrics["type.kappa"]["value"] == pytest.approx((0.75 - 7 / 16) / (1 - 7 / 16))


def test_folders_compare_only_what_both_hold(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = label([sheet("A", "register", [table("A1:B9", 1, {"A": "text"})])])
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "both.json").write_text(json.dumps(good), encoding="utf-8")
    (right / "both.json").write_text(json.dumps(good), encoding="utf-8")
    (left / "one.json").write_text(json.dumps(good), encoding="utf-8")
    (left / "both.run.json").write_text("{}", encoding="utf-8")  # A harness file: not a label.
    (right / "bad.json").write_text("{}", encoding="utf-8")
    report = compare_folders(left, right)
    assert report["ids"] == ["both"]
    assert report["onlyFirst"] == ["one"]
    assert report["refused"] == ["bad"]
    output = tmp_path / "agreement.json"
    assert main(["agreement", str(left), str(right), "-o", str(output)]) == 0
    assert output.with_suffix(".md").read_text(encoding="utf-8").startswith("# Labeller agreement on 1 workbooks")
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["agreement", str(left), str(empty), "-o", str(tmp_path / "none.json")]) == 3
