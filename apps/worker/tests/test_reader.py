import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any
import zipfile

from fastapi.testclient import TestClient
from msoffcrypto.format.ooxml import OOXMLFile
import olefile
import openpyxl
import pytest
import workbook_builders as builders
import xlrd
import xlsxwriter
import xlwt

from daftar_worker.app import app
from daftar_worker.cli import main
from daftar_worker.errors import MESSAGES, WorkerError
from daftar_worker.reader import read_file
from daftar_worker.reader.colours import apply_tint
from daftar_worker.reader.legacy import LegacyFacts, scan_biff
from daftar_worker.reader.stored import Stored, encode_stored
from daftar_worker.reader.text import decode, detect_delimiter


def sheet_of(snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    return next(sheet for sheet in snapshot["sheets"] if sheet["name"] == name)


def cell_of(sheet: dict[str, Any], ref: str) -> dict[str, Any]:
    return next(cell for cell in sheet["cells"] if cell["ref"] == ref)


# --- Round trip through `daftar read` -----------------------------------------------------------


@pytest.fixture
def snapshot(feature_workbook: Path, tmp_path: Path) -> dict[str, Any]:
    output = tmp_path / "out" / "snapshot.json"
    assert main(["read", str(feature_workbook), "-o", str(output)]) == 0
    data: dict[str, Any] = json.loads(output.read_text(encoding="utf-8"))
    return data


def test_source(snapshot: dict[str, Any], feature_workbook: Path) -> None:
    source = snapshot["source"]
    assert snapshot["snapshotVersion"] == 1
    assert source["fileName"] == "toutes.xlsx"
    assert source["format"] == "xlsx"
    assert source["sha256"] == hashlib.sha256(feature_workbook.read_bytes()).hexdigest()
    assert "convertedFrom" not in source


def test_values_formulas_and_stored_results(snapshot: dict[str, Any]) -> None:
    data = sheet_of(snapshot, "Données")
    assert cell_of(data, "B3") == {"ref": "B3", "v": 1500.5, "t": "n", "fmt": '#,##0.00 "DA"'}
    formula = cell_of(data, "C3")
    assert (formula["f"], formula["v"], formula["t"]) == ("=B3*2", 3001, "n")
    assert cell_of(data, "D3")["v"] == "2026-01-15T00:00:00"
    assert cell_of(data, "D3")["t"] == "d"
    assert (cell_of(data, "E3")["v"], cell_of(data, "E3")["t"]) == (True, "b")
    error = cell_of(data, "F3")
    assert (error["v"], error["t"], error["f"]) == ("#DIV/0!", "e", "=1/0")


def test_future_function_prefix_is_removed_but_not_from_strings(snapshot: dict[str, Any]) -> None:
    assert cell_of(sheet_of(snapshot, "Données"), "F4")["f"] == '=CONCAT("a","_xlfn.b")'


def test_styles(snapshot: dict[str, Any]) -> None:
    data = sheet_of(snapshot, "Données")
    assert cell_of(data, "A3")["style"] == {"fill": "#FFFF00", "color": "#FF0000"}
    assert cell_of(data, "A2")["style"] == {"bold": True}
    assert "style" not in cell_of(data, "A4")


def test_coloured_blank_is_kept_and_plain_blank_is_not(snapshot: dict[str, Any]) -> None:
    data = sheet_of(snapshot, "Données")
    assert cell_of(data, "G3") == {
        "ref": "G3", "v": None, "t": "s", "style": {"fill": "#FFFF00", "color": "#FF0000"},
    }  # fmt: skip
    assert not any(cell["ref"] == "B1" for cell in data["cells"])  # Inside the merge.


def test_merges_comments_validations(snapshot: dict[str, Any]) -> None:
    data = sheet_of(snapshot, "Données")
    assert data["merges"] == ["A1:C1"]
    assert cell_of(data, "A1")["v"] == "Suivi des paiements"
    assert cell_of(data, "A4")["comment"] == "À vérifier"
    assert data["validations"] == [
        {"ranges": ["E5:E9"], "type": "list", "allowBlank": True, "formula1": '"Payé,Impayé"'}
    ]


def test_conditional_formats_use_the_differential_background(snapshot: dict[str, Any]) -> None:
    rules = sheet_of(snapshot, "Données")["conditionalFormats"]
    by_type = {rule["type"]: rule for rule in rules}
    assert set(by_type) == {"cellIs", "dataBar", "colorScale"}
    cell_is = by_type["cellIs"]
    assert cell_is["ranges"] == ["E5:E9"]
    assert cell_is["operator"] == "equal"
    assert cell_is["formulas"] == ['"Impayé"']
    assert cell_is["style"] == {"fill": "#FFC7CE", "color": "#9C0006", "bold": True}
    assert len(by_type["colorScale"]["colours"]) == 3


def test_tables_and_defined_names(snapshot: dict[str, Any]) -> None:
    table = sheet_of(snapshot, "Tableau")["tables"][0]
    assert (table["name"], table["ref"]) == ("Clients", "A1:B3")
    assert [column["name"] for column in table["columns"]] == ["Client", "Solde"]
    assert {"name": "Taux", "ref": "Données!$B$3"} in snapshot["definedNames"]
    assert {"name": "Local", "scope": "Données", "ref": "Données!$B$4"} in snapshot["definedNames"]


def test_sheet_state_protection_direction(snapshot: dict[str, Any]) -> None:
    names = [sheet["name"] for sheet in snapshot["sheets"]]
    assert names == ["Données", "Tableau", "Masqué", "TrèsMasqué", "عربي", "Graphique"]
    assert [sheet["index"] for sheet in snapshot["sheets"]] == list(range(6))
    assert sheet_of(snapshot, "Masqué")["state"] == "hidden"
    assert sheet_of(snapshot, "TrèsMasqué")["state"] == "veryHidden"
    arabic = sheet_of(snapshot, "عربي")
    assert (arabic["protected"], arabic["rtl"], arabic["state"]) == (True, True, "visible")
    assert sheet_of(snapshot, "Données")["protected"] is False


def test_hidden_rows_and_columns(tmp_path: Path) -> None:
    path = tmp_path / "hidden.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("H")
    sheet.write_string("A1", "x")
    for row in (4, 5, 6, 8):  # Rows 5, 6, 7 and 9 in A1 terms.
        sheet.set_row(row, None, None, {"hidden": True})
    sheet.set_column("B:C", None, None, {"hidden": True})
    sheet.set_column("E:E", None, None, {"hidden": True})
    sheet.set_column("G:XFD", None, None, {"hidden": True})  # Hiding everything unused is common.
    book.close()
    data = read_file(path)["sheets"][0]
    assert data["hiddenRows"] == ["5:7", "9:9"]
    assert data["hiddenColumns"] == ["B:C", "E:E", "G:XFD"]


def test_nothing_hidden_gives_empty_lists(snapshot: dict[str, Any]) -> None:
    data = sheet_of(snapshot, "Données")
    assert (data["hiddenRows"], data["hiddenColumns"]) == ([], [])


def test_unsupported_parts_become_entries(snapshot: dict[str, Any]) -> None:
    assert snapshot["unsupported"] == [
        {"kind": "chart", "sheet": "Données", "ref": "H2"},
        {"kind": "chart", "sheet": "Graphique"},
        {"kind": "image", "sheet": "Tableau", "ref": "D2"},
        {"kind": "shape", "sheet": "Tableau", "ref": "D8"},
    ]
    assert sheet_of(snapshot, "Graphique")["cells"] == []


def test_x14_lists_pivots_links_and_macro_sheets(feature_workbook: Path) -> None:
    builders.add_extended_parts(feature_workbook)
    snapshot = read_file(feature_workbook)
    validations = sheet_of(snapshot, "Données")["validations"]
    assert {
        "ranges": ["A5:A9"], "type": "list", "allowBlank": True, "formula1": "Tableau!$A$2:$A$3",
    } in validations  # fmt: skip
    assert {"kind": "pivot", "sheet": "Données", "ref": "J5:K9"} in snapshot["unsupported"]
    assert {"kind": "externalLink"} in snapshot["unsupported"]
    assert {"kind": "macro", "sheet": "Macro1"} in snapshot["unsupported"]
    assert sheet_of(snapshot, "Macro1")["cells"] == []


def test_macro_is_reported_and_xlsm_reads(tmp_path: Path) -> None:
    path = tmp_path / "macro.xlsm"
    book = xlsxwriter.Workbook(str(path))
    book.add_worksheet("Feuil1").write_string("A1", "x")
    book.close()
    builders.patch_zip(path, add={"xl/vbaProject.bin": b"Attribute VB_Name = never run"})
    snapshot = read_file(path)
    assert snapshot["source"]["format"] == "xlsm"
    assert {"kind": "macro"} in snapshot["unsupported"]


def test_same_input_gives_identical_output(feature_workbook: Path) -> None:
    assert json.dumps(read_file(feature_workbook)) == json.dumps(read_file(feature_workbook))


def test_shared_and_array_formulas(tmp_path: Path) -> None:
    path = tmp_path / "formulas.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("F")
    sheet.write_row("A1", [1, 2])
    sheet.write_row("A2", [3, 4])
    sheet.write_array_formula("C1:C2", "{=A1:A2*B1:B2}", None, 2)
    sheet.write_number("C2", 12)
    book.close()

    def add_shared(xml: str) -> str:
        # As Excel stores a shared formula: the text is on the first cell only.
        first, second, tail = xml.split("</row>")
        return (
            f'{first}<c r="D1"><f t="shared" ref="D1:D2" si="0">A1+1</f><v>2</v></c></row>'
            f'{second}<c r="D2"><f t="shared" si="0"/><v>4</v></c></row>{tail}'
        )

    builders.patch_zip(path, edit={"xl/worksheets/sheet1.xml": add_shared})
    data = read_file(path)["sheets"][0]
    assert cell_of(data, "C1")["f"] == "{=A1:A2*B1:B2}"
    assert cell_of(data, "C2")["f"] == "{=A1:A2*B1:B2}"
    assert (cell_of(data, "C1")["v"], cell_of(data, "C2")["v"]) == (2, 12)
    assert cell_of(data, "D1")["f"] == "=A1+1"
    assert (cell_of(data, "D2")["f"], cell_of(data, "D2")["v"]) == ("=A2+1", 4)


def test_1900_dates(tmp_path: Path) -> None:
    path = tmp_path / "dates.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("D")
    dated = book.add_format({"num_format": "dd/mm/yyyy"})
    for row, serial in enumerate([59, 60, 61, 46037]):
        sheet.write_number(row, 0, serial, dated)
    sheet.write_number(4, 0, 60)  # A plain number, not a date.
    book.close()
    data = read_file(path)["sheets"][0]
    values = [cell_of(data, f"A{row}")["v"] for row in range(1, 6)]
    assert values[0].startswith("1900-02-28")
    assert values[1] == "1900-02-29"
    assert values[2].startswith("1900-03-01")
    assert values[3].startswith("2026-01-15")
    assert values[4] == 60


def test_theme_colour_with_tint() -> None:
    assert apply_tint("4472C4", 0.0) == "4472C4"
    assert apply_tint("000000", 0.5) == "808080"
    assert apply_tint("FFFFFF", -0.5) == "808080"


def test_theme_fill_resolves_through_the_file_theme(tmp_path: Path) -> None:
    path = tmp_path / "theme.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    assert sheet is not None
    sheet["A1"] = "x"
    sheet["A1"].fill = openpyxl.styles.PatternFill(
        "solid", fgColor=openpyxl.styles.colors.Color(theme=4)
    )
    book.save(path)
    fill = read_file(path)["sheets"][0]["cells"][0]["style"]["fill"]
    assert re.fullmatch(r"#[0-9A-F]{6}", fill)
    theme = zipfile.ZipFile(path).read("xl/theme/theme1.xml").decode()
    accent = re.search(r'<a:accent1>\s*<a:srgbClr val="([0-9A-Fa-f]{6})"', theme)
    assert accent and fill == f"#{accent.group(1).upper()}"


# --- resultsFrom --------------------------------------------------------------------------------


def _with_formula(path: Path) -> Path:
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("F")
    sheet.write_number("A1", 1)
    sheet.write_formula("B1", "=A1+1", None, 2)
    book.close()
    return path


def test_results_from_excel(tmp_path: Path) -> None:
    path = _with_formula(tmp_path / "excel.xlsx")
    builders.as_saved_by_excel(path)
    source = read_file(path)["source"]
    assert (source["application"], source["resultsFrom"]) == ("Microsoft Excel", "excel")


def test_writer_library_claiming_to_be_excel_is_not_excel(tmp_path: Path) -> None:
    source = read_file(_with_formula(tmp_path / "library.xlsx"))["source"]
    assert source["application"] == "Microsoft Excel"  # XlsxWriter does write this.
    assert source["resultsFrom"] == "other"


def test_manual_calculation_is_not_excel(tmp_path: Path) -> None:
    path = _with_formula(tmp_path / "manual.xlsx")
    builders.as_saved_by_excel(path, calc_mode="manual")
    assert read_file(path)["source"]["resultsFrom"] == "other"


def test_other_application_is_not_excel(tmp_path: Path) -> None:
    path = _with_formula(tmp_path / "lo.xlsx")
    builders.as_saved_by_excel(path)
    builders.patch_zip(
        path,
        edit={
            "docProps/app.xml": lambda xml: xml.replace(
                "<Application>Microsoft Excel</Application>",
                "<Application>LibreOffice/7.4</Application>",
            )
        },
    )
    source = read_file(path)["source"]
    assert (source["application"], source["resultsFrom"]) == ("LibreOffice/7.4", "other")


def test_no_formulas_means_none(tmp_path: Path) -> None:
    path = tmp_path / "plain.xlsx"
    book = xlsxwriter.Workbook(str(path))
    book.add_worksheet("A").write_number("A1", 1)
    book.close()
    assert read_file(path)["source"]["resultsFrom"] == "none"


# --- Rejections ---------------------------------------------------------------------------------


def _assert_rejected(path: Path, code: str, temp: Path, tmp_path: Path, name: str | None = None) -> None:
    with pytest.raises(WorkerError) as caught:
        read_file(path, name)
    assert caught.value.code == code
    message = caught.value.to_json()["message"]
    assert message == MESSAGES[caught.value.code]
    assert list(temp.iterdir()) == []  # Leaves nothing behind.
    output = tmp_path / "must-not-exist.json"
    if name is None:
        assert main(["read", str(path), "-o", str(output)]) == 2
        assert not output.exists()
        assert list(tmp_path.glob(".must-not-exist*")) == []


def test_corrupt_files(tmp_path: Path, clean_temp: Path, feature_workbook: Path) -> None:
    garbage = tmp_path / "garbage.xlsx"
    garbage.write_bytes(b"this is not a workbook")
    _assert_rejected(garbage, "unreadable", clean_temp, tmp_path)

    truncated = tmp_path / "truncated.xlsx"
    truncated.write_bytes(feature_workbook.read_bytes()[:2000])
    _assert_rejected(truncated, "unreadable", clean_temp, tmp_path)

    hollow = tmp_path / "hollow.xlsx"
    with zipfile.ZipFile(hollow, "w") as archive:
        archive.writestr("hello.txt", "no workbook inside")
    _assert_rejected(hollow, "unreadable", clean_temp, tmp_path)

    fake_xls = tmp_path / "fake.xls"
    fake_xls.write_bytes(b"<html><table></table></html>")
    _assert_rejected(fake_xls, "unreadable", clean_temp, tmp_path)

    fake_ods = tmp_path / "fake.ods"
    fake_ods.write_bytes(b"not a zip")
    _assert_rejected(fake_ods, "unreadable", clean_temp, tmp_path)


def test_xml_bomb_is_refused(tmp_path: Path, clean_temp: Path, feature_workbook: Path) -> None:
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE b [<!ENTITY a "aaaaaaaaaa">'
        '<!ENTITY c "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]><workbook>&c;</workbook>'
    )
    builders.patch_zip(feature_workbook, edit={"xl/workbook.xml": lambda _: bomb})
    _assert_rejected(feature_workbook, "unreadable", clean_temp, tmp_path)


def test_password_protected_xlsx(tmp_path: Path, clean_temp: Path, feature_workbook: Path) -> None:
    protected = tmp_path / "protected.xlsx"
    with feature_workbook.open("rb") as source, protected.open("wb") as target:
        OOXMLFile(source).encrypt("secret", target)
    _assert_rejected(protected, "protected", clean_temp, tmp_path)


def test_biff_records() -> None:
    filepass = b"\x2f\x00\x02\x00\x00\x00"
    manual = b"\x0d\x00\x02\x00\x00\x00"
    automatic = b"\x0d\x00\x02\x00\x01\x00"
    # BOF as a real Excel 2010 .xls holds it, and as xlwt writes it.
    excel_bof = bytes.fromhex("0908100000060500663" "2cd07d9800100" "06060000")
    library_bof = bytes.fromhex("0908100000060500bb0dcc070000000006000000")
    assert scan_biff(excel_bof).last_saved_by_excel == 6
    assert scan_biff(library_bof).last_saved_by_excel == 0
    assert scan_biff(excel_bof + filepass).encrypted is True
    assert scan_biff(excel_bof).encrypted is False
    assert scan_biff(excel_bof + automatic).automatic_calc is True
    assert scan_biff(excel_bof + manual).automatic_calc is False
    assert scan_biff(excel_bof + automatic + manual).automatic_calc is False


def test_password_protected_ods(tmp_path: Path, clean_temp: Path) -> None:
    path = tmp_path / "protected.ods"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        archive.writestr(
            "META-INF/manifest.xml",
            '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
            '<manifest:file-entry manifest:full-path="content.xml"><manifest:encryption-data/>'
            "</manifest:file-entry></manifest:manifest>",
        )
    _assert_rejected(path, "protected", clean_temp, tmp_path)


def test_oversized_file(tmp_path: Path, clean_temp: Path) -> None:
    path = tmp_path / "big.xlsx"
    with path.open("wb") as stream:
        stream.truncate(25 * 1024 * 1024 + 1)
    _assert_rejected(path, "too_large", clean_temp, tmp_path)


def test_a_file_exactly_at_the_size_limit_is_not_too_large(tmp_path: Path) -> None:
    path = tmp_path / "limit.csv"
    path.write_bytes(b"a,b\n" + b" " * (25 * 1024 * 1024 - 4))
    assert read_file(path)["source"]["format"] == "csv"


def test_too_many_cells(
    tmp_path: Path, clean_temp: Path, feature_workbook: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("daftar_worker.reader.raw.MAX_CELLS", 3)
    _assert_rejected(feature_workbook, "too_large", clean_temp, tmp_path)
    monkeypatch.setattr("daftar_worker.reader.text.MAX_CELLS", 3)
    table = tmp_path / "wide.csv"
    table.write_text("a,b\nc,d\n", encoding="utf-8")
    _assert_rejected(table, "too_large", clean_temp, tmp_path)


def test_exactly_the_cell_limit_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("daftar_worker.reader.text.MAX_CELLS", 4)
    table = tmp_path / "exact.csv"
    table.write_text("a,b\nc,d\n", encoding="utf-8")
    assert len(read_file(table)["sheets"][0]["cells"]) == 4


def test_unsupported_format(tmp_path: Path, clean_temp: Path) -> None:
    for name in ("notes.txt", "book.xlsb", "noextension"):
        path = tmp_path / name
        path.write_bytes(b"x")
        _assert_rejected(path, "unsupported_format", clean_temp, tmp_path)


def test_every_error_has_both_languages() -> None:
    for message in MESSAGES.values():
        assert message["fr"].strip() and message["ar"].strip()
        assert re.search(r"[؀-ۿ]", message["ar"])


# --- CSV ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ("Prénom;Tél\nAmina;0550123456\n".encode("utf-8-sig"), "Prénom"),
        ("Prénom;Tél\nAmina;0550123456\n".encode(), "Prénom"),
        ("Prénom;Tél\nÉlodie;0550123456\n".encode("cp1252"), "Prénom"),
        ("الاسم;الهاتف\nأمينة;0550123456\n".encode("cp1256"), "الاسم"),
        ("الاسم;الهاتف\nأمينة;0550123456\n".encode("utf-16"), "الاسم"),
    ],
    ids=["utf8-bom", "utf8", "cp1252-french", "cp1256-arabic", "utf16"],
)
def test_csv_encodings(data: bytes, expected: str) -> None:
    assert decode(data).splitlines()[0].split(";")[0] == expected


@pytest.mark.parametrize(
    ("text", "delimiter"),
    [
        ("a,b,c\n1,2,3\n", ","),
        ("a;b;c\n1;2;3\n", ";"),
        ("a\tb\n1\t2\n", "\t"),
        ("a|b\n1|2\n", "|"),
        ("prix;total\n1,5;2,5\n3,5;4,5\n", ";"),
        ('nom,adresse\n"a;b",c\n"d;e",f\n', ","),
    ],
    ids=["comma", "semicolon", "tab", "pipe", "french-decimals", "quoted-semicolons"],
)
def test_csv_delimiters(text: str, delimiter: str) -> None:
    assert detect_delimiter(text) == delimiter


def test_csv_snapshot_keeps_text_as_written(tmp_path: Path) -> None:
    path = tmp_path / "élèves.csv"
    path.write_bytes("Nom;Téléphone\nأمينة;0550123456\n;\nKarim;\n".encode("utf-8-sig"))
    snapshot = read_file(path)
    assert snapshot["source"]["format"] == "csv"
    assert snapshot["source"]["resultsFrom"] == "none"
    sheet = snapshot["sheets"][0]
    assert sheet["name"] == "élèves"
    assert sheet["dimension"] == "A1:B4"
    assert cell_of(sheet, "B2") == {"ref": "B2", "v": "0550123456", "t": "s"}
    assert cell_of(sheet, "A2")["v"] == "أمينة"
    assert [cell["ref"] for cell in sheet["cells"]] == ["A1", "B1", "A2", "B2", "A4"]


def test_binary_named_csv_is_refused(tmp_path: Path, clean_temp: Path) -> None:
    path = tmp_path / "binary.csv"
    path.write_bytes(b"\x00\x01\x02\x03")
    _assert_rejected(path, "unreadable", clean_temp, tmp_path)


# --- Stored results ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stored", "is_date", "mode", "expected"),
    [
        (Stored("number", 6.0), False, 0, (6, "n")),
        (Stored("number", 1.5), False, 0, (1.5, "n")),
        (Stored("number", 46037.0), True, 0, ("2026-01-15T00:00:00", "d")),
        (Stored("number", 60.0), True, 0, ("1900-02-29", "d")),
        (Stored("number", 1.0), True, 1, ("1904-01-02T00:00:00", "d")),
        (Stored("text", "abc"), False, 0, ("abc", "s")),
        (Stored("text", ""), False, 0, (None, "s")),
        (Stored("boolean", 1), False, 0, (True, "b")),
        (Stored("error", "#DIV/0!"), False, 0, ("#DIV/0!", "e")),
        (Stored("date", "2026-01-15"), False, 0, ("2026-01-15", "d")),
    ],
)
def test_encode_stored(stored: Stored, is_date: bool, mode: int, expected: tuple[Any, str]) -> None:
    assert encode_stored(stored, is_date, mode) == expected


# --- HTTP ---------------------------------------------------------------------------------------


def test_http_read(feature_workbook: Path, clean_temp: Path) -> None:
    client = TestClient(app)
    with feature_workbook.open("rb") as stream:
        response = client.post("/v1/read", files={"file": ("../../etc/toutes.xlsx", stream)})
    assert response.status_code == 200
    assert response.json()["source"]["fileName"] == "toutes.xlsx"
    assert list(clean_temp.glob("daftar-*")) == []


@pytest.mark.parametrize(
    ("name", "data", "status", "code"),
    [
        ("a.xlsx", b"garbage", 422, "unreadable"),
        ("a.txt", b"hello", 415, "unsupported_format"),
        ("big.csv", b"a" * (25 * 1024 * 1024 + 1), 413, "too_large"),
    ],
    ids=["corrupt", "format", "too-large"],
)
def test_http_errors(name: str, data: bytes, status: int, code: str, clean_temp: Path) -> None:
    response = TestClient(app).post("/v1/read", files={"file": (name, data)})
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    assert body["message"] == MESSAGES[code]  # type: ignore[index]
    assert list(clean_temp.glob("daftar-*")) == []


def test_http_without_a_file() -> None:
    response = TestClient(app).post("/v1/read", data={"nothing": "here"})
    assert response.status_code == 422
    assert response.json()["code"] == "unreadable"


# --- LibreOffice conversion: runs in the worker test image --------------------------------------


@pytest.mark.libreoffice
@pytest.mark.parametrize("stale", [0.0, 999.0], ids=["zero", "nonzero"])
def test_converted_xls_keeps_stale_stored_results(tmp_path: Path, stale: float) -> None:
    path = builders.stale_xls(tmp_path / "stale.xls", stale)

    direct = xlrd.open_workbook(str(path)).sheet_by_index(0)
    assert direct.cell_value(0, 1) == stale  # The original holds the wrong result on purpose.
    fresh = direct.cell_value(0, 0) + 1
    assert fresh == 6 and stale != fresh

    snapshot = read_file(path)
    cell = cell_of(snapshot["sheets"][0], "B1")
    assert cell["f"] == "=A1+1"
    assert cell["v"] == direct.cell_value(0, 1), "LibreOffice recalculated during conversion"
    assert snapshot["source"]["convertedFrom"] == "xls"
    assert snapshot["source"]["format"] == "xls"


@pytest.mark.libreoffice
def test_stale_date_result_in_xls_stays_a_date(tmp_path: Path) -> None:
    path = tmp_path / "date.xls"
    book = xlwt.Workbook()
    sheet = book.add_sheet("D")
    sheet.write(0, 0, 5)
    sheet.write(0, 1, xlwt.Formula("A1+1"), xlwt.easyxf(num_format_str="dd/mm/yyyy"))
    book.save(str(path))
    builders.set_stored_results(path, 46037.0)
    cell = cell_of(read_file(path)["sheets"][0], "B1")
    assert (cell["t"], cell["v"]) == ("d", "2026-01-15T00:00:00")


@pytest.mark.libreoffice
def test_unrestorable_result_is_not_excel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = builders.stale_xls(tmp_path / "stale.xls", 999.0)
    monkeypatch.setattr("daftar_worker.reader.xls_lookup", lambda _: ((lambda *_: None), 0))
    monkeypatch.setattr(
        "daftar_worker.reader.inspect_xls",
        lambda _: (False, LegacyFacts("Microsoft Excel", True, False)),
    )
    assert read_file(path)["source"]["resultsFrom"] == "other"


@pytest.mark.libreoffice
def test_xls_saved_by_excel_with_stale_result_is_excel_and_keeps_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = builders.stale_xls(tmp_path / "stale.xls", 999.0)
    monkeypatch.setattr(
        "daftar_worker.reader.inspect_xls",
        lambda _: (False, LegacyFacts("Microsoft Excel", True, False)),
    )
    snapshot = read_file(path)
    assert snapshot["source"]["resultsFrom"] == "excel"
    assert cell_of(snapshot["sheets"][0], "B1")["v"] == 999


def _stamp_excel_version(path: Path, version: int) -> None:
    with olefile.OleFileIO(str(path), write_mode=True) as ole:
        stream = bytearray(ole.openstream("Workbook").read())
        assert stream[:2] == b"\x09\x08"
        stream[4 + 13] = version
        ole.write_stream("Workbook", bytes(stream))


@pytest.mark.libreoffice
def test_xls_stamped_by_excel_counts_even_without_an_application_name(tmp_path: Path) -> None:
    path = builders.stale_xls(tmp_path / "stale.xls", 999.0)
    _stamp_excel_version(path, 6)
    source = read_file(path)["source"]
    assert (source["application"], source["resultsFrom"]) == ("Microsoft Excel", "excel")


@pytest.mark.libreoffice
def test_xls_written_by_libreoffice_is_not_excel(tmp_path: Path) -> None:
    source = builders.stale_xls(tmp_path / "input.xls", 999.0)
    output = tmp_path / "out"
    profile = tmp_path / "profile"
    subprocess.run(
        [
            "soffice", f"-env:UserInstallation={profile.as_uri()}", "--headless", "--norestore",
            "--convert-to", "xls:MS Excel 97", "--outdir", str(output), str(source),
        ],
        check=True, capture_output=True, timeout=170,
    )  # fmt: skip
    snapshot = read_file(output / "input.xls")
    assert snapshot["source"]["resultsFrom"] == "other"
    assert snapshot["source"].get("application") != "Microsoft Excel"


@pytest.mark.libreoffice
def test_converted_xls_is_not_excel_unless_excel_saved_it(tmp_path: Path) -> None:
    path = builders.stale_xls(tmp_path / "stale.xls", 999.0)
    assert read_file(path)["source"]["resultsFrom"] == "other"  # xlwt wrote this file.


@pytest.mark.libreoffice
def test_xls_features_and_french_arabic_text(tmp_path: Path, clean_temp: Path) -> None:
    path = tmp_path / "plain.xls"
    book = xlwt.Workbook(encoding="utf-8")
    sheet = book.add_sheet("Élèves")
    sheet.write(0, 0, "أمينة")
    sheet.write(0, 1, "Prénom")
    sheet.write_merge(2, 2, 0, 1, "Total")
    sheet.row(4).hidden = True
    sheet.col(3).hidden = True
    sheet.write(4, 3, "caché")
    hidden = book.add_sheet("Caché")
    hidden.write(0, 0, 1)
    hidden.visibility = 1
    book.save(str(path))
    snapshot = read_file(path)
    first = sheet_of(snapshot, "Élèves")
    assert cell_of(first, "A1")["v"] == "أمينة"
    assert first["merges"] == ["A3:B3"]
    assert sheet_of(snapshot, "Caché")["state"] == "hidden"
    assert first["hiddenRows"] == ["5:5"]
    assert first["hiddenColumns"] == ["D:D"]
    assert snapshot["source"]["resultsFrom"] == "none"
    assert list(clean_temp.iterdir()) == []


@pytest.mark.libreoffice
def test_ods_keeps_stored_results_and_is_never_excel(tmp_path: Path) -> None:
    path = tmp_path / "plain.ods"
    content = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 xmlns:of="urn:oasis:names:tc:opendocument:xmlns:of:1.2" office:version="1.2">
<office:body><office:spreadsheet><table:table table:name="Feuille"><table:table-row>
<table:table-cell office:value-type="float" office:value="5"><text:p>5</text:p></table:table-cell>
<table:table-cell table:formula="of:=[.A1]+1" office:value-type="float" office:value="999"><text:p>999</text:p></table:table-cell>
</table:table-row></table:table></office:spreadsheet></office:body></office:document-content>"""
    meta = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0" office:version="1.2"><office:meta>
<meta:generator>LibreOffice/7.4.7.2</meta:generator></office:meta></office:document-meta>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        archive.writestr("content.xml", content)
        archive.writestr("meta.xml", meta)
        archive.writestr(
            "META-INF/manifest.xml",
            '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
            '<manifest:file-entry manifest:full-path="/" '
            'manifest:media-type="application/vnd.oasis.opendocument.spreadsheet"/>'
            '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
            '<manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/>'
            "</manifest:manifest>",
        )
    snapshot = read_file(path)
    cell = cell_of(snapshot["sheets"][0], "B1")
    assert cell["v"] == 999
    assert cell["f"] == "=A1+1"
    assert snapshot["source"]["convertedFrom"] == "ods"
    assert snapshot["source"]["application"].startswith("LibreOffice")
    assert snapshot["source"]["resultsFrom"] == "other"


def test_missing_libreoffice_is_reported_cleanly(
    tmp_path: Path, clean_temp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("daftar_worker.reader.convert.soffice_path", lambda: None)
    path = builders.stale_xls(tmp_path / "stale.xls", 1.0)
    _assert_rejected(path, "unreadable", clean_temp, tmp_path)
