import hashlib
import json
from pathlib import Path
import time
from typing import Any

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest
from structure_corpus import CASES, Case
import xlsxwriter
from xlsxwriter.utility import xl_cell_to_rowcol

from daftar_worker import analyser
from daftar_worker.analyser import analyze_snapshot, confidence_level, finding_id
from daftar_worker.analyser.grid import Cell
from daftar_worker.analyser.types import infer_type, is_phone
from daftar_worker.app import app
from daftar_worker.cli import main
from daftar_worker.evaluation.metrics import compute_metrics, score_workbook
from daftar_worker.evaluation.predictions import from_analysis
from daftar_worker.evaluation.run import run_evaluation
from daftar_worker.reader import read_file


SCHEMA = json.loads((Path(analyser.__file__).with_name("analysis.schema.json")).read_text(encoding="utf-8"))


def analyse(case: Case, folder: Path) -> dict[str, Any]:
    path = folder / f"{case.id}.xlsx"
    case.build(path)
    return analyze_snapshot(read_file(path))


def by_kind(analysis: dict[str, Any], kind: str, sheet: str | None = None) -> list[dict[str, Any]]:
    return [
        item
        for item in analysis["findings"]
        if item["kind"] == kind and (sheet is None or item["sheet"] == sheet)
    ]


def case_named(name: str) -> Case:
    return next(case for case in CASES if case.id == name)


def field_types(analysis: dict[str, Any]) -> dict[str, str]:
    return {item["proposal"]["column"]: item["proposal"]["type"] for item in by_kind(analysis, "fieldType")}


# --- Every synthetic case gets the structure it was written with --------------------------------


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_case_outcomes(case: Case, tmp_path: Path) -> None:
    analysis = analyse(case, tmp_path)
    outcomes = {sheet["name"]: (sheet["outcome"], sheet.get("reason")) for sheet in analysis["sheets"]}
    expected = {sheet["name"]: (sheet["kind"], sheet.get("reason")) for sheet in case.sheets}
    assert outcomes == expected


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_case_tables_headers_and_totals(case: Case, tmp_path: Path) -> None:
    analysis = analyse(case, tmp_path)
    for sheet in case.sheets:
        found = by_kind(analysis, "table", sheet["name"])
        assert sorted(item["proposal"]["range"] for item in found) == sorted(t["range"] for t in sheet["tables"])
        for table in sheet["tables"]:
            finding = next(item for item in found if item["proposal"]["range"] == table["range"])
            assert finding["proposal"]["headerRows"] == table["headerRows"]
            assert finding["proposal"]["totalRows"] == table.get("totalRows", [])


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_case_field_types(case: Case, tmp_path: Path) -> None:
    analysis = analyse(case, tmp_path)
    for sheet in case.sheets:
        for table in sheet["tables"]:
            found = {
                item["proposal"]["column"]: item["proposal"]
                for item in by_kind(analysis, "fieldType", sheet["name"])
                if item["proposal"]["table"] == table["range"]
            }
            for field in table["fields"]:
                assert found[field["column"]]["type"] == field["type"], field
                assert found[field["column"]]["name"] == field["name"], field


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_every_analysis_meets_c2(case: Case, tmp_path: Path) -> None:
    analysis = analyse(case, tmp_path)
    errors = [error.message for error in Draft202012Validator(SCHEMA).iter_errors(analysis)]
    assert errors == []
    ids = [item["id"] for item in analysis["findings"]]
    assert len(ids) == len(set(ids))
    listed = {finding for sheet in analysis["sheets"] for finding in sheet["findingIds"]}
    assert listed <= set(ids)
    # Every sheet has exactly one outcome (R-3).
    assert len(analysis["sheets"]) == len({sheet["name"] for sheet in analysis["sheets"]})


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_every_finding_explains_itself_in_both_languages(case: Case, tmp_path: Path) -> None:
    for item in analyse(case, tmp_path)["findings"]:
        assert item["explanation"]["fr"].strip()
        assert any("؀" <= letter <= "ۿ" for letter in item["explanation"]["ar"])
        assert item["decision"] == {"status": "pending"}  # Nothing is applied on its own (R-12).
        assert item["confidence"]["source"] == "rules"


def test_synthetic_corpus_baseline_through_the_scorer(tmp_path: Path) -> None:
    """Regression floor over the corpus, through the real scorer. It is not an accuracy claim."""
    scores = []
    for case in CASES:
        label = {"resultsFrom": "none", "sheets": case.sheets, "relations": case.relations, "formulas": []}
        scores.append(score_workbook(case.id, case.stratum, label, from_analysis(analyse(case, tmp_path))))
    metrics = compute_metrics(scores)
    assert metrics["tables.exact.precision"] == 1.0
    assert metrics["tables.exact.recall"] == 1.0
    assert metrics["headers.f1"] == 1.0
    assert metrics["type.macroAccuracy"] == 1.0
    assert metrics["kind.accuracy"] == 1.0


# --- Individual rules ---------------------------------------------------------------------------


def test_title_and_notes_are_not_data(tmp_path: Path) -> None:
    proposal = by_kind(analyse(case_named("register-title"), tmp_path), "table")[0]["proposal"]
    assert proposal["dataRange"] == "A5:F16"


def test_title_on_the_row_above_with_no_gap(tmp_path: Path) -> None:
    path = tmp_path / "t.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("T")
    sheet.write("A1", "Liste des clients")
    sheet.write_row("A2", ["Nom", "Âge"])
    sheet.write_row("A3", ["Sara", 20])
    sheet.write_row("A4", ["Omar", 30])
    sheet.write("A5", "Note : à vérifier chaque mois")
    book.close()
    proposal = by_kind(analyze_snapshot(read_file(path)), "table")[0]["proposal"]
    assert proposal["range"] == "A2:B4"
    assert proposal["titleRows"] == [1]
    assert proposal["noteRows"] == [5]


def test_multi_row_header_flattens_to_one_label_per_field(tmp_path: Path) -> None:
    header = by_kind(analyse(case_named("merged-headers"), tmp_path), "header")[0]
    assert header["evidence"] == ["A1:E2"]
    assert header["proposal"]["rows"] == [1, 2]
    assert [item["label"] for item in header["proposal"]["labels"]] == [
        "Produit", "Janvier / Quantité", "Janvier / Valeur", "Février / Quantité", "Février / Valeur",
    ]  # fmt: skip


def test_totals_are_proposed_as_aggregates_and_left_out_of_the_data(tmp_path: Path) -> None:
    analysis = analyse(case_named("ledger-totals"), tmp_path)
    total = by_kind(analysis, "totalRow")[0]
    assert total["evidence"] == ["A12:E12"]
    assert total["proposal"]["source"] == "formula"
    assert total["proposal"]["aggregates"] == [
        {"column": "C", "function": "sum"},
        {"column": "D", "function": "sum"},
        {"column": "E", "function": "sum"},
    ]
    assert total["confidence"]["level"] == "high"
    amount = next(item for item in by_kind(analysis, "fieldType") if item["proposal"]["column"] == "C")
    assert amount["evidence"] == ["C2:C11"]  # The total isn't in the field's evidence.


def test_arabic_total_word(tmp_path: Path) -> None:
    total = by_kind(analyse(case_named("arabic"), tmp_path), "totalRow")[0]
    assert total["proposal"]["source"] == "keyword"
    assert total["proposal"]["row"] == 10


def test_pasted_total_is_found_by_arithmetic_at_medium_confidence(tmp_path: Path) -> None:
    total = by_kind(analyse(case_named("values-total"), tmp_path), "totalRow")[0]
    assert total["proposal"]["source"] == "arithmetic"
    assert total["confidence"]["level"] == "medium"


def test_subtotals_inside_a_table(tmp_path: Path) -> None:
    path = tmp_path / "s.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("S")
    sheet.write_row("A1", ["Nom", "Montant"])
    sheet.write_row("A2", ["Sara", 1.5])
    sheet.write_row("A3", ["Omar", 2.5])
    sheet.write("A4", "Sous-total")
    sheet.write_formula("B4", "=SUM(B2:B3)", None, 4)
    sheet.write_row("A5", ["Lina", 3.5])
    sheet.write_row("A6", ["Karim", 4.5])
    sheet.write("A7", "Total général")
    sheet.write_formula("B7", "=SUM(B2:B3,B5:B6)", None, 12)
    book.close()
    table = by_kind(analyze_snapshot(read_file(path)), "table")[0]["proposal"]
    assert table["totalRows"] == [4, 7]
    assert table["range"] == "A1:B7"


def test_running_total_column_is_data_not_a_total_row(tmp_path: Path) -> None:
    path = tmp_path / "r.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("R")
    sheet.write_row("A1", ["Jour", "Montant", "Cumul"])
    for row in range(2, 8):
        sheet.write_string(f"A{row}", f"J{row}")
        sheet.write_number(f"B{row}", row * 1.5)
        sheet.write_formula(f"C{row}", f"=SUM(B$2:B{row})", None, 1)
    book.close()
    assert by_kind(analyze_snapshot(read_file(path)), "table")[0]["proposal"]["totalRows"] == []


def _write(path: Path, rows: dict[str, list[Any]], name: str = "S", header_bold: bool = False) -> Path:
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet(name)
    bold = book.add_format({"bold": True}) if header_bold else None
    for position, (cell, values) in enumerate(rows.items()):
        for offset, value in enumerate(values):
            if value is None:
                continue
            target = xl_cell_to_rowcol(cell)
            if isinstance(value, str) and value.startswith("="):
                sheet.write_formula(target[0], target[1] + offset, value, None, 1)
            else:
                sheet.write(target[0], target[1] + offset, value, bold if position == 0 else None)
    book.close()
    return path


def test_tax_lines_under_a_total_are_not_data(tmp_path: Path) -> None:
    path = _write(tmp_path / "i.xlsx", {
        "A1": ["Désignation", "Qté", "PU", "Montant"],
        "A2": ["Article 1", 2, 100.5, "=B2*C2"],
        "A3": ["Article 2", 1, 50.5, "=B3*C3"],
        "C4": ["Total HT", "=SUM(D2:D3)"],
        "C5": ["TVA 19%", "=D4*0.19"],
        "C6": ["TTC", "=D4+D5"],
    })  # fmt: skip
    analysis = analyze_snapshot(read_file(path))
    table = by_kind(analysis, "table")[0]["proposal"]
    assert table["totalRows"] == [4, 5, 6]
    assert table["dataRange"] == "A2:D3"
    assert field_types(analysis)["C"] == "decimal"  # The labels no longer pollute the column.
    sources = [item["proposal"]["source"] for item in by_kind(analysis, "totalRow")]
    assert sources == ["formula", "afterTotal", "afterTotal"]


def test_a_full_record_after_a_subtotal_is_still_data(tmp_path: Path) -> None:
    path = _write(tmp_path / "s.xlsx", {
        "A1": ["Nom", "Montant"],
        "A2": ["Sara", 1.5],
        "A3": ["Omar", 2.5],
        "A4": ["Sous-total", "=SUM(B2:B3)"],
        "A5": ["Lina", 3.5],
    })  # fmt: skip
    assert by_kind(analyze_snapshot(read_file(path)), "table")[0]["proposal"]["totalRows"] == [4]


@pytest.mark.parametrize("tab", ["Janvier", "février 2026", "جانفي", "Paiements Mars", "مارس"])
def test_a_tab_named_for_a_month_with_amounts_is_a_ledger(tmp_path: Path, tab: str) -> None:
    rows: dict[str, list[Any]] = {"A1": ["N°", "Élève", "Montant"]}
    for row in range(2, 10):
        rows[f"A{row}"] = [row, f"Élève {row}", 1500.5 + row]
    analysis = analyze_snapshot(read_file(_write(tmp_path / "m.xlsx", rows, tab)))
    assert analysis["sheets"][0]["outcome"] == "ledger"


def test_month_word_inside_another_word_isnt_a_month(tmp_path: Path) -> None:
    rows: dict[str, list[Any]] = {"A1": ["N°", "Élève", "Montant"]}
    for row in range(2, 10):
        rows[f"A{row}"] = [row, f"Élève {row}", 1500.5 + row]
    analysis = analyze_snapshot(read_file(_write(tmp_path / "m.xlsx", rows, "Marseille")))
    assert analysis["sheets"][0]["outcome"] == "register"


def test_unstyled_text_over_text_is_a_low_confidence_header(tmp_path: Path) -> None:
    rows: dict[str, list[Any]] = {f"A{row}": [f"Nom {row}", f"Rue {row}"] for row in range(1, 8)}
    header = by_kind(analyze_snapshot(read_file(_write(tmp_path / "t.xlsx", rows))), "header")[0]
    assert header["confidence"]["level"] == "low"


def test_styled_header_over_numbers_is_high_confidence(tmp_path: Path) -> None:
    rows: dict[str, list[Any]] = {"A1": ["Nom", "Solde"]}
    for row in range(2, 8):
        rows[f"A{row}"] = [f"Nom {row}", row * 1.5]
    path = _write(tmp_path / "t.xlsx", rows, header_bold=True)
    assert by_kind(analyze_snapshot(read_file(path)), "header")[0]["confidence"]["level"] == "high"


def test_table_with_no_header_is_low_confidence_with_letter_names(tmp_path: Path) -> None:
    rows: dict[str, list[Any]] = {f"A{row}": [row, row * 2, row * 3] for row in range(1, 8)}
    analysis = analyze_snapshot(read_file(_write(tmp_path / "n.xlsx", rows)))
    table = by_kind(analysis, "table")[0]
    assert table["proposal"]["headerRows"] == []
    assert table["confidence"]["level"] == "low"
    assert by_kind(analysis, "header") == []
    assert {item["proposal"]["name"] for item in by_kind(analysis, "fieldType")} == {"A", "B", "C"}


def test_a_word_starting_like_total_isnt_one(tmp_path: Path) -> None:
    path = tmp_path / "w.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("W")
    sheet.write_row("A1", ["Nom", "Solde"])
    sheet.write_row("A2", ["Totalement neuf", 5])
    sheet.write_row("A3", ["Sommeil", 6])
    sheet.write_row("A4", ["Autre", 7])
    book.close()
    assert by_kind(analyze_snapshot(read_file(path)), "totalRow") == []


def test_a_blank_row_inside_a_table_doesnt_split_it(tmp_path: Path) -> None:
    path = tmp_path / "b.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("B")
    sheet.write_row("A1", ["Nom", "Âge"], book.add_format({"bold": True}))
    for row, values in {2: ["Sara", 20], 3: ["Omar", 30], 5: ["Lina", 40], 6: ["Karim", 50]}.items():
        sheet.write_row(f"A{row}", values)
    book.close()
    assert [item["proposal"]["range"] for item in by_kind(analyze_snapshot(read_file(path)), "table")] == ["A1:B6"]


def test_validation_list_becomes_choices_with_counts(tmp_path: Path) -> None:
    analysis = analyse(case_named("tracker"), tmp_path)
    choices = next(item for item in by_kind(analysis, "choiceList") if item["proposal"]["column"] == "E")
    assert choices["proposal"]["source"] == "validationList"
    assert choices["proposal"]["values"] == [
        {"value": "Reçu", "count": 3}, {"value": "En cours", "count": 3},
        {"value": "Prêt", "count": 3}, {"value": "Livré", "count": 3},
    ]  # fmt: skip
    assert choices["confidence"]["level"] == "high"


def test_low_cardinality_text_is_only_proposed_as_a_choice(tmp_path: Path) -> None:
    analysis = analyse(case_named("tracker"), tmp_path)
    technician = next(item for item in by_kind(analysis, "fieldType") if item["proposal"]["column"] == "C")
    # Two technicians over 12 rows: a choice, at medium confidence, with text as the alternative.
    assert technician["proposal"]["type"] == "choice"
    assert technician["confidence"]["level"] == "medium"
    assert technician["alternatives"] == [{"type": "text"}]
    listed = next(item for item in by_kind(analysis, "choiceList") if item["proposal"]["column"] == "C")
    assert listed["proposal"]["source"] == "values"


def test_validation_list_from_another_sheet_is_a_link(tmp_path: Path) -> None:
    analysis = analyse(case_named("reference"), tmp_path)
    wilaya = next(item for item in by_kind(analysis, "fieldType", "Commandes") if item["proposal"]["column"] == "B")
    assert wilaya["proposal"]["target"] == {"sheet": "Wilayas", "column": "A"}


def test_reference_list_is_found_through_what_points_at_it(tmp_path: Path) -> None:
    analysis = analyse(case_named("reference"), tmp_path)
    kind = by_kind(analysis, "sheetKind", "Wilayas")[0]
    assert kind["proposal"]["outcome"] == "referenceList"


def test_not_converted_sheets_have_reasons_and_no_table_findings(tmp_path: Path) -> None:
    analysis = analyse(case_named("not-converted"), tmp_path)
    assert by_kind(analysis, "table", "Fiche") == []
    assert by_kind(analysis, "sheetKind", "Vide")[0]["proposal"] == {"outcome": "notConverted", "reason": "empty"}


def test_unsupported_parts_become_findings(tmp_path: Path) -> None:
    analysis = analyse(case_named("not-converted"), tmp_path)
    found = by_kind(analysis, "unsupported")
    assert [item["proposal"] for item in found] == [{"kind": "chart", "count": 1}]
    assert found[0]["sheet"] == "Graphique"


def test_hidden_column_is_flagged(tmp_path: Path) -> None:
    path = tmp_path / "h.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("H")
    sheet.write_row("A1", ["Nom", "Coût"])
    sheet.write_row("A2", ["Sara", 1.5])
    sheet.write_row("A3", ["Omar", 2.5])
    sheet.set_column("B:B", None, None, {"hidden": True})
    book.close()
    fields = {item["proposal"]["column"]: item["proposal"] for item in by_kind(analyze_snapshot(read_file(path)), "fieldType")}
    assert fields["B"]["hidden"] is True
    assert "hidden" not in fields["A"]


def test_csv_works_too(tmp_path: Path) -> None:
    path = tmp_path / "c.csv"
    path.write_text("Nom;Téléphone;Inscrit\nأمينة;0550123456;15/01/2026\nKarim;0661234567;16/01/2026\n", encoding="utf-8")
    assert field_types(analyze_snapshot(read_file(path))) == {"A": "text", "B": "phone", "C": "date"}


# --- Types --------------------------------------------------------------------------------------


def _cells(values: list[Any], kind: str = "s", number_format: str | None = None, formula: str | None = None) -> list[Cell]:
    return [Cell(row + 2, 1, value, kind, formula, number_format, {}) for row, value in enumerate(values)]


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        ("0550123456", True), ("0661234567", True), ("0771234567", True),
        ("+213550123456", True), ("00213661234567", True), ("0550 12 34 56", True), ("05-50-12-34-56", True),
        ("0450123456", True), ("021234567", True),  # Landlines.
        ("٠٥٥٠١٢٣٤٥٦", False),  # is_phone sees normalised digits, normal_text does that.
        ("055012345", False), ("05501234567", False), ("1234567890", False), ("abc", False),
    ],
)  # fmt: skip
def test_phone_numbers(number: str, expected: bool) -> None:
    assert is_phone(number) is expected


@pytest.mark.parametrize(
    ("cells", "header", "expected"),
    [
        (_cells(["٠٥٥٠١٢٣٤٥٦", "٠٦٦١٢٣٤٥٦٧"]), "", "phone"),
        (_cells(["a@b.dz", "c@d.com"]), "", "email"),
        (_cells(["15/01/2026", "31/12/2025"]), "", "date"),
        (_cells(["15-01-26", "31.12.25"]), "", "date"),
        (_cells(["45/01/2026", "31/13/2025"]), "", "text"),  # Not real dates.
        (_cells(["15/01/2026 10:30", "16/01/2026 11:00"]), "", "datetime"),
        (_cells(["1 234,50 DA", "2 000,00 DA"]), "", "money"),
        (_cells(["1.234.567,89 د.ج", "500 دج"]), "", "money"),
        (_cells(["12%", "7,5 %"]), "", "percent"),
        (_cells(["oui", "non"]), "", "boolean"),
        (_cells(["نعم", "لا"]), "", "boolean"),
        (_cells(["1,5", "2,75"]), "", "decimal"),
        (_cells(["1 234", "5 678"]), "", "integer"),
        (_cells(["0123", "0456"]), "", "text"),  # Leading zeros mean a code.
        (_cells([46037, 46038], "n"), "Date de paiement", "date"),  # Excel serials.
        (_cells([46037, 46038], "n"), "Quantité", "integer"),
        (_cells([550123456, 661234567], "n"), "Téléphone", "phone"),  # Lost its leading zero.
        (_cells([1500.5, 200], "n"), "Montant", "money"),
        (_cells([1500.5, 200], "n"), "Poids", "decimal"),
        (_cells([1500, 200], "n"), "Stock", "integer"),
        (_cells([1500, 200], "n", '#,##0 "DA"'), "Valeur", "money"),
        (_cells([0.5, 0.2], "n", "0%"), "Taux", "percent"),
        (_cells(["2026-01-15T00:00:00", "2026-01-16T00:00:00"], "d", "dd/mm/yyyy"), "", "date"),
        (_cells(["2026-01-15T10:30:00", "2026-01-16T00:00:00"], "d"), "", "datetime"),
        (_cells([True, False], "b"), "", "boolean"),
        (_cells([3, 4], "n", None, "=A1+1"), "", "computed"),
        (_cells(["x" * 120, "y" * 130]), "", "longtext"),
        (_cells(["Rouge", "Vert", "Rouge", "Vert", "Rouge", "Vert"]), "", "choice"),
        (_cells(["Rouge;Vert", "Vert", "Bleu;Rouge", "Vert", "Bleu", "Rouge"]), "", "multichoice"),
        (_cells(["a", "b", "c", "d", "e", "f"]), "", "text"),
    ],
)
def test_infer_type(cells: list[Cell], header: str, expected: str) -> None:
    guess = infer_type(cells, header)
    assert guess is not None
    assert guess.type == expected


def test_stray_value_lowers_confidence_without_changing_the_type() -> None:
    clean = infer_type(_cells(["0550123456"] * 20), "")
    stray = infer_type(_cells(["0550123456"] * 19 + ["inconnu"]), "")
    assert clean is not None and stray is not None
    assert (clean.type, stray.type) == ("phone", "phone")
    assert stray.score < clean.score
    assert (stray.matched, stray.total) == (19, 20)


def test_too_many_exceptions_falls_back_to_text() -> None:
    guess = infer_type(_cells(["0550123456"] * 5 + ["n/a", "aucun", "?", "—", "x"]), "")
    assert guess is not None and guess.type == "text"


def test_empty_column_has_no_type() -> None:
    assert infer_type([], "Nom") is None


# --- Stability, confidence, explanations --------------------------------------------------------


def test_finding_ids_are_stable_and_depend_on_kind_and_evidence() -> None:
    assert finding_id("table", "S", ["A1:B2"]) == finding_id("table", "S", ["$A$1:$B$2"])
    assert finding_id("table", "S", ["A1:B2"]) != finding_id("header", "S", ["A1:B2"])
    assert finding_id("table", "S", ["A1:B2"]) != finding_id("table", "T", ["A1:B2"])
    assert finding_id("table", "S", ["A1", "B2"]) == finding_id("table", "S", ["B2", "A1"])


def test_same_input_gives_same_analysis_byte_for_byte(tmp_path: Path) -> None:
    path = tmp_path / "same.xlsx"
    case_named("ledger-totals").build(path)
    first = json.dumps(analyze_snapshot(read_file(path)), ensure_ascii=False)
    second = json.dumps(analyze_snapshot(read_file(path)), ensure_ascii=False)
    assert first == second


def test_editing_one_cell_keeps_every_other_finding_id(tmp_path: Path) -> None:
    path = tmp_path / "e.xlsx"
    case_named("register-title").build(path)
    snapshot = read_file(path)
    before = {item["id"] for item in analyze_snapshot(snapshot)["findings"]}
    cell = next(cell for cell in snapshot["sheets"][0]["cells"] if cell["ref"] == "B6")
    cell["v"] = "Un autre nom"
    assert {item["id"] for item in analyze_snapshot(snapshot)["findings"]} == before


@pytest.mark.parametrize(
    ("score", "level"),
    [(0.85, "high"), (0.849, "medium"), (0.6, "medium"), (0.599, "low"), (1.0, "high"), (0.0, "low")],
)
def test_confidence_levels_follow_d18(score: float, level: str) -> None:
    assert confidence_level(score) == level


def test_explanations_quote_the_facts(tmp_path: Path) -> None:
    analysis = analyse(case_named("ledger-totals"), tmp_path)
    table = by_kind(analysis, "table")[0]["explanation"]
    assert "A1:E12" in table["fr"] and "A1:E12" in table["ar"]
    assert "Janvier" in table["fr"] and "Janvier" in table["ar"]
    assert "10 lignes" in table["fr"] and "10 صف" in table["ar"]
    total = by_kind(analysis, "totalRow")[0]["explanation"]
    assert "ligne 12" in total["fr"] and "12" in total["ar"]


# --- Commands -----------------------------------------------------------------------------------


def test_cli_analyze(tmp_path: Path) -> None:
    source = tmp_path / "w.xlsx"
    case_named("tracker").build(source)
    output = tmp_path / "analysis.json"
    assert main(["analyze", str(source), "--no-llm", "-o", str(output)]) == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["engine"] == {"rulesVersion": analyser.RULES_VERSION}
    assert data["snapshotSha256"] == hashlib.sha256(source.read_bytes()).hexdigest()


def test_cli_analyze_unreadable(tmp_path: Path) -> None:
    source = tmp_path / "broken.xlsx"
    source.write_bytes(b"nope")
    output = tmp_path / "analysis.json"
    assert main(["analyze", str(source), "-o", str(output)]) == 2
    assert not output.exists()


def _wait_for(client: TestClient, job_id: str) -> dict[str, Any]:
    for _ in range(200):
        body: dict[str, Any] = client.get(f"/v1/jobs/{job_id}").json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError("the job never finished")


def test_http_analyze_runs_as_a_job(tmp_path: Path) -> None:
    source = tmp_path / "w.xlsx"
    case_named("tracker").build(source)
    client = TestClient(app)
    with source.open("rb") as stream:
        snapshot = client.post("/v1/read", files={"file": ("w.xlsx", stream)}).json()
    sha256 = snapshot["source"]["sha256"]
    response = client.post("/v1/analyze", json={"snapshotSha256": sha256, "llm": "off"})
    assert response.status_code == 202
    job = _wait_for(client, response.json()["jobId"])
    assert job["status"] == "done"
    assert job["progress"] == 1.0
    assert job["result"]["snapshotSha256"] == sha256
    assert job["result"]["sheets"][0]["outcome"] == "tracker"


def test_http_analyze_with_llm_on_and_no_model_still_works(tmp_path: Path) -> None:
    source = tmp_path / "w.csv"
    source.write_text("a;b\n1;2\n", encoding="utf-8")
    client = TestClient(app)
    with source.open("rb") as stream:
        sha256 = client.post("/v1/read", files={"file": ("w.csv", stream)}).json()["source"]["sha256"]
    job = client.post("/v1/analyze", json={"snapshotSha256": sha256, "llm": "on"}).json()
    assert _wait_for(client, job["jobId"])["status"] == "done"


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"snapshotSha256": "a" * 64, "llm": "off"}, 404),  # Never read.
        ({"snapshotSha256": "../../etc/passwd", "llm": "off"}, 422),
        ({"snapshotSha256": "a" * 64, "llm": "maybe"}, 422),
        ({}, 422),
        ([], 422),
    ],
)
def test_http_analyze_errors_use_the_contract_shape(body: Any, status: int) -> None:
    response = TestClient(app).post("/v1/analyze", json=body)
    assert response.status_code == status
    assert set(response.json()) == {"code", "message"}


def test_http_unknown_job() -> None:
    response = TestClient(app).get("/v1/jobs/nothing")
    assert response.status_code == 404
    assert set(response.json()) == {"code", "message"}


def test_eval_runs_the_analyser_when_given_no_analyses(tmp_path: Path) -> None:
    root = tmp_path / "eval"
    (root / "workbooks").mkdir(parents=True)
    (root / "labels").mkdir()
    case = case_named("tracker")
    path = root / "workbooks" / "wb.xlsx"
    case.build(path)
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / "manifest.csv").write_text(
        f"id,source,licence,language,stratum,split,consent,sha256\nwb,synthetic,CC0,fr,tracker,dev,n/a,{sha256}\n",
        encoding="utf-8",
    )
    label = {
        "labelVersion": 1, "id": "wb", "workbookSha256": sha256, "status": "reviewed",
        "resultsFrom": "excel", "sheets": case.sheets, "relations": [],
        "formulas": [{"sheet": "Réparations", "ref": "E2", "f": "=1+1", "result": 2, "t": "n"}],
    }  # fmt: skip
    (root / "labels" / "wb.json").write_text(json.dumps(label), encoding="utf-8")
    report = run_evaluation(root / "labels", root / "manifest.csv", "dev", None)
    assert report["engine"]["rulesVersion"] == [analyser.RULES_VERSION]
    assert report["missingAnalyses"] == []
    assert report["overall"]["metrics"]["kind.accuracy"]["value"] == 1.0
    # No formula engine ran. That's reported, and it doesn't read as 0% parity.
    assert report["parityNotRun"] == ["wb"]
    assert report["overall"]["metrics"]["parity.share"]["value"] is None
