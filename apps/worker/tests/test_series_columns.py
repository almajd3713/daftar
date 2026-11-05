"""A monthly series whose tabs differ: every value must reach its own field, and come back from a file."""

from pathlib import Path
from typing import Any

from openpyxl import Workbook

from daftar_spec import validate_spec
from daftar_worker.analyser import analyze_snapshot
from daftar_worker.analyser.periods import align_columns
from daftar_worker.project.decisions import decide
from daftar_worker.project.generate import Generator, Report
from daftar_worker.reader import read_file
from daftar_worker.roundtrip.diff import diff_workbook
from daftar_worker.roundtrip.export import build_workbook


Tab = tuple[str, list[Any], list[list[Any]]]
JAN = ["Facture", "Client", "Montant"]
JAN_ROWS: list[list[Any]] = [["F1", "Ali", 100], ["F2", "Sara", 200], ["F3", "Nora", 300]]


def workbook(path: Path, tabs: list[Tab], title_rows: dict[str, int] | None = None) -> Path:
    book = Workbook()
    book.remove(book.active)
    for name, header, rows in tabs:
        sheet = book.create_sheet(name)
        for _ in range((title_rows or {}).get(name, 0)):
            sheet.append(["Suivi des factures"])
        sheet.append(header)
        for row in rows:
            sheet.append(row)
    book.save(path)
    return path


def generated(path: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], Report]:
    snapshot = read_file(path)
    analysis = analyze_snapshot(snapshot)
    for finding in analysis["findings"]:
        if finding["kind"] != "unsupported":
            decide(finding, "accepted", "operator", at="2026-11-05T10:00:00+00:00")
    spec, seed, report = Generator(analysis, snapshot).generate()
    assert not list(validate_spec(spec))
    return spec, seed, report


def only(seed: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    assert len(seed) == 1
    return next(iter(seed.values()))


def current(seed: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {key: [{"_id": f"{key}-{at}", "_version": 1, **row} for at, row in enumerate(rows)] for key, rows in seed.items()}


def test_reordered_columns_reach_their_own_fields(tmp_path: Path) -> None:
    path = workbook(
        tmp_path / "w.xlsx",
        [
            ("Janvier 2026", JAN, JAN_ROWS),
            ("Février 2026", ["Client", "Montant", "Facture"], [["Omar", 400, "F4"], ["Lina", 500, "F5"], ["Yani", 600, "F6"]]),
        ],
    )
    _, seed, report = generated(path)
    february = [row for row in only(seed) if row["period"] == "2026-02-01"]
    assert [(row["facture"], row["client"], row["montant"]) for row in february] == [("F4", "Omar", 400), ("F5", "Lina", 500), ("F6", "Yani", 600)]
    assert report.bad_values == []


def test_a_table_starting_further_right_is_read_by_name(tmp_path: Path) -> None:
    path = workbook(
        tmp_path / "w.xlsx",
        [
            ("Janvier 2026", JAN, JAN_ROWS),
            ("Février 2026", [None, *JAN], [[None, "F4", "Omar", 400], [None, "F5", "Lina", 500], [None, "F6", "Yani", 600]]),
        ],
    )
    _, seed, _ = generated(path)
    assert {"facture": "F5", "client": "Lina", "montant": 500, "period": "2026-02-01"} in only(seed)


def test_a_column_only_later_tabs_have_keeps_its_values(tmp_path: Path) -> None:
    path = workbook(
        tmp_path / "w.xlsx",
        [
            ("Janvier 2026", JAN, JAN_ROWS),
            ("Février 2026", [*JAN, "Remarque"], [["F4", "Omar", 400, "urgent"], ["F5", "Lina", 500, "à revoir"], ["F6", "Yani", 600, "reporté"]]),
        ],
    )
    spec, seed, _ = generated(path)
    mapping = spec["mapping"][0]
    extra = next(item for item in mapping["columns"] if item["header"] == "Remarque")
    assert extra["column"] == "D"
    assert [item["field"] for item in mapping["sources"][0]["columns"]].count(extra["field"]) == 0
    assert next(row for row in only(seed) if row["facture"] == "F4")[extra["field"]] == "urgent"
    assert extra["field"] not in next(row for row in only(seed) if row["facture"] == "F1")


def test_export_and_reimport_of_differing_tabs_finds_no_change(tmp_path: Path) -> None:
    path = workbook(
        tmp_path / "w.xlsx",
        [
            ("Janvier 2026", JAN, JAN_ROWS),
            ("Février 2026", ["Client", "Montant", "Facture", "Remarque"], [["Omar", 400, "F4", "urgent"], ["Lina", 500, "F5", "x"], ["Yani", 600, "F6", "y"]]),
        ],
    )
    spec, seed, _ = generated(path)
    rows = current(seed)
    exported = tmp_path / "out.xlsx"
    exported.write_bytes(build_workbook(spec, rows))
    result = diff_workbook(exported, spec, rows)
    assert result["problems"] == []
    assert result["entities"] == {next(iter(seed)): {"added": [], "changed": [], "missing": []}}
    # The original file is the same data too, in its own layout.
    again = diff_workbook(path, spec, rows)
    assert again["problems"] == []
    assert again["entities"] == {next(iter(seed)): {"added": [], "changed": [], "missing": []}}


def test_export_keeps_a_value_its_tab_had_no_column_for(tmp_path: Path) -> None:
    path = workbook(
        tmp_path / "w.xlsx",
        [
            ("Janvier 2026", JAN, JAN_ROWS),
            ("Février 2026", [*JAN, "Remarque"], [["F4", "Omar", 400, "urgent"], ["F5", "Lina", 500, "x"], ["F6", "Yani", 600, "y"]]),
        ],
    )
    spec, seed, _ = generated(path)
    rows = current(seed)
    extra = next(item["field"] for item in spec["mapping"][0]["columns"] if item["header"] == "Remarque")
    next(row for row in next(iter(rows.values())) if row["facture"] == "F1")[extra] = "ajouté dans l'app"
    exported = tmp_path / "out.xlsx"
    exported.write_bytes(build_workbook(spec, rows))
    result = diff_workbook(exported, spec, rows)
    assert result["entities"][next(iter(seed))] == {"added": [], "changed": [], "missing": []}


def test_a_different_header_row_is_kept(tmp_path: Path) -> None:
    path = workbook(
        tmp_path / "w.xlsx",
        [("Janvier 2026", JAN, JAN_ROWS), ("Février 2026", JAN, [["F4", "Omar", 400], ["F5", "Lina", 500], ["F6", "Yani", 600]])],
        title_rows={"Février 2026": 2},
    )
    spec, seed, _ = generated(path)
    february = next(item for item in spec["mapping"][0]["sources"] if item["sheet"] == "Février 2026")
    assert february["headerRow"] == 3
    rows = current(seed)
    assert diff_workbook(path, spec, rows)["entities"][next(iter(seed))] == {"added": [], "changed": [], "missing": []}


def formula_tabs(path: Path, february_formula: str) -> Path:
    book = Workbook()
    book.remove(book.active)
    for name, formula in (("Janvier 2026", "=B{row}-C{row}"), ("Février 2026", february_formula)):
        sheet = book.create_sheet(name)
        sheet.append(["Client", "Du", "Paye", "Reste"])
        for row, who in enumerate(("Ali", "Sara", "Nora", "Omar"), start=2):
            sheet.append([who, row * 100, row * 10, formula.format(row=row)])
    book.save(path)
    return path


def test_one_formula_stands_for_every_tab_only_if_it_is_the_same(tmp_path: Path) -> None:
    # The file has no stored results, so both columns stay data or formulas by their text alone.
    same = generated(formula_tabs(tmp_path / "same.xlsx", "=B{row}-C{row}"))
    assert same[2].series_formulas == []
    other = generated(formula_tabs(tmp_path / "other.xlsx", "=B{row}+C{row}"))
    assert [(item["sheet"], item["reason"]) for item in other[2].series_formulas] == [("Février 2026", "differentFormula")]
    fields = {item["key"]: item for item in other[0]["entities"][0]["fields"]}
    assert fields["reste"]["type"] != "computed"


def test_a_lower_header_row_is_the_same_formula(tmp_path: Path) -> None:
    path = tmp_path / "w.xlsx"
    book = Workbook()
    book.remove(book.active)
    for name, offset in (("Janvier 2026", 0), ("Février 2026", 2)):
        sheet = book.create_sheet(name)
        for _ in range(offset):
            sheet.append(["Suivi"])
        sheet.append(["Client", "Du", "Paye", "Reste"])
        for row, who in enumerate(("Ali", "Sara", "Nora", "Omar"), start=2 + offset):
            sheet.append([who, row * 100, row * 10, f"=B{row}-C{row}"])
    book.save(path)
    spec, _, report = generated(path)
    assert report.series_formulas == []
    fields = {item["key"]: item for item in spec["entities"][0]["fields"]}
    assert fields["reste"]["type"] == "computed"
    assert fields["reste"]["computed"]["excel"] == "=B2-C2"


def test_typed_numbers_in_one_tab_are_reported_and_kept(tmp_path: Path) -> None:
    path = tmp_path / "w.xlsx"
    book = Workbook()
    book.remove(book.active)
    for name, typed in (("Janvier 2026", False), ("Février 2026", True)):
        sheet = book.create_sheet(name)
        sheet.append(["Client", "Du", "Paye", "Reste"])
        for row, who in enumerate(("Ali", "Sara", "Nora", "Omar"), start=2):
            sheet.append([who, row * 100, row * 10, 999 if typed else f"=B{row}-C{row}"])
    book.save(path)
    spec, seed, report = generated(path)
    assert [(item["field"], item["reason"]) for item in report.series_formulas] == [("reste", "notAFormula")]
    assert {item["key"]: item for item in spec["entities"][0]["fields"]}["reste"]["type"] != "computed"
    series = next(item["key"] for item in spec["entities"] if "period" in item)
    # This file has no stored results, so the column's type is a guess: the value is what matters.
    assert float(next(row for row in seed[series] if row["period"] == "2026-02-01")["reste"]) == 999


def test_another_table_on_a_tab_is_not_lost(tmp_path: Path) -> None:
    path = tmp_path / "w.xlsx"
    book = Workbook()
    book.remove(book.active)
    for name, code in (("Janvier 2026", "F1"), ("Février 2026", "F2")):
        sheet = book.create_sheet(name)
        for row in [["Code", "Banque"], ["B1", "BNA"], ["B2", "CPA"], ["B3", "BEA"], [], [], [], JAN, *[[f"{code}{at}", f"Nom {at}", at * 100] for at in range(1, 7)]]:
            sheet.append(row)
    book.save(path)
    spec, seed, _ = generated(path)
    # The main table is the series. The small one above it isn't dropped.
    assert len(spec["entities"]) >= 2
    series = next(item for item in spec["entities"] if "period" in item)
    assert len(seed[series["key"]]) == 12


def test_align_uses_names_not_positions() -> None:
    known = ["Date", "Client", "Montant"]
    assert align_columns(known, {1: "Client", 2: "Montant", 3: "Date"}) == {1: 1, 2: 2, 3: 0}


def test_align_ignores_dates_in_headers() -> None:
    assert align_columns(["Etudiants 2011/2012"], {3: "Etudiants 2012/2013"}) == {3: 0}


def test_align_doesnt_join_columns_that_only_look_alike() -> None:
    assert align_columns(["Prix achat", "Montant HT"], {1: "Prix vente", 2: "Montant TTC"}) == {}


def test_two_columns_dont_share_one_place() -> None:
    assert align_columns(["Etudiants"], {3: "Etudiants 2015 au 10/09", 4: "Etudiants 2015 au 29/02"}) == {3: 0}
