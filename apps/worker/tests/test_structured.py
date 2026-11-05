"""Structured references become A1, in the snapshot and in the engine (R-19)."""

from pathlib import Path
import zipfile

from formualizer import Workbook
import pytest
import xlsxwriter

from daftar_worker.formulas.engine import EngineError, EngineWorkbook
from daftar_worker.formulas.parity import run_parity
from daftar_worker.reader import read_file
from daftar_worker.reader.structured import SheetTable, expand_formula


# Headers on row 1, data on rows 2 to 4, totals on row 5, in columns B to D of Feuille.
TABLE = SheetTable("Ventes", "Feuille", 1, 2, 5, 4, 1, 1, ("Qté", "Prix unit", "Note [x]"))


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("=Ventes[[#This Row],[Qté]]*2", "=B3*2"),
        ("=Ventes[@Qté]*Ventes[@[Prix unit]]", "=B3*C3"),
        ("=SUM(Ventes[Qté])", "=SUM($B$2:$B$4)"),
        ("=SUM(ventes[QTÉ])", "=SUM($B$2:$B$4)"),
        ("=SUM(Ventes[[Qté]:[Prix unit]])", "=SUM($B$2:$C$4)"),
        ("=SUM(Ventes[[#This Row],[Qté]:[Prix unit]])", "=SUM(B3:C3)"),
        ("=COUNTA(Ventes[#All])", "=COUNTA($B$1:$D$5)"),
        ("=COUNT(Ventes[#Data])", "=COUNT($B$2:$D$4)"),
        ("=COUNT(Ventes[])", "=COUNT($B$2:$D$4)"),
        ("=Ventes[[#Totals],[Qté]]", "=$B$5"),
        ("=Ventes[[#Headers],[Qté]]", "=$B$1"),
        ("=COUNTA(Ventes[[#Headers],[#Data],[Qté]])", "=COUNTA($B$1:$B$4)"),
        ("=Ventes[Note '[x']]", "=$D$2:$D$4"),
        ('=IF(A1="Ventes[Qté]",1,0)', '=IF(A1="Ventes[Qté]",1,0)'),
        ("=[@Qté]+1", "=B3+1"),
        ("=SUM([Qté])", "=SUM($B$2:$B$4)"),
    ],
)
def test_expansion(formula: str, expected: str) -> None:
    assert expand_formula(formula, [TABLE], "Feuille", 3, 4) == expected


def test_another_sheet_names_the_sheet() -> None:
    assert expand_formula("=SUM(Ventes[Qté])", [TABLE], "Mon total", 1, 1) == "=SUM(Feuille!$B$2:$B$4)"
    other = SheetTable("T", "Mes ventes", 1, 1, 3, 1, 1, 0, ("A",))
    assert expand_formula("=SUM(T[A])", [other], "Feuille", 1, 1) == "=SUM('Mes ventes'!$A$2:$A$3)"


@pytest.mark.parametrize(
    "formula",
    [
        "=Ventes[Inconnue]",
        "=Autre[Qté]",
        "=[1]Feuil1!A1",
        "=SUM([1]!Ventes[Qté])",
        "=SUM('[classeur.xlsx]Feuil1'!Ventes[Qté])",
        "='[classeur.xlsx]Feuil1'!A1",
        "=Ventes[[#Headers],[#Totals]]",
    ],
)
def test_what_cant_be_resolved_stays_as_written(formula: str) -> None:
    assert expand_formula(formula, [TABLE], "Feuille", 3, 4) == formula


def test_this_row_outside_the_data_stays_as_written() -> None:
    assert expand_formula("=Ventes[@Qté]", [TABLE], "Feuille", 9, 9) == "=Ventes[@Qté]"


@pytest.fixture(name="workbook")
def fixture_workbook(tmp_path: Path) -> Path:
    path = tmp_path / "t.xlsx"
    book = xlsxwriter.Workbook(path)
    sheet = book.add_worksheet("Ventes")
    data = [[2, 10], [3, 20], [4, 30]]
    sheet.add_table(
        "A1:C4",
        {
            "name": "T",
            "data": data,
            "columns": [{"header": "Qté"}, {"header": "Prix"}, {"header": "Total", "formula": "=[@Qté]*[@Prix]"}],
        },
    )
    for row, (quantity, price) in enumerate(data, start=2):
        sheet.write_formula(row - 1, 2, "=T[[#This Row],[Qté]]*T[[#This Row],[Prix]]", None, quantity * price)
    sheet.write_formula("E1", "=SUM(T[Total])", None, 200)
    other = book.add_worksheet("Bilan")
    other.write_formula("A1", "=SUM(T[Qté])", None, 9)
    book.close()
    return path


def test_the_reader_gives_a1_and_keeps_the_original(workbook: Path) -> None:
    snapshot = read_file(workbook)
    cells = {cell["ref"]: cell for cell in snapshot["sheets"][0]["cells"]}
    assert cells["C2"]["f"] == "=A2*B2"
    assert cells["C2"]["fStructured"] == "=T[[#This Row],[Qté]]*T[[#This Row],[Prix]]"
    assert cells["E1"]["f"] == "=SUM($C$2:$C$4)"
    assert snapshot["sheets"][1]["cells"][0]["f"] == "=SUM(Ventes!$A$2:$A$4)"
    assert "fStructured" not in cells["A2"]


def test_the_engine_gets_excels_results(workbook: Path) -> None:
    report = run_parity(workbook, read_file(workbook))
    assert report["cells"] == 5
    assert report["equal"] == 5


def test_replacements_win_over_the_file(workbook: Path) -> None:
    engine = EngineWorkbook(str(workbook), replacements=[("Ventes", 1, 5, "=1+1")])
    assert engine.value("Ventes", 1, 5).value == 2


def test_a_zip_the_engine_refuses_is_repacked(tmp_path: Path) -> None:
    plain = tmp_path / "plain.xlsx"
    book = xlsxwriter.Workbook(plain)
    book.add_worksheet("S").write_formula("A1", "=1+2", None, 3)
    book.close()
    awkward = tmp_path / "zip64.xlsx"
    with zipfile.ZipFile(plain) as source, zipfile.ZipFile(awkward, "w", zipfile.ZIP_DEFLATED) as out:
        for name in source.namelist():
            with out.open(name, "w", force_zip64=True) as member:
                member.write(source.read(name))
    with pytest.raises(OSError, match="ZIP64"):
        Workbook.from_path(str(awkward))
    assert EngineWorkbook(str(awkward)).value("S", 1, 1).value == 3


def test_a_file_that_really_is_broken_is_still_an_engine_error(tmp_path: Path) -> None:
    broken = tmp_path / "broken.xlsx"
    broken.write_bytes(b"not a zip")
    with pytest.raises(EngineError):
        EngineWorkbook(str(broken))
