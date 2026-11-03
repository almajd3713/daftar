"""Synthetic workbooks, built at test time so no binary fixtures enter the repo."""

from collections.abc import Callable
from datetime import datetime
from io import BytesIO
from pathlib import Path
import re
import struct
import zipfile

import olefile
import xlsxwriter
import xlwt


# A 1x1 transparent PNG.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082"
)
X14_MAIN = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
XM = "http://schemas.microsoft.com/office/excel/2006/main"
FORMULA_RECORD = 0x0006


def patch_zip(
    path: Path,
    edit: dict[str, Callable[[str], str]] | None = None,
    add: dict[str, bytes | str] | None = None,
) -> None:
    """Rewrite parts of an OOXML package, for features the writer library can't produce."""
    edit = edit or {}
    add = add or {}
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    for name, change in edit.items():
        parts[name] = change(parts[name].decode("utf-8")).encode("utf-8")
    for name, data in add.items():
        parts[name] = data.encode("utf-8") if isinstance(data, str) else data
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


def as_saved_by_excel(path: Path, calc_mode: str | None = None) -> None:
    """Make a package look as Excel leaves it: no fullCalcOnLoad flag, Excel's calcPr."""
    attribute = f' calcMode="{calc_mode}"' if calc_mode else ""
    patch_zip(
        path,
        edit={
            "xl/workbook.xml": lambda xml: re.sub(
                r"<calcPr[^>]*/>", f'<calcPr calcId="191029"{attribute}/>', xml
            )
        },
    )


def build_feature_workbook(path: Path) -> Path:
    """One workbook holding every R-2 feature. The reader and census tests count on its shape."""
    book = xlsxwriter.Workbook(str(path))
    data = book.add_worksheet("Données")
    bold = book.add_format({"bold": True})
    filled = book.add_format({"bg_color": "#FFFF00", "font_color": "#FF0000"})
    money = book.add_format({"num_format": '#,##0.00 "DA"'})
    dated = book.add_format({"num_format": "dd/mm/yyyy"})
    data.merge_range("A1:C1", "Suivi des paiements", bold)
    data.write_string("A2", "Nom", bold)
    data.write_string("B2", "Montant", bold)
    data.write_string("C2", "Double", bold)
    data.write_string("A3", "أمينة", filled)
    data.write_number("B3", 1500.5, money)
    data.write_formula("C3", "=B3*2", money, 3001)
    data.write_string("A4", "Karim")
    data.write_number("B4", 250, money)
    data.write_formula("C4", "=B4*2", money, 500)
    data.write_datetime("D3", datetime(2026, 1, 15), dated)
    data.write_boolean("E3", True)
    data.write_formula("F3", "=1/0", None, "#DIV/0!")
    data.write_formula("F4", '=_xlfn.CONCAT("a","_xlfn.b")', None, "a_xlfn.b")
    data.write_comment("A4", "À vérifier")
    data.write_blank("G3", None, filled)  # A coloured blank cell is still evidence.
    data.data_validation("E5:E9", {"validate": "list", "source": ["Payé", "Impayé"]})
    red = book.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006", "bold": True})
    data.conditional_format(
        "E5:E9", {"type": "cell", "criteria": "==", "value": '"Impayé"', "format": red}
    )
    data.conditional_format("B3:B4", {"type": "data_bar", "data_bar_2010": True})
    data.conditional_format("C3:C4", {"type": "3_color_scale"})
    column_chart = book.add_chart({"type": "column"})
    column_chart.add_series({"values": "=Données!$B$3:$B$4"})
    data.insert_chart("H2", column_chart)
    book.define_name("Taux", "=Données!$B$3")
    book.define_name("Données!Local", "=Données!$B$4")

    table = book.add_worksheet("Tableau")
    table.add_table("A1:B3", {"name": "Clients", "columns": [{"header": "Client"}, {"header": "Solde"}]})
    table.write_row("A2", ["Sara", 10])
    table.write_row("A3", ["Omar", 20])
    table.insert_image("D2", "pixel.png", {"image_data": BytesIO(PNG)})
    table.insert_textbox("D8", "Note")

    hidden = book.add_worksheet("Masqué")
    hidden.write_string("A1", "caché")
    hidden.hide()
    secret = book.add_worksheet("TrèsMasqué")
    secret.write_string("A1", "secret")
    secret.very_hidden()
    arabic = book.add_worksheet("عربي")
    arabic.right_to_left()
    arabic.write_string("A1", "الاسم")
    arabic.protect("pw")
    line_chart = book.add_chart({"type": "line"})
    line_chart.add_series({"values": "=Données!$B$3:$B$4"})
    book.add_chartsheet("Graphique").set_chart(line_chart)
    book.close()
    return path


def add_extended_parts(path: Path) -> None:
    """Add what openpyxl drops or XlsxWriter can't write: x14 lists, pivots, links, macro sheets."""
    x14 = (
        f'<extLst><ext uri="{{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}}" xmlns:x14="{X14_MAIN}">'
        f'<x14:dataValidations xmlns:xm="{XM}" count="1">'
        '<x14:dataValidation type="list" allowBlank="1"><x14:formula1><xm:f>Tableau!$A$2:$A$3</xm:f>'
        "</x14:formula1><xm:sqref>A5:A9</xm:sqref></x14:dataValidation></x14:dataValidations></ext>"
        "</extLst></worksheet>"
    )

    def add_rel(xml: str, rel_id: str, kind: str, target: str) -> str:
        return xml.replace(
            "</Relationships>",
            f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships/{kind}" Target="{target}"/></Relationships>',
        )

    def add_x14(xml: str) -> str:
        # Keep any extLst XlsxWriter already wrote: merge into it when it's there.
        if "<extLst>" in xml:
            inner = x14.removeprefix("<extLst>").removesuffix("</extLst></worksheet>")
            return xml.replace("</extLst>", inner + "</extLst>")
        return xml.replace("</worksheet>", x14)

    patch_zip(
        path,
        edit={
            "xl/worksheets/sheet1.xml": add_x14,
            "xl/worksheets/_rels/sheet1.xml.rels": lambda xml: add_rel(
                xml, "rIdPivot", "pivotTable", "../pivotTables/pivotTable1.xml"
            ),
            "xl/workbook.xml": lambda xml: xml.replace(
                "</sheets>", '<sheet name="Macro1" sheetId="99" r:id="rIdMacro"/></sheets>'
            ),
            "xl/_rels/workbook.xml.rels": lambda xml: add_rel(
                xml, "rIdMacro", "xlMacrosheet", "macrosheets/sheet1.xml"
            ),
        },
        add={
            "xl/pivotTables/pivotTable1.xml": (
                '<pivotTableDefinition xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<location ref="J5:K9"/></pivotTableDefinition>'
            ),
            "xl/externalLinks/externalLink1.xml": "<externalLink/>",
            "xl/macrosheets/sheet1.xml": "<xm:macrosheet xmlns:xm='urn:x'/>",
        },
    )


def set_stored_results(path: Path, value: float) -> None:
    """Overwrite the stored result of every formula in an .xls, as a stale file would hold it."""
    with olefile.OleFileIO(str(path), write_mode=True) as ole:
        stream = bytearray(ole.openstream("Workbook").read())
        position = 0
        found = 0
        while position + 4 <= len(stream):
            record, length = struct.unpack_from("<HH", stream, position)
            if record == FORMULA_RECORD:
                # row, column, xf, then the 8-byte stored result.
                struct.pack_into("<d", stream, position + 4 + 6, value)
                found += 1
            position += 4 + length
        assert found > 0
        ole.write_stream("Workbook", bytes(stream))


def stale_xls(path: Path, stale_value: float) -> Path:
    """A real .xls where B1 is =A1+1 and A1 is 5, whose stored result is deliberately wrong."""
    book = xlwt.Workbook()
    sheet = book.add_sheet("Feuille")
    sheet.write(0, 0, 5)
    sheet.write(0, 1, xlwt.Formula("A1+1"))
    book.save(str(path))
    set_stored_results(path, stale_value)
    return path
