"""Every expected number here was worked out by hand from the fixture, in the comments."""

import copy
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import workbook_builders as builders

from daftar_worker.cli import main
from daftar_worker.evaluation.labels import (
    EvalError,
    ManifestRow,
    check_frozen,
    check_label,
    read_manifest,
)
from daftar_worker.evaluation.metrics import (
    WorkbookScore,
    bootstrap,
    compute_metrics,
    error_of_boundary,
    function_categories,
    match_tables,
    percentile_interval,
    results_match,
    score_workbook,
)
from daftar_worker.evaluation.predictions import from_analysis
from daftar_worker.evaluation.run import run_evaluation


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
FIELDS = "id,source,licence,language,stratum,split,consent,sha256"


def label(workbook_id: str = "a", sha256: str = SHA_A) -> dict[str, Any]:
    """Gold: 2 sheets; 2 tables on Clients and 1 on Mois; 3 header rows; 4 fields; 2 relations."""
    return {
        "labelVersion": 1,
        "id": workbook_id,
        "workbookSha256": sha256,
        "status": "reviewed",
        "resultsFrom": "excel",
        "sheets": [
            {
                "name": "Clients",
                "kind": "register",
                "regions": [{"range": "A1:C1", "type": "title"}],
                "tables": [
                    {
                        "range": "A2:C20",
                        "headerRows": [2],
                        "fields": [
                            {"column": "A", "name": "Nom", "type": "text"},
                            {"column": "B", "name": "Tél", "type": "phone"},
                            {"column": "C", "name": "Solde", "type": "money"},
                        ],
                    },
                    {"range": "E2:F9", "headerRows": [2], "fields": []},
                ],
            },
            {
                "name": "Mois",
                "kind": "ledger",
                "regions": [],
                "tables": [
                    {
                        "range": "A3:B30",
                        "headerRows": [3],
                        "fields": [{"column": "B", "name": "Montant", "type": "money"}],
                    }
                ],
            },
        ],
        "relations": [
            {"from": {"sheet": "Mois", "column": "A"}, "to": {"sheet": "Clients", "column": "A"}},
            {"from": {"sheet": "Mois", "column": "C"}, "to": {"sheet": "Clients", "column": "B"}},
        ],
        "formulas": [
            {"sheet": "Mois", "ref": "C4", "f": "=SUM(A1:A2)", "result": 10, "t": "n"},
            {"sheet": "Mois", "ref": "C5", "f": "=A1*2", "result": 3.5, "t": "n"},
            {"sheet": "Mois", "ref": "C6", "f": '=VLOOKUP(A1,Clients!A:B,2,FALSE)', "result": "Sara", "t": "s"},
            {"sheet": "Mois", "ref": "C7", "f": "=1/0", "result": "#DIV/0!", "t": "e"},
        ],
    }


def finding(kind: str, sheet: str, evidence: list[str], proposal: Any = None, status: str = "pending") -> dict[str, Any]:
    return {
        "id": f"{kind}-{sheet}-{evidence}",
        "kind": kind,
        "sheet": sheet,
        "evidence": evidence,
        "proposal": proposal or {},
        "decision": {"status": status},
    }


def relation(a: str, b: str, c: str, d: str) -> dict[str, Any]:
    return finding("relation", a, [], {"from": {"sheet": a, "column": b}, "to": {"sheet": c, "column": d}})


def analysis(sha256: str = SHA_A) -> dict[str, Any]:
    """With known errors, each one counted in test_known_errors_give_hand_computed_metrics."""
    return {
        "snapshotSha256": sha256,
        "engine": {"rulesVersion": "1", "model": "qwen3.5:9b", "quant": "Q4"},
        "sheets": [
            {"name": "Clients", "outcome": "register"},
            {"name": "Mois", "outcome": "tracker"},  # Wrong kind.
        ],
        "findings": [
            finding("table", "Clients", ["A2:C20"]),  # Exact.
            finding("table", "Clients", ["E2:F11"]),  # EoB 2: near only.
            finding("table", "Mois", ["A1:B30"]),  # EoB 2: near only.
            finding("table", "Mois", ["H1:J5"]),  # False positive at both.
            finding("table", "Mois", ["A3:B30"], status="rejected"),  # Rejected: ignored.
            finding("header", "Clients", ["A2:C2"]),  # Right.
            finding("header", "Mois", ["A3:B3"]),  # Right.
            finding("header", "Mois", ["A7:B7"]),  # False positive.
            finding("fieldType", "Clients", ["A3:A20"], {"type": "text"}),  # Right.
            finding("fieldType", "Clients", ["B3:B20"], {"type": "text"}),  # Wrong: phone.
            finding("fieldType", "Mois", ["B4:B30"], {"type": "money"}),  # Right.
            # Clients C has no prediction, so it's wrong.
            relation("Mois", "A", "Clients", "A"),  # Right.
            relation("Mois", "D", "Clients", "A"),  # False positive.
            # Mois C to Clients B is missed.
        ],
    }


PARITY = {
    "results": [
        {"sheet": "Mois", "ref": "C4", "value": 10.000000001},  # Within 1e-9 relative: 1e-10.
        {"sheet": "Mois", "ref": "C5", "value": 3.6},  # Wrong.
        {"sheet": "Mois", "ref": "C6", "value": "Sara"},  # Right.
        # C7 is missing, so it's wrong.
    ]
}


def test_known_errors_give_hand_computed_metrics() -> None:
    score = score_workbook("a", "register", label(), from_analysis(analysis(), PARITY))
    metrics = compute_metrics([score])
    # Tables, exact: 1 match of 4 predicted (rejected one ignored) and 3 gold.
    assert metrics["tables.exact.precision"] == pytest.approx(1 / 4)
    assert metrics["tables.exact.recall"] == pytest.approx(1 / 3)
    # Tables, within 2 cells: 3 matches of 4 predicted and 3 gold.
    assert metrics["tables.near.precision"] == pytest.approx(3 / 4)
    assert metrics["tables.near.recall"] == pytest.approx(3 / 3)
    # Headers: gold {Clients 2, Mois 3}; predicted adds Mois 7. tp 2, fp 1, fn 0: F1 = 4/5.
    assert metrics["headers.f1"] == pytest.approx(4 / 5)
    # Types: text 1/1; phone 0/1; money: Clients C wrong, Mois B right, 1/2. Mean of 1, 0, 1/2.
    assert metrics["type.macroAccuracy"] == pytest.approx(0.5)
    # Relations: tp 1, fp 1, fn 1.
    assert metrics["relations.precision"] == pytest.approx(1 / 2)
    assert metrics["relations.recall"] == pytest.approx(1 / 2)
    assert metrics["relations.f1"] == pytest.approx(1 / 2)
    # Kind: Clients right, Mois wrong.
    assert metrics["kind.accuracy"] == pytest.approx(1 / 2)
    assert score.confusion[("ledger", "tracker")] == 1
    # Parity: C4 and C6 of four.
    assert metrics["parity.share"] == pytest.approx(2 / 4)
    assert metrics["parity.category.math.share"] == 1.0  # SUM, C4.
    assert metrics["parity.category.operators.share"] == 0.0  # C5 and C7 are both wrong.
    assert metrics["parity.category.lookup.share"] == 1.0  # VLOOKUP, C6.


def test_pooling_across_workbooks_by_hand() -> None:
    first = score_workbook("a", "register", label(), from_analysis(analysis(), PARITY))
    # A perfect kind result on the second workbook: 2 of 2. Pooled: 3 of 4.
    second_analysis = analysis()
    second_analysis["sheets"][1]["outcome"] = "ledger"
    second = score_workbook("b", "ledger", label(), from_analysis(second_analysis, PARITY))
    assert compute_metrics([first, second])["kind.accuracy"] == pytest.approx(3 / 4)


def test_an_empty_analysis_scores_zero_recall() -> None:
    score = score_workbook("a", "register", label(), from_analysis({"sheets": [], "findings": []}))
    metrics = compute_metrics([score])
    assert metrics["tables.exact.recall"] == 0.0
    assert metrics["tables.exact.precision"] is None  # No predictions: undefined, not perfect.
    assert metrics["kind.accuracy"] == 0.0
    assert metrics["parity.share"] == 0.0
    assert score.confusion[("register", "(none)")] == 1


def test_results_not_from_excel_stay_out_of_parity() -> None:
    gold = label()
    gold["resultsFrom"] = "other"
    score = score_workbook("a", "register", gold, from_analysis(analysis(), PARITY))
    assert score.in_parity is False
    assert compute_metrics([score])["parity.share"] is None


@pytest.mark.parametrize(
    ("gold", "predicted", "error"),
    [
        ("A1:C10", "A1:C10", 0),
        ("A1:C10", "A1:C12", 2),
        ("A1:C10", "B3:C10", 2),
        ("A1:C10", "A1:C13", 3),
        ("A2:C10", "A1:D10", 1),
    ],
)
def test_error_of_boundary(gold: str, predicted: str, error: int) -> None:
    assert error_of_boundary(gold, predicted) == error


def test_three_cells_off_is_outside_the_near_tolerance() -> None:
    gold = label()
    gold["sheets"] = [gold["sheets"][1]]  # One gold table, A3:B30.
    result = {"sheets": [], "findings": [finding("table", "Mois", ["A3:B33"])]}  # EoB 3.
    metrics = compute_metrics([score_workbook("a", "register", gold, from_analysis(result))])
    assert metrics["tables.near.recall"] == 0.0
    assert metrics["tables.near.precision"] == 0.0


def test_a_table_matches_only_once() -> None:
    # Two predictions near one gold table: one match, the other is a false positive.
    assert match_tables(["A1:C10"], ["A1:C10", "A1:C11"], 2) == 1
    # One prediction near two gold tables: it can only fill one of them.
    assert match_tables(["A1:C10", "A1:C11"], ["A1:C10"], 2) == 1
    # The closest pairs win, leaving both gold tables matched.
    assert match_tables(["A1:C10", "A1:C12"], ["A1:C12", "A1:C10"], 2) == 2


@pytest.mark.parametrize(
    ("expected", "actual", "same"),
    [
        (1.0, 1.0, True),
        (1.0, 1.0 + 1e-10, True),
        (1.0, 1.0 + 1e-8, False),
        (1e12, 1e12 + 100, True),
        (0, 0.0, True),
        (0.0, 1e-16, False),  # R-19 gives a relative tolerance: near zero means exactly zero.
        ("a", "a", True),
        ("a", "A", False),
        (True, 1, False),  # Excel's TRUE isn't the number 1.
        (1, True, False),
        ("1", 1, False),
        (None, None, True),
        (None, 0, False),
        ("#DIV/0!", "#DIV/0!", True),
    ],
)
def test_results_match(expected: Any, actual: Any, same: bool) -> None:
    assert results_match(expected, actual) is same


def test_function_categories() -> None:
    assert function_categories("=A1+1") == {"operators"}
    assert function_categories("=IF(SUM(A1:A2)>0,VLOOKUP(A1,B:C,2),0)") == {"logical", "math", "lookup"}
    assert function_categories("=UNHEARDOF(1)") == {"other"}


# --- Bootstrap ----------------------------------------------------------------------------------


def _kind_score(workbook_id: str, correct: bool) -> WorkbookScore:
    score = WorkbookScore(workbook_id, "register", True)
    score.tallies["kind.total"] = 1
    score.tallies["kind.correct"] = int(correct)
    return score


def test_bootstrap_interval_by_hand() -> None:
    # 10 workbooks, 8 right. A resample's accuracy is Binomial(10, 0.8) / 10.
    # P(X<=4) = 0.0064 and P(X<=5) = 0.0328, so the 2.5th percentile is 0.5.
    # P(X<=9) = 0.8926, so the 97.5th percentile is 1.0.
    scores = [_kind_score(str(i), i < 8) for i in range(10)]
    assert bootstrap(scores)["kind.accuracy"] == [0.5, 1.0]


def test_bootstrap_resamples_workbooks_not_cells() -> None:
    # One workbook of 1000 sheets all right, one of 1000 all wrong. Pooled accuracy is 0.5, but with
    # 2 workbooks a resample holds only 0, 1 or 2 of the right one: 0, 0.5 or 1. Any cell-level
    # bootstrap would give a tight interval around 0.5 instead.
    good = WorkbookScore("good", "register", True)
    good.tallies.update({"kind.total": 1000, "kind.correct": 1000})
    bad = WorkbookScore("bad", "register", True)
    bad.tallies.update({"kind.total": 1000, "kind.correct": 0})
    assert compute_metrics([good, bad])["kind.accuracy"] == 0.5
    assert bootstrap([good, bad])["kind.accuracy"] == [0.0, 1.0]


def test_bootstrap_is_repeatable_and_empty_is_safe() -> None:
    scores = [_kind_score(str(i), i % 3 == 0) for i in range(12)]
    assert bootstrap(scores) == bootstrap(scores)
    assert bootstrap([]) == {}


def test_percentile_interval() -> None:
    assert percentile_interval([float(i) for i in range(101)]) == [2.0, 98.0]
    assert percentile_interval([1.0]) == [1.0, 1.0]


# --- Labels and the manifest --------------------------------------------------------------------


def _row(workbook_id: str = "a", sha256: str = SHA_A, stratum: str = "register", split: str = "dev") -> str:
    return f"{workbook_id},synthetic,CC-BY-4.0,fr,{stratum},{split},n/a,{sha256}"


def write_set(root: Path, rows: list[str], labels: dict[str, dict[str, Any]]) -> Path:
    (root / "labels").mkdir(parents=True, exist_ok=True)
    (root / "manifest.csv").write_text("\n".join([FIELDS, *rows]) + "\n", encoding="utf-8")
    for workbook_id, data in labels.items():
        (root / "labels" / f"{workbook_id}.json").write_text(json.dumps(data), encoding="utf-8")
    return root / "labels"


def write_analysis(folder: Path, workbook_id: str, data: dict[str, Any], parity: Any = None) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{workbook_id}.json").write_text(json.dumps(data), encoding="utf-8")
    if parity:
        (folder / f"{workbook_id}.parity.json").write_text(json.dumps(parity), encoding="utf-8")


def test_valid_label_has_no_problems() -> None:
    row = read_manifest_row()
    assert check_label(label(), row) == []


def read_manifest_row() -> ManifestRow:
    return ManifestRow("a", "synthetic", "CC-BY-4.0", "fr", "register", "dev", "n/a", SHA_A)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda d: d.update(status="draft"), "still a draft"),
        (lambda d: d.update(workbookSha256=SHA_B), "doesn't match the manifest"),
        (lambda d: d.update(id="other"), "id says other"),
        (lambda d: d["sheets"][0].update(kind="spreadsheet"), "sheets/0/kind"),
        (lambda d: d["sheets"][0].update(kind="notConverted"), "reason"),
        (lambda d: d["sheets"][0]["tables"][0].update(range="$A$1"), "sheets/0/tables/0/range"),
        (lambda d: d["sheets"][0]["tables"][0]["fields"][0].update(type="currency"), "fields/0/type"),
        (lambda d: d.pop("formulas"), "formulas"),
        (lambda d: d["sheets"].append(copy.deepcopy(d["sheets"][0])), "duplicate sheet"),
    ],
)
def test_bad_labels_are_refused(change: Any, expected: str) -> None:
    data = label()
    change(data)
    problems = check_label(data, read_manifest_row())
    assert any(expected in problem for problem in problems), problems


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([_row(), _row(sha256=SHA_B)], "duplicate id"),
        ([_row(split="train")], "split must be"),
        ([_row(stratum="misc")], "stratum must be"),
        ([_row(sha256="xyz")], "sha256"),
        ([_row("a", SHA_A, split="dev"), _row("b", SHA_A, split="test")], "both splits"),
    ],
)
def test_bad_manifests_are_refused(tmp_path: Path, rows: list[str], expected: str) -> None:
    write_set(tmp_path, rows, {})
    with pytest.raises(EvalError, match=expected):
        read_manifest(tmp_path / "manifest.csv")


def test_manifest_needs_its_exact_columns(tmp_path: Path) -> None:
    path = tmp_path / "manifest.csv"
    path.write_text("id,split\na,dev\n", encoding="utf-8")
    with pytest.raises(EvalError, match="columns must be"):
        read_manifest(path)


# --- The whole command --------------------------------------------------------------------------


@pytest.fixture
def evaluation_set(tmp_path: Path) -> tuple[Path, Path]:
    """Two dev workbooks and one in test, whose labels are broken to prove dev never reads them."""
    root = tmp_path / "eval"
    labels = write_set(
        root,
        [
            _row("a", SHA_A, "register", "dev"),
            _row("b", SHA_B, "stress", "dev"),
            _row("c", SHA_C, "ledger", "test"),
        ],
        {"a": label("a", SHA_A), "b": label("b", SHA_B), "c": {"broken": True}},
    )
    analyses = tmp_path / "analyses"
    write_analysis(analyses, "a", analysis(SHA_A), PARITY)
    write_analysis(analyses, "b", analysis(SHA_B), PARITY)
    return labels, analyses


def test_command_writes_stamped_reports(evaluation_set: tuple[Path, Path], tmp_path: Path) -> None:
    labels, analyses = evaluation_set
    out = tmp_path / "report"
    code = main(["eval", "--labels", str(labels), "--split", "dev", "--analyses", str(analyses), "-o", str(out)])
    assert code == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["split"] == "dev"
    assert report["engine"] == {"rulesVersion": ["1"], "model": ["qwen3.5:9b"], "quant": ["Q4"]}
    assert "sha" in report["git"] and "dirty" in report["git"]
    assert set(report["perWorkbook"]) == {"a", "b"}
    # The stress workbook is reported under its stratum and stays out of the headline.
    assert report["overall"]["workbooks"] == 1
    assert report["excludedFromHeadline"] == ["b"]
    assert set(report["byStratum"]) == {"register", "stress"}
    assert report["overall"]["metrics"]["kind.accuracy"]["value"] == 0.5
    assert report["overall"]["metrics"]["kind.accuracy"]["ci95"] == [0.5, 0.5]
    markdown = (out / "report.md").read_text(encoding="utf-8")
    assert "| Sheet kind: accuracy | 50.0 | 50.0–50.0 |" in markdown
    assert "qwen3.5:9b" in markdown
    assert "| ledger | tracker | 1 |" in markdown


def test_missing_analysis_scores_as_wrong_and_is_listed(evaluation_set: tuple[Path, Path]) -> None:
    labels, analyses = evaluation_set
    (analyses / "a.json").unlink()
    report = run_evaluation(labels, labels.parent / "manifest.csv", "dev", analyses)
    assert report["missingAnalyses"] == ["a"]
    assert report["overall"]["metrics"]["kind.accuracy"]["value"] == 0.0


def test_analysis_of_another_workbook_is_refused(evaluation_set: tuple[Path, Path], tmp_path: Path) -> None:
    labels, analyses = evaluation_set
    write_analysis(analyses, "a", analysis(SHA_C))
    args = ["eval", "--labels", str(labels), "--split", "dev", "--analyses", str(analyses), "-o", str(tmp_path / "o")]
    assert main(args) == 3


def test_test_report_has_no_per_workbook_detail(tmp_path: Path) -> None:
    labels = write_set(tmp_path / "eval", [_row("c", SHA_C, "ledger", "test")], {"c": label("c", SHA_C)})
    analyses = tmp_path / "analyses"
    write_analysis(analyses, "c", analysis(SHA_C), PARITY)
    report = run_evaluation(labels, labels.parent / "manifest.csv", "test", analyses)
    assert "perWorkbook" not in report
    assert report["split"] == "test"


def test_split_is_enforced(evaluation_set: tuple[Path, Path], tmp_path: Path) -> None:
    labels, analyses = evaluation_set
    # Dev works although test's label is broken, because dev doesn't read it...
    args = ["eval", "--labels", str(labels), "--analyses", str(analyses), "-o", str(tmp_path / "o")]
    assert main([*args, "--split", "dev"]) == 0
    # ...and the test split does read it, and refuses.
    assert main([*args, "--split", "test"]) == 3


def test_draft_label_is_refused(evaluation_set: tuple[Path, Path], tmp_path: Path) -> None:
    labels, analyses = evaluation_set
    draft = label("a", SHA_A)
    draft["status"] = "draft"
    (labels / "a.json").write_text(json.dumps(draft), encoding="utf-8")
    args = ["eval", "--labels", str(labels), "--split", "dev", "--analyses", str(analyses), "-o", str(tmp_path / "o")]
    assert main(args) == 3
    assert not (tmp_path / "o" / "report.json").exists()


def test_empty_split_is_refused(tmp_path: Path) -> None:
    labels = write_set(tmp_path / "eval", [], {})
    assert main(["eval", "--labels", str(labels), "--split", "dev", "--analyses", str(tmp_path), "-o", str(tmp_path / "o")]) == 3


# --- Freezing -----------------------------------------------------------------------------------


def _freeze_args(labels: Path, tmp_path: Path, split: str = "test") -> list[str]:
    return ["eval", "--labels", str(labels), "--split", split, "--freeze", "-o", str(tmp_path / "o")]


def _write_manifest(labels: Path, rows: list[str]) -> None:
    (labels.parent / "manifest.csv").write_text("\n".join([FIELDS, *rows]) + "\n", encoding="utf-8")


def _can_load(labels: Path) -> None:
    manifest = labels.parent / "manifest.csv"
    check_frozen(read_manifest(manifest), manifest)


def test_frozen_test_split_only_grows(tmp_path: Path) -> None:
    rows = [_row("c", SHA_C, "ledger", "test")]
    labels = write_set(tmp_path / "eval", rows, {})
    assert main(_freeze_args(labels, tmp_path)) == 0

    # Adding is allowed.
    grown = [*rows, _row("d", SHA_A, "ledger", "test")]
    _write_manifest(labels, grown)
    _can_load(labels)

    # Changing a file is not.
    _write_manifest(labels, [_row("c", SHA_B, "ledger", "test")])
    with pytest.raises(EvalError, match="changed"):
        _can_load(labels)
    # Moving one to dev, where it could be tuned on, is not.
    _write_manifest(labels, [_row("c", SHA_C, "ledger", "dev")])
    with pytest.raises(EvalError, match="moved to dev"):
        _can_load(labels)
    # Removing one is not.
    _write_manifest(labels, [_row("d", SHA_A, "ledger", "test")])
    with pytest.raises(EvalError, match="removed"):
        _can_load(labels)
    # And a freeze can't paper over any of that.
    assert main(_freeze_args(labels, tmp_path)) == 3


def test_only_test_can_be_frozen(evaluation_set: tuple[Path, Path], tmp_path: Path) -> None:
    labels, _ = evaluation_set
    assert main(_freeze_args(labels, tmp_path, "dev")) == 3


# --- Pre-labelling ------------------------------------------------------------------------------


def _workbook_with_formula(root: Path, workbook_id: str) -> str:
    folder = root / "workbooks"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{workbook_id}.xlsx"
    builders.build_feature_workbook(path)
    builders.as_saved_by_excel(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_prelabel_writes_a_draft_a_person_must_review(tmp_path: Path) -> None:
    root = tmp_path / "eval"
    sha256 = _workbook_with_formula(root, "wb1")
    labels = write_set(root, [_row("wb1", sha256)], {})
    analyses = tmp_path / "analyses"
    write_analysis(
        analyses,
        "wb1",
        {
            "snapshotSha256": sha256,
            "engine": {"rulesVersion": "1"},
            "sheets": [{"name": "Données", "outcome": "ledger"}],
            "findings": [
                finding("table", "Données", ["A2:C4"]),
                finding("header", "Données", ["A2:C2"]),
                finding("fieldType", "Données", ["B3:B4"], {"type": "money"}),
            ],
        },
    )
    drafts = tmp_path / "drafts"
    args = ["eval", "--labels", str(labels), "--split", "dev", "--prelabel", "--analyses", str(analyses), "-o", str(drafts)]
    assert main(args) == 0
    draft = json.loads((drafts / "wb1.json").read_text(encoding="utf-8"))
    assert draft["status"] == "draft"
    assert draft["resultsFrom"] == "excel"
    first = draft["sheets"][0]
    assert first["kind"] == "ledger"
    assert first["tables"] == [
        {
            "range": "A2:C4",
            "headerRows": [2],
            "fields": [{"column": "B", "name": "Montant", "type": "money"}],
        }
    ]
    # The oracle comes from the file itself.
    assert {"sheet": "Données", "ref": "C3", "f": "=B3*2", "result": 3001, "t": "n"} in draft["formulas"]
    # Its shape is valid, and scoring still refuses it because it's a draft.
    problems = check_label(draft, read_manifest(labels.parent / "manifest.csv")[0])
    assert problems == ["wb1: still a draft; a person must correct it and mark it reviewed"]


def test_prelabel_never_overwrites(tmp_path: Path) -> None:
    root = tmp_path / "eval"
    sha256 = _workbook_with_formula(root, "wb1")
    human = label("wb1", sha256)
    labels = write_set(root, [_row("wb1", sha256)], {"wb1": human})
    drafts = tmp_path / "drafts"
    assert main(["eval", "--labels", str(labels), "--split", "dev", "--prelabel", "-o", str(drafts)]) == 0
    assert not (drafts / "wb1.json").exists()
    assert json.loads((labels / "wb1.json").read_text(encoding="utf-8")) == human


def test_prelabel_refuses_a_changed_workbook(tmp_path: Path) -> None:
    root = tmp_path / "eval"
    _workbook_with_formula(root, "wb1")
    labels = write_set(root, [_row("wb1", SHA_A)], {})
    drafts = tmp_path / "drafts"
    assert main(["eval", "--labels", str(labels), "--split", "dev", "--prelabel", "-o", str(drafts)]) == 3


def test_repo_manifest_has_the_contract_columns() -> None:
    manifest = Path(__file__).resolve().parents[3] / "eval" / "manifest.csv"
    with manifest.open(encoding="utf-8") as stream:
        assert next(csv.reader(stream)) == FIELDS.split(",")
