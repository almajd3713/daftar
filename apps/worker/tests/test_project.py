import json
import os
from pathlib import Path
import shutil
from typing import Any

import pytest
import workbook_builders as builders
import xlsxwriter

from daftar_spec import validate_spec
from daftar_worker.analyser import analyze_snapshot
from daftar_worker.analyser.grid import Cell
from daftar_worker.cli import main
from daftar_worker.project.decisions import accept_high_confidence, decide, match_key, reapply
from daftar_worker.project.files import project_generate, project_init, project_reanalyze
from daftar_worker.project.generate import Generator, convert_value, parse_number, slug
from daftar_worker.reader import read_file


FIXTURE = Path(__file__).resolve().parents[3] / "packages" / "spec" / "fixtures" / "generated"
DECIDED_AT = "2026-11-04T10:00:00+00:00"


def accept_everything(analysis: dict[str, Any], skip: tuple[str, ...] = ()) -> None:
    for finding in analysis["findings"]:
        if finding["kind"] not in skip and finding["kind"] != "unsupported":
            decide(finding, "accepted", "operator", at=DECIDED_AT)


def generate(path: Path, skip: tuple[str, ...] = ()) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], Any]:
    snapshot = read_file(path)
    analysis = analyze_snapshot(snapshot)
    accept_everything(analysis, skip)
    return Generator(analysis, snapshot).generate()


@pytest.fixture
def tutoring(tmp_path: Path) -> Path:
    return builders.tutoring_workbook(tmp_path / "centre.xlsx")


def entity(spec: dict[str, Any], key: str) -> dict[str, Any]:
    return next(item for item in spec["entities"] if item["key"] == key)


def field(item: dict[str, Any], key: str) -> dict[str, Any]:
    return next(entry for entry in item["fields"] if entry["key"] == key)


# --- Only what a person accepted reaches the spec (R-12) ----------------------------------------


def test_nothing_accepted_means_an_empty_spec(tutoring: Path) -> None:
    snapshot = read_file(tutoring)
    spec, seed, _ = Generator(analyze_snapshot(snapshot), snapshot).generate()
    assert spec["entities"] == [] and spec["calculators"] == [] and seed == {}
    assert validate_spec(spec) == []


def test_a_rejected_finding_doesnt_reach_the_spec(tutoring: Path) -> None:
    snapshot = read_file(tutoring)
    analysis = analyze_snapshot(snapshot)
    accept_everything(analysis)
    for finding in analysis["findings"]:
        if finding["kind"] == "fieldType" and finding["proposal"]["name"] == "Téléphone parent":
            decide(finding, "rejected", "operator")
        if finding["kind"] == "calculator":
            decide(finding, "rejected", "operator")
    spec, _, _ = Generator(analysis, snapshot).generate()
    fields = [item["key"] for item in entity(spec, "eleves")["fields"]]
    assert "telephone_parent" not in fields
    assert spec["calculators"] == []


def test_an_edit_wins_over_the_proposal(tutoring: Path) -> None:
    snapshot = read_file(tutoring)
    analysis = analyze_snapshot(snapshot)
    accept_everything(analysis)
    for finding in analysis["findings"]:
        if finding["kind"] == "fieldType" and finding["proposal"]["name"] == "Élève":
            decide(finding, "edited", "operator", {"type": "longtext", "label": {"fr": "Nom de l'élève", "ar": "اسم التلميذ"}})
    spec, _, _ = Generator(analysis, snapshot).generate()
    edited = next(item for item in entity(spec, "eleves")["fields"] if item["label"]["fr"] == "Nom de l'élève")
    assert edited["type"] == "longtext"
    assert edited["provenance"]["decision"] == "edited"


# --- The tutoring workbook, end to end ----------------------------------------------------------


def test_the_generated_spec_is_valid_and_has_provenance(tutoring: Path) -> None:
    spec, _, _ = generate(tutoring)
    assert validate_spec(spec) == []
    provenance = entity(spec, "eleves")["provenance"]
    assert provenance["sheet"] == "Élèves"
    assert provenance["decision"] == "accepted"
    assert len(provenance["workbookSha256"]) == 64


def test_monthly_tabs_become_one_entity_with_a_period(tutoring: Path) -> None:
    spec, seed, _ = generate(tutoring)
    payments = next(item for item in spec["entities"] if "period" in item)
    assert payments["kind"] == "ledger"
    assert payments["key"] == "paiements"  # From the title above the table, minus the month.
    assert payments["period"]["granularity"] == "month"
    mapping = next(item for item in spec["mapping"] if item["entity"] == payments["key"])
    assert [(item["sheet"], item["period"]) for item in mapping["sources"]] == [
        ("Janvier 2026", "2026-01"),
        ("Février 2026", "2026-02"),
        ("Mars 2026", "2026-03"),
    ]
    rows = seed[payments["key"]]
    assert len(rows) == 36  # 12 a month: the three total rows are gone.
    assert {row["period"] for row in rows} == {"2026-01-01", "2026-02-01", "2026-03-01"}
    assert mapping["totals"]


def test_a_copied_formula_becomes_a_computed_field_in_real_keys(tutoring: Path) -> None:
    spec, seed, _ = generate(tutoring)
    payments = next(item for item in spec["entities"] if "period" in item)
    rest = field(payments, "reste")
    assert rest["type"] == "computed"
    assert rest["computed"]["eval"] == "translated"
    assert rest["computed"]["deps"] == ["du", "paye"]
    assert "col_" not in json.dumps(rest["computed"]["expr"])
    assert all("reste" not in row for row in seed[payments["key"]])  # The runtime computes it.


def test_coloured_status_becomes_choices_with_colours(tutoring: Path) -> None:
    spec, seed, _ = generate(tutoring)
    payments = next(item for item in spec["entities"] if "period" in item)
    status = field(payments, "statut")
    assert {(item["source"], item.get("colour")) for item in status["choices"]} == {("Payé", "#00FF00"), ("Impayé", "#FF0000")}
    assert {row["statut"] for row in seed[payments["key"]]} == {item["key"] for item in status["choices"]}


def test_retyped_names_become_one_list_and_a_link(tutoring: Path) -> None:
    spec, seed, _ = generate(tutoring)
    parents = entity(spec, "parent")
    assert parents["kind"] == "reference"
    names = sorted(row["nom"] for row in seed["parent"])
    assert len(names) == 4, names  # Eight spellings, four people.
    link = field(entity(spec, "eleves"), "parent")
    assert (link["type"], link["target"]) == ("link", "parent")
    assert seed["eleves"][0]["parent"]["$ref"]["field"] == "nom"
    assert {row["parent"]["$ref"]["value"] for row in seed["eleves"]} == set(names)


def test_a_relation_makes_a_link_with_a_seed_reference(tutoring: Path) -> None:
    spec, seed, _ = generate(tutoring)
    payments = next(item for item in spec["entities"] if "period" in item)
    link = field(payments, "matricule")
    assert (link["type"], link["target"]) == ("link", "eleves")
    assert seed[payments["key"]][0]["matricule"] == {"$ref": {"field": "matricule", "value": "E000"}}


def test_a_formula_model_becomes_a_calculator(tutoring: Path) -> None:
    spec, _, _ = generate(tutoring)
    calculator = spec["calculators"][0]
    assert [item["cell"] for item in calculator["inputs"]] == ["B1", "B2", "B3"]
    assert [item["cell"] for item in calculator["outputs"]] == ["B6"]
    assert calculator["testCases"][0]["outputs"] == {"output_b6": 5700}


def test_personal_and_sensitive_fields_are_marked(tmp_path: Path) -> None:
    path = tmp_path / "p.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("Atelier")
    sheet.write_row("A1", ["Client", "Téléphone", "Prix", "Coût", "Marge"], book.add_format({"bold": True}))
    for row in range(2, 8):
        sheet.write_row(f"A{row}", [f"Nom {row}", "0550123456", row * 10.5, row * 2.5, row * 8.0])
    book.close()
    spec, _, report = generate(path)
    item = spec["entities"][0]
    assert item["personalData"] is True and item["retention"]["months"] == 36
    assert field(item, "client").get("personalData") is True
    assert field(item, "cout")["level"] == 1 and field(item, "marge")["level"] == 1
    assert "level" not in field(item, "prix")
    assert {"kind": "confirmRetention", "entity": item["key"], "months": 36} in report.questions


def test_a_tracker_gets_a_workflow_and_a_board(tmp_path: Path) -> None:
    path = tmp_path / "t.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("Réparations")
    sheet.write_row("A1", ["Appareil", "Technicien", "État"], book.add_format({"bold": True}))
    for row in range(2, 14):
        sheet.write_row(f"A{row}", [f"Tél {row}", ["Ali", "Omar"][row % 2], ["Reçu", "En cours", "Prêt"][row % 3]])
    sheet.data_validation("C2:C13", {"validate": "list", "source": ["Reçu", "En cours", "Prêt"]})
    book.close()
    spec, _, _ = generate(path)
    workflow = spec["workflows"][0]
    assert workflow["initialState"] == "recu"
    assert [(item["from"], item["to"]) for item in workflow["transitions"]] == [
        (["recu"], "en_cours"), (["en_cours"], "recu"), (["en_cours"], "pret"), (["pret"], "en_cours"),
    ]  # fmt: skip
    assert any(view["type"] == "board" for view in spec["views"])


def test_mapping_keeps_real_column_letters_when_one_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "g.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("S")
    sheet.write_row("A1", ["Réf", "Note", "Montant"], book.add_format({"bold": True}))
    for row in range(2, 8):
        sheet.write_row(f"A{row}", [f"R{row}", f"n{row}", row * 1.5])
    book.close()
    snapshot = read_file(path)
    analysis = analyze_snapshot(snapshot)
    accept_everything(analysis)
    for finding in analysis["findings"]:
        if finding["kind"] == "fieldType" and finding["proposal"]["column"] == "B":
            decide(finding, "rejected", "operator")
    spec, _, _ = Generator(analysis, snapshot).generate()
    assert [(item["column"], item["field"]) for item in spec["mapping"][0]["columns"]] == [("A", "ref"), ("C", "montant")]


# --- R-19: a wrong formula never becomes a computed field ---------------------------------------


def test_a_formula_the_engine_gets_wrong_stays_as_excels_values(tmp_path: Path) -> None:
    path = tmp_path / "w.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("S")
    sheet.write_row("A1", ["Réf", "Valeur", "Calcul"], book.add_format({"bold": True}))
    for row in range(2, 8):
        sheet.write_string(f"A{row}", f"R{row}")
        sheet.write_number(f"B{row}", row)
        # The stored results are 99, so a real recalculation disagrees with them.
        sheet.write_formula(f"C{row}", f'=SUMIF(B$2:B$7,">0")+B{row}', None, 99)
    book.close()
    builders.as_saved_by_excel(path)
    folder = tmp_path / "project"
    project_init(path, folder)
    analysis_path = folder / "analysis.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    accept_everything(analysis)
    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    result = project_generate(folder)
    assert result["parityFailures"] == 1
    spec = json.loads((folder / "daftar.spec.json").read_text(encoding="utf-8"))
    assert field(spec["entities"][0], "calcul")["type"] != "computed"
    rows = (folder / "seed" / f"{spec['entities'][0]['key']}.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(rows[0])["calcul"] == 99  # Excel's own result, kept as data.
    report = json.loads((folder / "generation-report.json").read_text(encoding="utf-8"))
    assert report["parityFailures"][0]["count"] == 6


def test_a_function_the_engine_lacks_stays_as_values(tmp_path: Path) -> None:
    path = tmp_path / "m.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("S")
    sheet.write_row("A1", ["Réf", "Calcul"], book.add_format({"bold": True}))
    for row in range(2, 8):
        sheet.write_string(f"A{row}", f"R{row}")
        sheet.write_formula(f"B{row}", f"=MACROFONCTION(A{row})", None, row * 2)
    book.close()
    spec, _, report = generate(path)
    assert field(spec["entities"][0], "calcul")["type"] != "computed"
    assert report.parity_failures[0]["missingFunctions"] == ["MACROFONCTION"]


# --- Values -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "number"),
    [("1 234,50 DA", 1234.5), ("1.234.567,89 د.ج", 1234567.89), ("1,234.50", 1234.5), ("12,5", 12.5), ("٣٠٠", 300.0), ("abc", None), ("", None)],
)
def test_parse_number(text: str, number: float | None) -> None:
    assert parse_number(text) == number


def _cell(value: Any, kind: str = "s") -> Cell:
    return Cell(2, 1, value, kind, None, None, {})


@pytest.mark.parametrize(
    ("entry", "cell", "expected"),
    [
        ({"type": "money"}, _cell("1 200,50 DA"), 1200.5),
        ({"type": "money"}, _cell(1500, "n"), 1500),
        ({"type": "money"}, _cell("gratuit"), None),
        ({"type": "integer"}, _cell(2.5, "n"), None),
        ({"type": "percent"}, _cell("12%"), 0.12),
        ({"type": "date"}, _cell("15/01/2026"), "2026-01-15"),
        ({"type": "date"}, _cell("2026-01-15T00:00:00", "d"), "2026-01-15"),
        ({"type": "date"}, _cell(46037, "n"), "2026-01-15"),
        ({"type": "date"}, _cell("31/02/2026"), None),
        ({"type": "boolean"}, _cell("Oui"), True),
        ({"type": "boolean"}, _cell("لا"), False),
        ({"type": "boolean"}, _cell(True, "b"), True),
        ({"type": "phone"}, _cell("0550 12 34 56"), "0550123456"),
        ({"type": "phone"}, _cell(550123456, "n"), "0550123456"),
        ({"type": "choice", "choices": [{"key": "paye", "source": "Payé"}]}, _cell("PAYÉ"), "paye"),
        ({"type": "choice", "choices": [{"key": "paye", "source": "Payé"}]}, _cell("Autre"), None),
        ({"type": "text"}, _cell(12, "n"), "12"),
    ],
)
def test_convert_value(entry: dict[str, Any], cell: Cell, expected: Any) -> None:
    assert convert_value(entry, cell) == expected


def test_a_value_that_doesnt_fit_is_reported_not_lost_silently(tmp_path: Path) -> None:
    path = tmp_path / "b.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("S")
    sheet.write_row("A1", ["Réf", "Montant"], book.add_format({"bold": True}))
    for row in range(2, 22):
        sheet.write_string(f"A{row}", f"R{row}")
        sheet.write_number(f"B{row}", row * 1.5)
    sheet.write_string("B21", "voir facture")
    book.close()
    _, _, report = generate(path)
    assert report.bad_values == [{"sheet": "S", "cell": "B21", "field": "montant", "type": "money"}]


@pytest.mark.parametrize(
    ("text", "key"),
    [("Élèves", "eleves"), ("N° de reçu", "n_de_recu"), ("2026 ventes", "x_2026_ventes"), ("الزبائن", "x"), ('x"; DROP TABLE y', "x_drop_table_y"), ("a" * 80, "a" * 63)],
)
def test_keys_are_always_safe(text: str, key: str) -> None:
    assert slug(text, "x") == key


# --- R-15: decisions survive a rerun ------------------------------------------------------------


def _small(path: Path, rows: int = 6, status_header: str = "Montant") -> Path:
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("S")
    sheet.write_row("A1", ["Réf", status_header], book.add_format({"bold": True}))
    for row in range(2, rows + 2):
        sheet.write_row(f"A{row}", [f"R{row}", row * 1.5])
    book.close()
    return path


def test_a_rerun_on_the_same_workbook_keeps_every_decision(tutoring: Path) -> None:
    snapshot = read_file(tutoring)
    first = analyze_snapshot(snapshot)
    accept_everything(first)
    second = analyze_snapshot(snapshot)
    result = reapply(first, second)
    assert result["conflicts"] == [] and result["moved"] == 0
    assert result["applied"] == sum(item["decision"]["status"] != "pending" for item in first["findings"])
    assert [item["decision"] for item in first["findings"]] == [item["decision"] for item in second["findings"]]


def test_more_rows_change_the_ids_but_decisions_follow(tmp_path: Path) -> None:
    first = analyze_snapshot(read_file(_small(tmp_path / "a.xlsx", 6)))
    accept_everything(first)
    second = analyze_snapshot(read_file(_small(tmp_path / "b.xlsx", 9)))
    assert {item["id"] for item in first["findings"]} != {item["id"] for item in second["findings"]}
    result = reapply(first, second)
    assert result["moved"] > 0 and result["conflicts"] == []
    assert all(item["decision"]["status"] == "accepted" for item in second["findings"])


def test_a_decision_on_something_gone_is_a_conflict(tmp_path: Path) -> None:
    path = tmp_path / "a.xlsx"
    book = xlsxwriter.Workbook(str(path))
    for name in ("S", "T"):
        sheet = book.add_worksheet(name)
        sheet.write_row("A1", ["Réf", "Montant"], book.add_format({"bold": True}))
        for row in range(2, 8):
            sheet.write_row(f"A{row}", [f"R{row}", row * 1.5])
    book.close()
    first = analyze_snapshot(read_file(path))
    accept_everything(first)
    second = analyze_snapshot(read_file(_small(tmp_path / "b.xlsx")))
    result = reapply(first, second)
    assert {item["reason"] for item in result["conflicts"]} == {"gone"}
    # Everything on T, plus what spanned both sheets: that proposal doesn't exist any more either.
    others = [item["finding"]["kind"] for item in result["conflicts"] if item["finding"]["sheet"] != "T"]
    assert set(others) <= {"entityMerge", "periodUnion"}
    assert any(item["finding"]["sheet"] == "T" for item in result["conflicts"])


def test_a_finding_that_now_proposes_something_else_is_a_conflict(tmp_path: Path) -> None:
    first = analyze_snapshot(read_file(_small(tmp_path / "a.xlsx")))
    accept_everything(first)
    path = tmp_path / "b.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("S")
    sheet.write_row("A1", ["Réf", "Montant"], book.add_format({"bold": True}))
    for row in range(2, 8):
        sheet.write_row(f"A{row}", [f"R{row}", f"{row:02d}/01/2026"])  # Now dates.
    book.close()
    second = analyze_snapshot(read_file(path))
    result = reapply(first, second)
    changed = [item for item in result["conflicts"] if item["reason"] == "changed"]
    assert [item["finding"]["proposal"]["column"] for item in changed] == ["B"]
    amount = next(item for item in second["findings"] if item["kind"] == "fieldType" and item["proposal"]["column"] == "B")
    assert amount["decision"]["status"] == "pending"  # Never applied to something else.


def test_match_keys_tell_columns_apart() -> None:
    a = {"kind": "fieldType", "sheet": "S", "evidence": ["A2:A9"], "proposal": {"column": "A"}}
    b = {"kind": "fieldType", "sheet": "S", "evidence": ["B2:B9"], "proposal": {"column": "B"}}
    c = {"kind": "fieldType", "sheet": "S", "evidence": ["A2:A99"], "proposal": {"column": "A"}}
    assert match_key(a) != match_key(b)
    assert match_key(a) == match_key(c)


def test_accept_high_only_touches_pending_high_findings(tutoring: Path) -> None:
    analysis = analyze_snapshot(read_file(tutoring))
    high = [item for item in analysis["findings"] if item["confidence"]["level"] == "high"]
    decide(high[0], "rejected", "operator")
    count = accept_high_confidence(analysis, "operator")
    assert count == len(high) - 1
    assert high[0]["decision"]["status"] == "rejected"
    assert all(item["decision"]["status"] == "pending" for item in analysis["findings"] if item["confidence"]["level"] != "high")


def test_cli_project_flow(tmp_path: Path, tutoring: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "p"
    assert main(["project", "init", str(folder), "--file", str(tutoring), "--no-llm"]) == 0
    assert (folder / "source.xlsx").exists() and (folder / "snapshot.json").exists()
    assert main(["project", "decide", str(folder), "--accept-high"]) == 0
    assert main(["project", "decide", str(folder), "--accept", "nope"]) == 3
    assert main(["project", "generate", str(folder)]) == 0
    assert validate_spec(json.loads((folder / "daftar.spec.json").read_text(encoding="utf-8"))) == []
    assert main(["project", "reanalyze", str(folder), "--no-llm"]) == 0
    assert '"conflicts": 0' in capsys.readouterr().out
    assert main(["project", "generate", str(tmp_path / "missing")]) == 3


def test_reanalyze_with_an_updated_workbook_reports_conflicts(tmp_path: Path) -> None:
    folder = tmp_path / "p"
    project_init(_small(tmp_path / "a.xlsx"), folder)
    analysis = json.loads((folder / "analysis.json").read_text(encoding="utf-8"))
    accept_everything(analysis)
    (folder / "analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
    path = tmp_path / "b.xlsx"
    book = xlsxwriter.Workbook(str(path))
    book.add_worksheet("Autre").write_row("A1", ["x", "y"])
    book.close()
    result = project_reanalyze(folder, path)
    assert result["conflicts"] > 0
    assert json.loads((folder / "conflicts.json").read_text(encoding="utf-8"))


# --- The fixture the runtime boots --------------------------------------------------------------


def build_fixture(root: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    path = builders.tutoring_workbook(root / "centre.xlsx")
    snapshot = read_file(path)
    # Patching the zip stamps the current time in it, so the real hash differs on every run.
    snapshot["source"]["sha256"] = "0" * 64
    analysis = analyze_snapshot(snapshot)
    accept_everything(analysis)
    spec, seed, _ = Generator(analysis, snapshot).generate()
    return spec, seed


def test_generated_fixture_is_current(tmp_path: Path) -> None:
    """packages/spec/fixtures/generated is what the runtime's tests boot. DAFTAR_WRITE_CASES=1 updates it."""
    spec, seed = build_fixture(tmp_path)
    text = json.dumps(spec, ensure_ascii=False, indent=1) + "\n"
    if os.environ.get("DAFTAR_WRITE_CASES"):
        shutil.rmtree(FIXTURE, ignore_errors=True)
        (FIXTURE / "seed").mkdir(parents=True)
        (FIXTURE / "daftar.spec.json").write_text(text, encoding="utf-8")
        for key, rows in seed.items():
            (FIXTURE / "seed" / f"{key}.jsonl").write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
            )
    assert (FIXTURE / "daftar.spec.json").read_text(encoding="utf-8") == text
    for key, rows in seed.items():
        expected = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        assert (FIXTURE / "seed" / f"{key}.jsonl").read_text(encoding="utf-8") == expected
