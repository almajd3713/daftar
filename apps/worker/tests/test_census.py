from collections import Counter
import json
from pathlib import Path
import shutil
from typing import Any

import pytest
import workbook_builders as builders
import xlsxwriter

from daftar_worker.census import analyse_formula, function_coverage, run_census
from daftar_worker.cli import main


def _formulas_workbook(path: Path) -> Path:
    """Hand-countable: 7 formulas, of which 1 passing, 1 cross-sheet, 1 lookup, 1 volatile."""
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("Calc")
    sheet.write_number("A1", 1)
    sheet.write_formula("B1", "=SUM(A1:A1)", None, 1)
    sheet.write_formula("B2", "=SUM(A1,A1)+IF(A1>0,1,2)", None, 3)
    sheet.write_formula("B3", "=A1", None, 1)
    sheet.write_formula("B4", "=Autre!A1+1", None, 2)
    sheet.write_formula("B5", "=VLOOKUP(A1,Autre!A:B,2,FALSE)", None, 0)
    sheet.write_formula("B6", "=TODAY()", None, 46000)
    sheet.write_formula("B7", '="SUM(1)"', None, "SUM(1)")  # Text in a string isn't a call.
    other = book.add_worksheet("Autre")
    other.write_number("A1", 1)
    book.close()
    return path


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    (root / "sub").mkdir(parents=True)
    builders.build_feature_workbook(root / "features.xlsx")
    _formulas_workbook(root / "sub" / "formulas.xlsx")
    shutil.copy(root / "sub" / "formulas.xlsx", root / "sub" / "zz-copy.xlsx")
    (root / "plain.csv").write_text("a;b\n1;2\n", encoding="utf-8")
    (root / "broken.xlsx").write_bytes(b"not a workbook")
    (root / "~$lock.xlsx").write_bytes(b"lock file")
    (root / "notes.txt").write_text("ignored", encoding="utf-8")
    return root


def _record(census: dict[str, Any], name: str) -> dict[str, Any]:
    return next(item for item in census["workbooks"] if item["file"].endswith(name))


def test_feature_workbook_matches_hand_counts(corpus: Path) -> None:
    counts = _record(run_census([corpus]), "features.xlsx")["counts"]
    expected = {
        "hiddenSheets": 2,  # Masqué, TrèsMasqué.
        "protectedSheets": 1,  # عربي.
        "merges": 1,
        "validations": 1,
        "conditionalFormats": 3,
        "tables": 1,
        "definedNames": 2,
        "comments": 1,
        "formulas": 4,  # C3, C4, F3, F4.
        "errorValues": 1,
        "macros": 0,
        "charts": 2,  # One embedded, one chart sheet.
        "images": 1,
        "shapes": 1,
        "multipleSheets": 1,
    }
    for name, value in expected.items():
        assert counts[name] == value, name


def test_formula_workbook_matches_hand_counts(corpus: Path) -> None:
    record = _record(run_census([corpus]), "formulas.xlsx")
    counts = record["counts"]
    assert counts["formulas"] == 7
    assert counts["passingFormulas"] == 1
    assert counts["crossSheetFormulas"] == 2  # B4, B5.
    assert counts["lookupFunctions"] == 1
    assert counts["volatileFunctions"] == 1
    assert record["functions"] == {"IF": 1, "SUM": 2, "TODAY": 1, "VLOOKUP": 1}
    assert record["sheets"] == 2
    assert record["maxRowsPerSheet"] == 7


def test_aggregate_matches_hand_counts(corpus: Path) -> None:
    census = run_census([corpus])
    data = census["aggregate"]
    assert data["workbooks"] == 3  # features, formulas, plain.csv.
    assert data["duplicatesSkipped"] == 1
    assert data["unreadable"] == {"unreadable": 1}
    assert census["failures"][0]["file"].endswith("broken.xlsx")
    assert data["formats"] == {"csv": 1, "xlsx": 2}
    assert data["applications"] == {"Microsoft Excel": 2, "unknown": 1}
    assert data["workbooksWithFormulas"] == 2
    assert data["features"]["formulas"] == {"workbooks": 2, "percent": 66.7}
    assert data["features"]["merges"] == {"workbooks": 1, "percent": 33.3}
    assert data["formulaFeatures"]["lookupFunctions"] == {"workbooks": 1, "percent": 50.0}
    # SUM 2, IF 1, TODAY 1, VLOOKUP 1, CONCAT 1 from the feature workbook.
    assert data["functionCalls"] == 6
    assert data["distinctFunctions"] == 5
    assert data["topFunctions"][0] == {"name": "SUM", "calls": 2, "percent": 33.3, "workbooks": 1}
    assert data["sheetsPerWorkbook"]["max"] == 6


def test_function_coverage_by_hand() -> None:
    # 10 calls: A 5, B 3, C 1, D 1. 80% needs A and B; 90% needs three; 95% and 99% need all four.
    coverage = function_coverage(Counter({"A": 5, "B": 3, "C": 1, "D": 1}))
    assert coverage == {"80%": 2, "90%": 3, "95%": 4, "99%": 4}
    assert function_coverage(Counter()) == {}


def test_coverage_is_exact_on_the_mark() -> None:
    assert function_coverage(Counter({"A": 4, "B": 1}))["80%"] == 1


@pytest.mark.parametrize(
    ("formula", "functions", "cross", "passing"),
    [
        ("=SUM(A1:A3)", ["SUM"], False, False),
        ("=Sheet2!A1", [], True, True),
        ("='Mes données'!A1+1", [], True, False),
        ("=A1", [], False, True),
        ('="IF(1)"', [], False, False),
        ("=if(a1>0,sum(b1),0)", ["IF", "SUM"], False, False),
        ("{=SUM(A1:A2*B1:B2)}", ["SUM"], False, False),
    ],
)
def test_analyse_formula(formula: str, functions: list[str], cross: bool, passing: bool) -> None:
    facts = analyse_formula(formula)
    assert facts["functions"] == functions
    assert facts["crossSheet"] is cross
    assert facts["passing"] is passing


def test_cli_writes_both_outputs_and_no_cell_values(corpus: Path, tmp_path: Path) -> None:
    output = tmp_path / "report" / "census.json"
    assert main(["census", str(corpus), "-o", str(output)]) == 0
    text = output.read_text(encoding="utf-8")
    assert json.loads(text)["aggregate"]["workbooks"] == 3
    markdown = output.with_suffix(".md").read_text(encoding="utf-8")
    assert "| merges | 1 | 33.3 |" in markdown
    assert "| 80% |" in markdown
    # Personal data must not reach a report that gets shared.
    for value in ("أمينة", "Karim", "Sara", "À vérifier"):
        assert value not in text and value not in markdown


def test_cli_missing_path(tmp_path: Path) -> None:
    output = tmp_path / "census.json"
    assert main(["census", str(tmp_path / "nowhere"), "-o", str(output)]) == 2
    assert not output.exists()


def test_empty_folder(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    data = run_census([empty])["aggregate"]
    assert data["workbooks"] == 0
    assert data["features"]["formulas"] == {"workbooks": 0, "percent": 0.0}
