"""R-22 and R-23, on the worker's side: what the file holds, and what a comparison finds."""

import copy
from datetime import datetime
import io
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
import pytest
import workbook_builders as builders

from daftar_spec import validate_spec
from daftar_worker.analyser import analyze_snapshot
from daftar_worker.app import app
from daftar_worker.project.decisions import decide
from daftar_worker.project.generate import Generator
from daftar_worker.reader import read_file
from daftar_worker.roundtrip.diff import diff_workbook
from daftar_worker.roundtrip.export import build_workbook, period_label, shift_rows


JANVIER = "Janvier 2026"
NOTHING: dict[str, list[Any]] = {"added": [], "changed": [], "missing": []}


def accepted(path: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    snapshot = read_file(path)
    analysis = analyze_snapshot(snapshot)
    for finding in analysis["findings"]:
        if finding["kind"] != "unsupported":
            decide(finding, "accepted", "operator", at="2026-11-04T10:00:00+00:00")
    spec, seed, _ = Generator(analysis, snapshot).generate()
    return spec, seed


def current_rows(spec: dict[str, Any], seed: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """The data as the runtime sends it: link labels, and computed values worked out."""
    out: dict[str, list[dict[str, Any]]] = {}
    for key, rows in seed.items():
        out[key] = []
        for place, row in enumerate(rows):
            plain: dict[str, Any] = {"_id": f"{key}-{place}", "_version": 1}
            for name, value in row.items():
                plain[name] = value["$ref"]["value"] if isinstance(value, dict) and "$ref" in value else value
            if key == "paiements":
                plain["reste"] = plain["du"] - plain["paye"]
            out[key].append(plain)
    return out


@pytest.fixture(name="tutoring")
def fixture_tutoring(tmp_path: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    path = tmp_path / "tutoring.xlsx"
    builders.tutoring_workbook(path)
    spec, seed = accepted(path)
    return spec, current_rows(spec, seed)


def written(tmp_path: Path, data: bytes, name: str = "out.xlsx") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def small_spec(fields: list[dict[str, Any]] | None = None, **mapping: Any) -> dict[str, Any]:
    fields = fields or [{"key": "code", "label": {"fr": "Code", "ar": "رمز"}, "type": "text"}, {"key": "n", "label": {"fr": "N", "ar": "ن"}, "type": "integer"}]
    return {
        "app": {"defaultLocale": "fr-DZ"},
        "entities": [{"key": "items", "fields": fields}],
        "mapping": [
            {
                "entity": "items",
                "sources": [{"sheet": "Items", "range": f"A1:{chr(64 + len(fields))}9"}],
                "headerRow": 1,
                "columns": [{"header": field["label"]["fr"], "field": field["key"]} for field in fields],
                "keyColumns": [fields[0]["key"]],
                **mapping,
            }
        ],
    }


@pytest.mark.parametrize(
    ("formula", "delta", "shifted"),
    [
        ("=B4-C4", 2, "=B6-C6"),
        ("=$B4*C$4", 1, "=$B5*C$4"),
        ('="B4"&B4', 1, '="B4"&B5'),
        ("='Feuille B4'!B4+1", 3, "='Feuille B4'!B7+1"),
        ("=LOG10(B4)", 1, "=LOG10(B5)"),
        ("=Tarifs[B4]", 1, "=Tarifs[B4]"),
    ],
)
def test_copying_a_formula_down(formula: str, delta: int, shifted: str) -> None:
    assert shift_rows(formula, delta) == shifted


@pytest.mark.parametrize(
    ("value", "granularity", "label"),
    [("2026-02-17", "month", "2026-02"), ("2026-05-01", "quarter", "2026-Q2"), ("2026-12-31", "quarter", "2026-Q4"), ("2026-02-17", "year", "2026"), (None, "month", None)],
)
def test_the_period_a_date_falls_in(value: str | None, granularity: str, label: str | None) -> None:
    assert period_label(value, granularity) == label


def test_export_follows_the_original_layout(tutoring: Any, tmp_path: Path) -> None:
    spec, rows = tutoring
    path = written(tmp_path, build_workbook(spec, rows))
    book = load_workbook(path)
    assert book.sheetnames == ["Élèves", JANVIER, "Février 2026", "Mars 2026", "Parent"]
    january = book[JANVIER]
    assert [january.cell(3, column).value for column in range(1, 6)] == ["Matricule", "Dû", "Payé", "Reste", "Statut"]
    assert january["A4"].value == "E000"
    assert january["B4"].number_format == '#,##0.00 "DA"'
    assert january["E4"].value == "Payé"
    assert book["Élèves"]["C2"].value == rows["eleves"][0]["parent"]
    assert not january.sheet_view.rightToLeft


def test_computed_columns_keep_their_formulas_with_results_filled_in(tutoring: Any, tmp_path: Path) -> None:
    spec, rows = tutoring
    path = written(tmp_path, build_workbook(spec, rows))
    formulas = load_workbook(path)[JANVIER]
    results = load_workbook(path, data_only=True)[JANVIER]
    january = [row for row in rows["paiements"] if row["period"].startswith("2026-01")]
    assert formulas["D4"].value == "=B4-C4"
    assert formulas["D5"].value == "=B5-C5"
    assert results["D5"].value == january[1]["du"] - january[1]["paye"]
    total = 4 + len(january)
    assert formulas.cell(total, 2).value == f"=SUM(B4:B{total - 1})"
    assert results.cell(total, 2).value == sum(row["du"] for row in january)
    assert results.cell(total, 4).value == sum(row["reste"] for row in january)
    assert results.cell(total, 1).value == "Total"


def test_a_masked_export_holds_values_and_no_total_over_masks(tutoring: Any, tmp_path: Path) -> None:
    spec, rows = tutoring
    for row in rows["paiements"]:
        row["du"] = "*"
    sheet = load_workbook(written(tmp_path, build_workbook(spec, rows, use_formulas=False)))[JANVIER]
    assert sheet["B4"].value == "*"
    assert sheet["D4"].value == rows["paiements"][0]["reste"]
    assert sheet.cell(4 + 12, 2).value is None
    assert sheet.cell(4 + 12, 3).value == "=SUM(C4:C15)"


def test_arabic_exports_are_right_to_left(tutoring: Any, tmp_path: Path) -> None:
    spec, rows = tutoring
    book = load_workbook(written(tmp_path, build_workbook(spec, rows, "ar-DZ")))
    assert all(sheet.sheet_view.rightToLeft for sheet in book)
    assert book[JANVIER].cell(4 + 12, 1).value == "المجموع"


def test_text_that_looks_like_a_formula_stays_text(tmp_path: Path) -> None:
    spec = small_spec()
    path = written(tmp_path, build_workbook(spec, {"items": [{"code": '=HYPERLINK("http://x","y")', "n": 1}, {"code": "@SUM(A1)", "n": 2}]}))
    sheet = load_workbook(path)["Items"]
    assert sheet["A2"].data_type == "s"
    assert sheet["A2"].value == '=HYPERLINK("http://x","y")'
    assert sheet["A3"].data_type == "s"


def test_a_file_nobody_touched_has_no_differences(tutoring: Any, tmp_path: Path) -> None:
    spec, rows = tutoring
    result = diff_workbook(written(tmp_path, build_workbook(spec, rows)), spec, rows)
    assert result == {"entities": dict.fromkeys(result["entities"], NOTHING), "problems": []}


def test_a_comparison_finds_exactly_the_edits(tutoring: Any, tmp_path: Path) -> None:
    spec, rows = tutoring
    path = written(tmp_path, build_workbook(spec, rows))
    book = load_workbook(path)
    book[JANVIER]["C4"] = 1500
    book[JANVIER]["E5"] = "Payé"
    book["Mars 2026"].delete_rows(6)
    book["Élèves"]["A18"] = "E999"
    book["Élèves"]["B18"] = "Nouvel Élève"
    book.save(path)
    result = diff_workbook(path, spec, rows)["entities"]
    assert result["parent"] == NOTHING
    assert [item["key"] for item in result["eleves"]["added"]] == ["E999"]
    assert result["eleves"]["added"][0]["values"] == {"matricule": "E999", "eleve": "Nouvel Élève"}
    assert result["paiements"]["added"] == []
    assert [(item["key"], item["fields"]) for item in result["paiements"]["changed"]] == [
        ("2026-01␟E000", {"paye": [1000, 1500]}),
        ("2026-01␟E001", {"statut": ["impaye", "paye"]}),
    ]
    assert [item["key"] for item in result["paiements"]["missing"]] == ["2026-03␟E002"]


def test_a_moved_column_still_lines_up(tutoring: Any, tmp_path: Path) -> None:
    spec, rows = tutoring
    path = written(tmp_path, build_workbook(spec, rows))
    book = load_workbook(path)
    sheet = book["Élèves"]
    sheet.move_range("A1:D30", cols=2)
    book.save(path)
    assert diff_workbook(path, spec, rows)["entities"]["eleves"] == NOTHING


def test_a_sheet_left_out_says_nothing_about_its_rows(tutoring: Any, tmp_path: Path) -> None:
    spec, rows = tutoring
    path = written(tmp_path, build_workbook(spec, rows))
    book = load_workbook(path)
    del book["Élèves"]
    book.save(path)
    assert diff_workbook(path, spec, rows)["entities"]["eleves"] == NOTHING


def test_a_month_added_in_the_app_gets_a_tab_and_comes_back(tutoring: Any, tmp_path: Path) -> None:
    spec, rows = tutoring
    april = {**rows["paiements"][0], "_id": "new", "period": "2026-04-01"}
    undated = {**rows["paiements"][0], "_id": "undated", "period": None}
    rows["paiements"] += [april, undated]
    path = written(tmp_path, build_workbook(spec, rows))
    book = load_workbook(path)
    assert book.sheetnames[-2:] == ["Parent", "2026-04"] or "2026-04" in book.sheetnames
    assert "Sans période" in book.sheetnames
    assert book["2026-04"]["A4"].value == april["matricule"]
    assert diff_workbook(path, spec, rows)["entities"]["paiements"] == NOTHING


def test_a_date_inside_a_month_stays_in_its_tab_and_isnt_a_change(tutoring: Any, tmp_path: Path) -> None:
    spec, rows = tutoring
    rows["paiements"][0]["period"] = "2026-01-17"
    path = written(tmp_path, build_workbook(spec, rows))
    assert load_workbook(path)[JANVIER]["A4"].value == rows["paiements"][0]["matricule"]
    assert diff_workbook(path, spec, rows)["entities"]["paiements"] == NOTHING


def test_two_tabs_of_one_period_dont_write_a_row_twice(tmp_path: Path) -> None:
    fields = [{"key": "code", "label": {"fr": "Code", "ar": "رمز"}, "type": "text"}]
    spec = small_spec(fields)
    spec["entities"][0]["fields"].insert(0, {"key": "period", "label": {"fr": "P", "ar": "ف"}, "type": "date"})
    spec["entities"][0]["period"] = {"field": "period", "granularity": "year"}
    spec["mapping"][0]["sources"] = [{"sheet": "2011-2012", "period": "2011"}, {"sheet": "2011-2012 bis", "period": "2011"}]
    rows = {"items": [{"_id": "a", "period": "2011-01-01", "code": "X"}]}
    path = written(tmp_path, build_workbook(spec, rows))
    book = load_workbook(path)
    assert book["2011-2012"]["A2"].value == "X"
    assert book["2011-2012 bis"]["A2"].value is None
    assert diff_workbook(path, spec, rows) == {"entities": {"items": NOTHING}, "problems": []}


def test_every_kind_of_field_survives_the_trip(tmp_path: Path) -> None:
    def field(key: str, kind: str, **extra: Any) -> dict[str, Any]:
        return {"key": key, "label": {"fr": key, "ar": key}, "type": kind, **extra}

    choices = [{"key": "a", "label": {"fr": "Alpha", "ar": "ألف"}, "source": "A!"}, {"key": "b", "label": {"fr": "Bêta", "ar": "باء"}}]
    fields = [
        field("code", "text"),
        field("note", "longtext"),
        field("n", "integer"),
        field("d", "decimal"),
        field("m", "money"),
        field("p", "percent"),
        field("day", "date"),
        field("at", "datetime"),
        field("yes", "boolean"),
        field("no", "boolean"),
        field("c1", "choice", choices=choices),
        field("c2", "choice", choices=choices),
        field("mc", "multichoice", choices=choices),
        field("tel", "phone"),
        field("mail", "email"),
        field("empty", "text"),
    ]
    spec = small_spec(fields)
    spec["mapping"][0]["sources"][0]["range"] = "A1:P9"
    row = {
        "_id": "1",
        "code": "0012",
        "note": "ligne\nsuivante",
        "n": 7,
        "d": 1.5,
        "m": 1234.56,
        "p": 0.125,
        "day": "2026-03-09",
        "at": "2026-03-09T09:30:00.000Z",
        "yes": True,
        "no": False,
        "c1": "a",
        "c2": "b",
        "mc": ["b", "a"],
        "tel": "0555123456",
        "mail": "a@b.dz",
        "empty": None,
    }
    path = written(tmp_path, build_workbook(spec, {"items": [row]}, timezone="Africa/Algiers"))
    sheet = load_workbook(path)["Items"]
    assert sheet["D2"].value == 1.5
    assert sheet["F2"].number_format == "0.00%"
    assert sheet["G2"].value == datetime(2026, 3, 9)
    assert sheet["H2"].value == datetime(2026, 3, 9, 10, 30)  # The firm's clock, not UTC.
    assert sheet["K2"].value == "A!"
    assert sheet["L2"].value == "Bêta"
    assert sheet["M2"].value == "Bêta; A!"
    assert diff_workbook(path, spec, {"items": [row]}, timezone="Africa/Algiers") == {"entities": {"items": NOTHING}, "problems": []}


@pytest.mark.parametrize(("zone", "expected"), [("Africa/Algiers", "2026-03-09T11:00:00Z"), ("Asia/Tokyo", "2026-03-09T03:00:00Z"), ("UTC", "2026-03-09T12:00:00Z")])
def test_a_time_edited_in_the_sheet_is_the_firms_clock(tmp_path: Path, zone: str, expected: str) -> None:
    fields = [{"key": "code", "label": {"fr": "Code", "ar": "رمز"}, "type": "text"}, {"key": "at", "label": {"fr": "At", "ar": "و"}, "type": "datetime"}]
    spec = small_spec(fields)
    rows = {"items": [{"_id": "1", "code": "x", "at": "2026-03-09T09:30:00.000Z"}]}
    path = written(tmp_path, build_workbook(spec, rows, timezone=zone))
    assert diff_workbook(path, spec, rows, timezone=zone)["entities"]["items"] == NOTHING
    book = load_workbook(path)
    book["Items"]["B2"] = datetime(2026, 3, 9, 12, 0)
    book.save(path)
    changed = diff_workbook(path, spec, rows, timezone=zone)["entities"]["items"]["changed"][0]
    assert changed["fields"]["at"][1] == expected


def _with_cells(tmp_path: Path, spec: dict[str, Any], rows: dict[str, Any], cells: dict[str, Any]) -> Path:
    path = written(tmp_path, build_workbook(spec, rows))
    book = load_workbook(path)
    for reference, value in cells.items():
        book["Items"][reference] = value
    book.save(path)
    return path


def test_a_value_that_doesnt_fit_is_reported_and_left_alone(tmp_path: Path) -> None:
    spec = small_spec()
    rows = {"items": [{"_id": "1", "code": "a", "n": 1}]}
    result = diff_workbook(_with_cells(tmp_path, spec, rows, {"B2": "beaucoup"}), spec, rows)
    assert result["entities"]["items"] == NOTHING
    assert result["problems"] == [{"sheet": "Items", "cell": "B2", "field": "n"}]


def test_a_row_with_no_key_is_reported_not_added(tmp_path: Path) -> None:
    spec = small_spec()
    rows = {"items": [{"_id": "1", "code": "a", "n": 1}]}
    result = diff_workbook(_with_cells(tmp_path, spec, rows, {"B3": 5}), spec, rows)
    assert result["entities"]["items"] == NOTHING
    assert result["problems"] == [{"sheet": "Items", "cell": "row 3", "field": "missingKey"}]


def test_a_key_typed_twice_is_reported_and_only_the_first_counts(tmp_path: Path) -> None:
    spec = small_spec()
    rows = {"items": [{"_id": "1", "code": "a", "n": 1}]}
    result = diff_workbook(_with_cells(tmp_path, spec, rows, {"A3": "a", "B3": 9}), spec, rows)
    assert result["entities"]["items"] == NOTHING
    assert result["problems"] == [{"sheet": "Items", "cell": "row 3", "field": "duplicateKey"}]


def test_rows_the_app_holds_twice_arent_guessed_at(tmp_path: Path) -> None:
    spec = small_spec()
    rows = {"items": [{"_id": "1", "code": "a", "n": 1}, {"_id": "2", "code": "a", "n": 2}]}
    result = diff_workbook(written(tmp_path, build_workbook(spec, rows)), spec, rows)
    assert {"entity": "items", "field": "duplicateKey", "id": "2"} in result["problems"]


def test_an_entity_with_no_key_columns_is_reported_not_guessed(tmp_path: Path) -> None:
    spec = small_spec(keyColumns=[])
    rows = {"items": [{"_id": "1", "code": "a", "n": 1}]}
    result = diff_workbook(written(tmp_path, build_workbook(spec, rows)), spec, rows)
    assert result == {"entities": {"items": NOTHING}, "problems": [{"entity": "items", "field": "noKeyColumns"}]}


@pytest.mark.parametrize("label", ["Total", "TOTAL", "المجموع"])
def test_a_total_row_isnt_a_new_record(tmp_path: Path, label: str) -> None:
    spec = small_spec()
    rows = {"items": [{"_id": "1", "code": "a", "n": 1}]}
    assert diff_workbook(_with_cells(tmp_path, spec, rows, {"A3": label, "B3": "=SUM(B2:B2)"}), spec, rows)["entities"]["items"] == NOTHING


@pytest.mark.parametrize("label", ["Total général", "Sous-total", "المجموع العام"])
def test_a_total_row_with_a_longer_label_isnt_a_new_record(tmp_path: Path, label: str) -> None:
    spec = small_spec()
    rows = {"items": [{"_id": "1", "code": "a", "n": 1}]}
    assert diff_workbook(_with_cells(tmp_path, spec, rows, {"A3": label, "B3": "=SUM(B2:B2)"}), spec, rows)["entities"]["items"] == NOTHING


def test_a_customer_called_total_is_a_customer(tmp_path: Path) -> None:
    spec = small_spec()
    rows = {"items": [{"_id": "1", "code": "a", "n": 1}]}
    added = diff_workbook(_with_cells(tmp_path, spec, rows, {"A3": "Total Énergies", "B3": 4}), spec, rows)["entities"]["items"]["added"]
    assert [item["key"] for item in added] == ["Total Énergies"]


def test_masks_come_back_as_no_change_and_typing_over_one_is_reported(tmp_path: Path) -> None:
    fields = [
        {"key": "code", "label": {"fr": "Code", "ar": "رمز"}, "type": "text"},
        {"key": "secret", "label": {"fr": "Secret", "ar": "سر"}, "type": "decimal"},
    ]
    spec = small_spec(fields)
    rows = {"items": [{"_id": "1", "code": "a", "secret": "*"}, {"_id": "2", "code": "b", "secret": "*"}, {"_id": "3", "code": "c", "secret": "*"}]}
    path = _with_cells(tmp_path, spec, rows, {"B3": None, "B4": 99, "A5": "d"})
    result = diff_workbook(path, spec, rows)
    assert result["entities"]["items"]["changed"] == []
    assert result["problems"] == [{"sheet": "Items", "cell": "row 4", "field": "secret", "reason": "hidden"}]
    # A new row with the mask's column blank asks for nothing on it.
    assert result["entities"]["items"]["added"] == [{"key": "d", "values": {"code": "d"}}]


def test_a_year_less_tab_is_stored_with_its_year_so_the_spec_stays_valid(tmp_path: Path) -> None:
    path = tmp_path / "months.xlsx"
    book = Workbook()
    book.remove(book.active)
    for name in ("Jan", "Feb", "Mar"):
        sheet = book.create_sheet(name)
        sheet.append(["Code", "Montant"])
        for row in range(1, 7):
            sheet.append([f"C{row}", row * 10])
    book.save(path)
    snapshot = read_file(path)
    analysis = analyze_snapshot(snapshot)
    for finding in analysis["findings"]:
        if finding["kind"] != "unsupported":
            decide(finding, "accepted", "operator", at="2026-11-04T10:00:00+00:00")
    union = next(item for item in analysis["findings"] if item["kind"] == "periodUnion")
    tabs = [{**tab, "year": 2026} for tab in union["proposal"]["tabs"]]
    decide(union, "edited", "operator", {"tabs": tabs}, at="2026-11-04T10:00:00+00:00")
    spec, _, _ = Generator(analysis, snapshot).generate()
    assert validate_spec(spec) == []
    mapping = next(item for item in spec["mapping"] if len(item["sources"]) > 1)
    assert [source["period"] for source in mapping["sources"]] == ["2026-01", "2026-02", "2026-03"]


def test_the_endpoints_run_the_whole_trip(tutoring: Any) -> None:
    spec, rows = tutoring
    spec = copy.deepcopy(spec)
    client = TestClient(app)
    exported = client.post("/v1/export", json={"spec": spec, "rows": rows, "locale": "ar-DZ", "formulas": True, "timezone": "Africa/Algiers"})
    assert exported.status_code == 200
    assert "spreadsheetml" in exported.headers["content-type"]
    book = load_workbook(io.BytesIO(exported.content))
    assert book[JANVIER].sheet_view.rightToLeft
    book[JANVIER]["C4"] = 1500
    edited = io.BytesIO()
    book.save(edited)
    diff = client.post(
        "/v1/reimport/diff",
        data={"spec": json.dumps(spec), "keys": json.dumps(rows), "timezone": "Africa/Algiers"},
        files={"file": ("edited.xlsx", edited.getvalue())},
    )
    assert diff.status_code == 200
    assert [item["key"] for item in diff.json()["entities"]["paiements"]["changed"]] == ["2026-01␟E000"]


def test_the_endpoints_refuse_what_they_cant_use(tutoring: Any) -> None:
    spec, rows = tutoring
    client = TestClient(app, raise_server_exceptions=False)
    assert client.post("/v1/export", json={"spec": {"nope": 1}, "rows": {}}).json()["code"] == "invalid_spec"
    assert client.post("/v1/export", content=b"not json").json()["code"] == "invalid_spec"
    no_file = client.post("/v1/reimport/diff", data={"spec": json.dumps(spec), "keys": "{}"})
    assert no_file.json()["code"] == "unreadable"
    garbage = client.post("/v1/reimport/diff", data={"spec": json.dumps(spec), "keys": json.dumps(rows)}, files={"file": ("a.xlsx", b"not a workbook")})
    assert garbage.status_code < 500
    assert garbage.json()["code"] == "unreadable"


@pytest.mark.libreoffice
def test_libreoffice_opens_an_export_with_the_same_totals(tutoring: Any, tmp_path: Path) -> None:
    spec, rows = tutoring
    source = written(tmp_path, build_workbook(spec, rows))
    out = tmp_path / "out"
    soffice = shutil.which("soffice")
    assert soffice
    subprocess.run(
        [soffice, "--headless", f"-env:UserInstallation=file://{tmp_path}/profile", "--convert-to", "ods", "--outdir", str(out), str(source)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    sheets = {sheet["name"]: sheet for sheet in read_file(out / "out.ods")["sheets"]}
    assert set(sheets) >= {"Élèves", JANVIER}
    january = [row for row in rows["paiements"] if row["period"].startswith("2026-01")]
    cells = {cell["ref"]: cell for cell in sheets[JANVIER]["cells"]}
    total = 4 + len(january)
    assert cells[f"B{total}"]["v"] == sum(row["du"] for row in january)
    assert cells[f"C{total}"]["v"] == sum(row["paye"] for row in january)
    assert cells[f"D{total}"]["v"] == sum(row["reste"] for row in january)


