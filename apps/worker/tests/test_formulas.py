from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import ironcalc
from jsonschema import Draft202012Validator
from openpyxl.utils.cell import column_index_from_string, coordinate_from_string
import pytest
import workbook_builders as builders
import xlsxwriter

from daftar_spec import load_schema
from daftar_worker.analyser import analyze_snapshot
from daftar_worker.cli import main
from daftar_worker.evaluation.run import run_evaluation
from daftar_worker.formulas.calculators import cells_read_by
from daftar_worker.formulas.engine import (
    EngineValue,
    evaluate_cells,
    is_supported,
    parse_formula,
)
from daftar_worker.formulas.evaluate import (
    TRANSLATABLE,
    Evaluator,
    ExcelError,
    from_serial,
    to_serial,
)
from daftar_worker.formulas.parity import last_saved, run_parity, values_match
from daftar_worker.formulas.references import relative_form
from daftar_worker.formulas.translate import translate
from daftar_worker.reader import read_file


RECORD_ROW = 2
# Row 2 of every fixture: A number, B number, C text, D blank, E boolean, F date serial, G number.
RECORD: dict[int, Any] = {1: 7.5, 2: -2.0, 3: "Bonjour le Monde", 5: True, 6: 46037.0, 7: 3.0}
TYPES = {1: "number", 2: "number", 3: "text", 4: "any", 5: "boolean", 6: "date", 7: "number"}
EVAL_RECORD = {"col_a": 7.5, "col_b": -2.0, "col_c": "Bonjour le Monde", "col_d": None, "col_e": True, "col_f": 46037.0, "col_g": 3.0}

# (formula, expected). None as the expected value means "whatever the engine says"; those are
# still checked for agreement. Hand-known values are written out where the answer is unambiguous.
CASES: list[tuple[str, Any]] = [
    ("=A2+G2", 10.5), ("=A2-G2", 4.5), ("=A2*G2", 22.5), ("=A2/G2", 2.5), ("=G2^2", 9.0), ("=-A2", -7.5),
    ("=A2%", 0.075), ('=C2&"!"', "Bonjour le Monde!"), ("=A2&G2", "7.53"), ("=A2=7.5", True), ("=A2<>7.5", False),
    ("=A2<G2", False), ("=A2<=7.5", True), ("=A2>G2", True), ("=A2>=8", False), ('=C2="BONJOUR LE MONDE"', True),
    ("=D2+1", 1.0), ('=D2=""', True), ("=D2=0", True), ("=E2+1", 2.0), ('="3"+1', 4.0), ('="x"+1', "#VALUE!"),
    ("=A2/0", "#DIV/0!"), ("=A2/D2", "#DIV/0!"),
    ("=ABS(B2)", 2.0), ("=INT(A2)", 7.0), ("=INT(B2-0.5)", -3.0), ("=SQRT(G2*3)", 3.0), ("=SQRT(B2)", "#NUM!"),
    ("=POWER(G2,3)", 27.0), ("=MOD(A2,2)", 1.5), ("=MOD(-7,3)", 2.0), ("=MOD(A2,0)", "#DIV/0!"),
    ("=ROUND(2.5,0)", 3.0), ("=ROUND(-2.5,0)", -3.0), ("=ROUND(1.005,2)", 1.01), ("=ROUND(1234.5,-2)", 1200.0),
    ("=ROUNDUP(1.21,1)", 1.3), ("=ROUNDDOWN(1.29,1)", 1.2), ("=ROUNDUP(-1.21,1)", -1.3), ("=MROUND(17,5)", 15.0),
    ("=MROUND(18,5)", 20.0), ("=CEILING(7.1,1)", 8.0), ("=FLOOR(7.9,1)", 7.0), ("=CEILING(7,2)", 8.0),
    ("=SUM(A2,G2)", 10.5), ("=SUM(A2:B2)", 5.5), ("=SUM(A2:C2)", 5.5), ("=MIN(A2:B2)", -2.0), ("=MAX(A2:B2)", 7.5),
    ("=AVERAGE(A2,G2)", 5.25), ("=COUNT(A2:D2)", 2.0), ("=COUNTA(A2:D2)", 3.0), ("=PRODUCT(A2,G2)", 22.5),
    ("=IF(A2>1,G2,0)", 3.0), ("=IF(A2<1,G2)", False), ('=IF(A2>1,"oui","non")', "oui"), ("=IF(A2>1,1,1/0)", 1.0),
    ("=IFS(A2<1,1,A2<10,2)", 2.0), ("=IFS(A2<1,1)", "#N/A"), ("=AND(A2>1,G2>1)", True), ("=AND(A2>1,G2<1)", False),
    ("=OR(A2<1,G2>1)", True), ("=OR(A2<1,G2<1)", False), ("=NOT(E2)", False), ("=TRUE()", True), ("=FALSE()", False),
    ("=IFERROR(A2/0,9)", 9.0), ("=IFERROR(A2,9)", 7.5), ("=IFNA(NA(),9)", 9.0), ("=NA()", "#N/A"),
    ("=SWITCH(G2,1,10,3,30)", 30.0), ("=SWITCH(G2,1,10,99)", 99.0), ("=SWITCH(G2,1,10)", "#N/A"),
    ("=ISBLANK(D2)", True), ("=ISBLANK(A2)", False), ("=ISNUMBER(A2)", True), ("=ISNUMBER(C2)", False),
    ("=ISTEXT(C2)", True), ("=ISERROR(A2/0)", True), ("=ISERROR(A2)", False), ("=ISNA(NA())", True), ("=ISNA(A2/0)", False),
    ('=CONCATENATE(C2," ",G2)', "Bonjour le Monde 3"), ('=CONCAT(C2,"-",A2)', "Bonjour le Monde-7.5"),
    ("=LEFT(C2,7)", "Bonjour"), ("=RIGHT(C2,5)", "Monde"), ("=MID(C2,9,2)", "le"), ("=LEFT(C2)", "B"), ("=LEN(C2)", 16.0),
    ('=TRIM("  a   b  ")', "a b"), ("=UPPER(C2)", "BONJOUR LE MONDE"), ("=LOWER(C2)", "bonjour le monde"),
    ('=PROPER("bonJOUR le monde")', "Bonjour Le Monde"), ('=SUBSTITUTE(C2,"o","0")', "B0nj0ur le M0nde"),
    ('=SUBSTITUTE(C2,"o","0",2)', "Bonj0ur le Monde"), ('=REPLACE(C2,1,7,"Salut")', "Salut le Monde"),
    ('=FIND("le",C2)', 9.0), ('=FIND("LE",C2)', "#VALUE!"), ('=SEARCH("LE",C2)', 9.0), ('=VALUE("12.5")', 12.5),
    ('=EXACT("a","a")', True), ('=EXACT("a","A")', False), ('=REPT("ab",2)', "abab"),
    ("=DATE(2026,1,15)", 46037.0), ("=DATE(2026,14,1)", 46419.0), ("=DATE(2026,1,32)", 46054.0), ("=YEAR(F2)", 2026.0),
    ("=MONTH(F2)", 1.0), ("=DAY(F2)", 15.0), ("=HOUR(0.5)", 12.0), ("=MINUTE(0.75)", 0.0), ("=SECOND(0.5)", 0.0),
    ("=WEEKDAY(F2)", 5.0), ("=WEEKDAY(F2,2)", 4.0), ("=WEEKDAY(F2,3)", 3.0), ("=EDATE(F2,1)", 46068.0),
    ("=EDATE(F2,-1)", 46006.0), ("=EDATE(DATE(2026,1,31),1)", 46081.0), ("=EOMONTH(F2,0)", 46053.0), ("=EOMONTH(F2,1)", 46081.0),
    ("=DAYS(F2,46000)", 37.0), ("=TODAY()", 46000.0), ("=NOW()", None),
]  # fmt: skip
CLOCK = datetime(2025, 12, 9, 12, 0, tzinfo=timezone.utc)  # Serial 46000.5.


def _as_scalar(value: EngineValue) -> Any:
    if value.kind == "error":
        return value.value
    if value.kind == "date":
        return to_serial(value.value)
    if value.kind == "time":
        moment = value.value
        return (moment.hour * 3600 + moment.minute * 60 + moment.second) / 86400
    return value.value


def _engine_result(formula: str) -> Any:
    cells: list[tuple[str, int, int, Any, str | None]] = [
        ("S", RECORD_ROW, column, value, None) for column, value in RECORD.items()
    ]
    cells.append(("S", RECORD_ROW, 9, None, formula))
    return _as_scalar(evaluate_cells(cells, [("S", RECORD_ROW, 9)], CLOCK)[0])


def _translated_result(formula: str) -> Any:
    translation = translate(formula, "S", RECORD_ROW, TYPES)
    assert translation.expr is not None, f"{formula}: {translation.reasons}"
    result = Evaluator(EVAL_RECORD, now=CLOCK.replace(tzinfo=None)).run(translation.expr)
    return result.code if isinstance(result, ExcelError) else result


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-12)
    return bool(left == right)


@pytest.mark.parametrize(("formula", "expected"), CASES, ids=[case[0] for case in CASES])
def test_translated_and_engine_agree(formula: str, expected: Any) -> None:
    translated = _translated_result(formula)
    engine = _engine_result(formula)
    assert _same(translated, engine), f"translated {translated!r}, engine {engine!r}"
    if expected is not None:
        assert _same(translated, expected), f"translated {translated!r}, expected {expected!r}"


def test_every_translatable_function_has_a_fixture() -> None:
    used: set[str] = set()
    for formula, _ in CASES:
        translation = translate(formula, "S", RECORD_ROW, TYPES)
        used |= translation.functions
    assert TRANSLATABLE - used == set()


def test_every_translatable_function_is_known_to_the_engine() -> None:
    assert {name for name in TRANSLATABLE if not is_supported(name)} == set()


# --- IronCalc is the independent cross-check (D-5) ----------------------------------------------

def _ironcalc_result(formula: str) -> Any:
    model = ironcalc.create("check", "en", "UTC")
    for column, value in RECORD.items():
        model.set_user_input(0, RECORD_ROW, column, str(value).upper() if isinstance(value, bool) else str(value))
    model.set_user_input(0, RECORD_ROW, 9, formula)
    model.evaluate()
    return model.get_cell_value(0, RECORD_ROW, 9)


NO_CLOCK = {"=TODAY()", "=NOW()"}


@pytest.mark.parametrize(
    ("formula", "expected"),
    [case for case in CASES if case[0] not in NO_CLOCK],
    ids=[case[0] for case in CASES if case[0] not in NO_CLOCK],
)
def test_ironcalc_agrees_on_the_fixtures(formula: str, expected: Any) -> None:
    other = _ironcalc_result(formula)
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        assert isinstance(other, (int, float)) and math.isclose(float(other), expected, rel_tol=1e-9, abs_tol=1e-12), other
    else:
        assert other == expected


# --- Translation rules --------------------------------------------------------------------------


def _translate(formula: str, row: int = RECORD_ROW) -> Any:
    return translate(formula, "S", row, TYPES)


def test_same_row_references_become_fields() -> None:
    translation = _translate("=A2*G2")
    assert translation.deps == ["col_a", "col_g"]
    assert translation.expr == {
        "kind": "op",
        "valueType": "number",
        "op": "mul",
        "args": [
            {"kind": "field", "valueType": "number", "field": "col_a"},
            {"kind": "field", "valueType": "number", "field": "col_g"},
        ],
    }


@pytest.mark.parametrize(
    ("formula", "reason"),
    [
        ("=A2*$H$1", "otherRow"),  # An absolute cell outside the record.
        ("=A1+A2", "otherRow"),
        ("=A2*Taux", "namedOrTableReference"),
        ("=SUM(A:A)", "wholeColumn"),
        ("=Tarifs!B2", "otherSheet"),
        ("=TEXT(F2,\"mmm\")", "function:TEXT"),
        ("=SUMIF(A:A,1,B:B)", "function:SUMIF"),
        ("=UNHEARDOF(A2)", "function:UNHEARDOF"),
        ("=IF(A2,,1)", "omittedArgument"),
        ("{=SUM(A2:B2*2)}", "arrayFormula"),
        ("=A2+Z2", "referenceOutsideTable"),
    ],
)
def test_what_a_record_cant_compute_stays_with_the_engine(formula: str, reason: str) -> None:
    translation = _translate(formula)
    assert translation.expr is None
    assert translation.reasons == [reason]


def test_exact_lookups_become_related_and_relation_evidence() -> None:
    translation = _translate("=VLOOKUP(A2,Prix!$A$2:$C$9,3,FALSE)")
    assert translation.expr == {"kind": "related", "valueType": "any", "via": "col_a", "field": "col_c"}
    lookup = translation.lookups[0]
    assert (lookup.from_column, lookup.to_sheet, lookup.key_column, lookup.result_column) == (1, "Prix", 1, 3)


@pytest.mark.parametrize(
    "formula",
    [
        "=INDEX(Prix!$C:$C,MATCH(A2,Prix!$A:$A,0))",
        "=XLOOKUP(A2,Prix!A2:A9,Prix!C2:C9)",
    ],
)
def test_other_lookup_shapes_give_the_same_relation(formula: str) -> None:
    lookup = _translate(formula).lookups[0]
    assert (lookup.from_column, lookup.to_sheet, lookup.key_column, lookup.result_column) == (1, "Prix", 1, 3)


def test_a_lookup_into_another_file_isnt_a_relation() -> None:
    translation = _translate("=VLOOKUP(A2,'[1]May 2021'!$A:$C,3,FALSE)")
    assert translation.expr is None
    assert translation.lookups == []


def test_approximate_lookup_isnt_a_relation_or_a_translation() -> None:
    translation = _translate("=VLOOKUP(A2,Prix!$A:$C,3,TRUE)")
    assert translation.expr is None
    assert translation.lookups == []


def test_a_lookup_inside_an_engine_formula_is_still_evidence() -> None:
    translation = _translate('=TEXT(VLOOKUP(A2,Prix!$A:$C,3,FALSE),"0.00")')
    assert translation.expr is None
    assert translation.lookups[0].to_sheet == "Prix"


def test_expressions_meet_the_spec_schema() -> None:
    schema = load_schema()
    validator = Draft202012Validator(
        {"$ref": "#/$defs/expr", "$defs": schema["$defs"]},
    )
    for formula, _ in CASES:
        expr = _translate(formula).expr
        # `discriminator` is ours, so stock jsonschema checks every oneOf branch: that's stricter.
        errors = [error.message for error in validator.iter_errors(expr)]
        assert errors == [], formula


def test_function_support_is_probed() -> None:
    assert is_supported("SUM")
    assert is_supported("VLOOKUP")
    assert not is_supported("UNHEARDOF")


def test_parser_returns_plain_data() -> None:
    assert parse_formula("=A1+1")["node_type"] == "BinaryOp"


# --- Copied formulas ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("first", "second", "same"),
    [
        (("=C2*D2", 2, 5), ("=C3*D3", 3, 5), True),
        (("=C2*$F$1", 2, 5), ("=C3*$F$1", 3, 5), True),
        (("=SUM(B$2:B2)", 2, 3), ("=SUM(B$2:B3)", 3, 3), True),
        (("=C2*D2", 2, 5), ("=C3+D3", 3, 5), False),
        (("=C2*D2", 2, 5), ("=C2*D3", 3, 5), False),
        (('="C2"&C2', 2, 5), ('="C2"&C3', 3, 5), True),  # Text in a string isn't a reference.
        (("=Prix!A2", 2, 5), ("=Prix!A3", 3, 5), True),
        (("='Mes prix'!A2", 2, 5), ("='Mes prix'!A3", 3, 5), True),
    ],
)
def test_relative_form_groups_copies(first: tuple[str, int, int], second: tuple[str, int, int], same: bool) -> None:
    assert (relative_form(*first) == relative_form(*second)) is same


def _ledger(path: Path, excel: bool = True, broken_row: int | None = None, formula: str = "=C{r}-D{r}") -> Path:
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("Janvier")
    sheet.write_row("A1", ["N°", "Client", "Dû", "Payé", "Reste"], book.add_format({"bold": True}))
    for row in range(2, 8):
        sheet.write_number(f"A{row}", row)
        sheet.write_string(f"B{row}", f"Client {row}")
        sheet.write_number(f"C{row}", row * 100.5)
        sheet.write_number(f"D{row}", 50.25)
        if row == broken_row:
            sheet.write_number(f"E{row}", 1)
        else:
            value = row * 100.5 - 50.25
            sheet.write_formula(f"E{row}", formula.format(r=row), None, value)
    book.close()
    if excel:
        builders.as_saved_by_excel(path)
    return path


def _findings(path: Path, kind: str) -> list[dict[str, Any]]:
    return [item for item in analyze_snapshot(read_file(path))["findings"] if item["kind"] == kind]


def test_copied_column_becomes_a_verified_computed_field(tmp_path: Path) -> None:
    finding = _findings(_ledger(tmp_path / "l.xlsx"), "computedField")[0]
    proposal = finding["proposal"]
    assert finding["evidence"] == ["E2:E7"]
    assert proposal["eval"] == "translated"
    assert proposal["excel"] == "=C2-D2"
    assert proposal["deps"] == ["col_c", "col_d"]
    assert proposal["check"] == {"checked": 6, "agreed": 6}
    assert proposal["coverage"] == {"matching": 6, "total": 6}
    assert finding["confidence"]["level"] == "high"
    assert "=C2-D2" in finding["explanation"]["fr"] and "=C2-D2" in finding["explanation"]["ar"]


def test_a_translation_disagreeing_with_excel_goes_to_the_engine(tmp_path: Path) -> None:
    """The stored results say otherwise, so the translated expression can't be trusted."""
    path = tmp_path / "stale.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("S")
    sheet.write_row("A1", ["N°", "Reste"])
    for row in range(2, 8):
        sheet.write_number(f"A{row}", row)
        sheet.write_formula(f"B{row}", f"=A{row}*2", None, 999)
    book.close()
    builders.as_saved_by_excel(path)
    proposal = _findings(path, "computedField")[0]["proposal"]
    assert proposal["eval"] == "engine"
    assert "expr" not in proposal
    assert proposal["reasons"] == ["disagreesWithStoredResults"]
    assert proposal["check"] == {"checked": 6, "agreed": 0}


def test_results_not_from_excel_dont_judge_a_translation(tmp_path: Path) -> None:
    proposal = _findings(_ledger(tmp_path / "l.xlsx", excel=False), "computedField")[0]["proposal"]
    assert proposal["eval"] == "translated"
    assert proposal["check"] == {"checked": 0, "agreed": 0}


def test_a_function_outside_the_list_falls_back_and_is_reported(tmp_path: Path) -> None:
    path = _ledger(tmp_path / "l.xlsx", formula='=SUMIF(C$2:C$7,">0",D$2:D$7)+C{r}')
    finding = _findings(path, "computedField")[0]
    assert finding["proposal"]["eval"] == "engine"
    assert finding["proposal"]["functions"] == ["SUMIF"]
    assert finding["proposal"]["reasons"] == ["function:SUMIF"]
    assert finding["proposal"]["engineSupported"] is True


def test_a_function_the_engine_lacks_is_flagged_low_confidence(tmp_path: Path) -> None:
    finding = _findings(_ledger(tmp_path / "l.xlsx", formula="=MACROFONCTION(C{r})"), "computedField")[0]
    assert finding["proposal"]["engineSupported"] is False
    assert finding["proposal"]["missingFunctions"] == ["MACROFONCTION"]
    assert finding["confidence"]["level"] == "low"
    assert "MACROFONCTION" in finding["explanation"]["fr"]


def test_a_cell_breaking_the_column_formula_is_an_anomaly(tmp_path: Path) -> None:
    path = _ledger(tmp_path / "l.xlsx", broken_row=5)
    finding = _findings(path, "anomaly")[0]
    assert finding["evidence"] == ["E5"]
    assert finding["proposal"]["kind"] == "inconsistentFormula"
    assert _findings(path, "computedField")[0]["proposal"]["coverage"] == {"matching": 5, "total": 6}


def test_lookup_column_becomes_a_relation_finding(tmp_path: Path) -> None:
    path = tmp_path / "r.xlsx"
    book = xlsxwriter.Workbook(str(path))
    orders = book.add_worksheet("Commandes")
    orders.write_row("A1", ["Article", "Prix"], book.add_format({"bold": True}))
    for row in range(2, 8):
        orders.write_string(f"A{row}", f"A{row % 3}")
        orders.write_formula(f"B{row}", f"=VLOOKUP(A{row},Tarifs!$A$2:$B$4,2,FALSE)", None, 10)
    prices = book.add_worksheet("Tarifs")
    prices.write_row("A1", ["Code", "Prix"])
    for row in range(2, 5):
        prices.write_row(f"A{row}", [f"A{row - 2}", 10])
    book.close()
    analysis = analyze_snapshot(read_file(path))
    relation = next(item for item in analysis["findings"] if item["kind"] == "relation")
    assert relation["proposal"]["from"] == {"sheet": "Commandes", "column": "A"}
    assert relation["proposal"]["to"] == {"sheet": "Tarifs", "column": "A"}
    assert relation["proposal"]["evidence"] == "lookupFormula"
    assert relation["confidence"]["level"] == "high"
    computed = next(item for item in analysis["findings"] if item["kind"] == "computedField")
    assert computed["proposal"]["expr"]["kind"] == "related"


# --- Calculators --------------------------------------------------------------------------------


def _calculator(path: Path) -> Path:
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("Calcul")
    for row, (label, value) in enumerate([("Prix par matière", 3000), ("Nombre de matières", 2), ("Frères et sœurs", 1)], start=1):
        sheet.write_string(f"A{row}", label)
        sheet.write_number(f"B{row}", value)
    sheet.write_string("A4", "Sous-total")
    sheet.write_formula("B4", "=B1*B2", None, 6000)
    sheet.write_string("A5", "Remise")
    sheet.write_formula("B5", "=IF(B3>=1,0.05,0)*B4", None, 300)
    sheet.write_string("A6", "À payer")
    sheet.write_formula("B6", "=B4-B5", None, 5700)
    sheet.write_string("D1", "Note libre")  # Nothing reads it: it isn't an input.
    book.close()
    builders.as_saved_by_excel(path)
    return path


def test_calculator_inputs_outputs_and_test_case(tmp_path: Path) -> None:
    finding = _findings(_calculator(tmp_path / "c.xlsx"), "calculator")[0]
    proposal = finding["proposal"]
    assert [(item["cell"], item["name"], item["default"]) for item in proposal["inputs"]] == [
        ("B1", "Prix par matière", 3000),
        ("B2", "Nombre de matières", 2),
        ("B3", "Frères et sœurs", 1),
    ]
    assert [(item["cell"], item["name"]) for item in proposal["outputs"]] == [("B6", "À payer")]
    assert proposal["testCases"] == [
        {"inputs": {"input_b1": 3000, "input_b2": 2, "input_b3": 1}, "outputs": {"output_b6": 5700}}
    ]
    assert "Prix par matière" in finding["explanation"]["fr"]
    assert "À payer" in finding["explanation"]["ar"]


def test_calculator_reproduces_excel_in_the_engine(tmp_path: Path) -> None:
    proposal = _findings(_calculator(tmp_path / "c.xlsx"), "calculator")[0]["proposal"]
    def place(cell: dict[str, Any]) -> tuple[str, int, int]:
        column, row = coordinate_from_string(cell["ref"] if "ref" in cell else cell["cell"])
        return cell["sheet"], row, column_index_from_string(column)

    def run(inputs: dict[str, Any]) -> Any:
        by_cell = {item["cell"]: inputs[item["key"]] for item in proposal["inputs"]}
        cells = [
            (*place(cell), by_cell.get(cell["ref"], cell.get("v")), cell.get("f"))
            for cell in proposal["cells"]
        ]
        output = place(proposal["outputs"][0])
        return evaluate_cells(cells, [output])[0].value

    case = proposal["testCases"][0]
    assert run(case["inputs"]) == case["outputs"]["output_b6"]
    # And with new inputs, as the calculator screen will run it: 2500 * 3, with 5% off.
    assert run({"input_b1": 2500, "input_b2": 3, "input_b3": 1}) == 7125


def test_cells_read_by_a_formula() -> None:
    assert cells_read_by("=A1+B2", "S") == {("S", 1, 1), ("S", 2, 2)}
    assert cells_read_by("=SUM(A1:A3)", "S") == {("S", 1, 1), ("S", 2, 1), ("S", 3, 1)}
    assert cells_read_by("=Prix!A1+'Mes prix'!B2", "S") == {("Prix", 1, 1), ("Mes prix", 2, 2)}
    assert cells_read_by('="A1"&B1', "S") == {("S", 1, 2)}
    assert cells_read_by("=SUM(A:A)", "S") == set()


def test_no_calculator_without_inputs(tmp_path: Path) -> None:
    path = tmp_path / "n.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("N")
    sheet.write_formula("A1", "=1+1", None, 2)
    book.close()
    assert _findings(path, "calculator") == []


# --- Parity -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("result", "stored", "kind", "same"),
    [
        (EngineValue("number", 6.0), 6, "n", True),
        (EngineValue("number", 1.0 + 1e-10), 1.0, "n", True),
        (EngineValue("number", 1.0 + 1e-8), 1.0, "n", False),
        (EngineValue("number", 1e-16), 0, "n", False),  # R-19's tolerance is relative.
        (EngineValue("text", "a"), "a", "s", True),
        (EngineValue("text", "a"), "A", "s", False),
        (EngineValue("empty", None), None, "s", True),
        (EngineValue("text", ""), None, "s", True),
        (EngineValue("text", "  "), None, "s", True),  # Spaces read back as empty.
        (EngineValue("text", "x"), None, "s", False),
        (EngineValue("boolean", True), True, "b", True),
        (EngineValue("number", 1.0), True, "b", False),
        (EngineValue("error", "#DIV/0!"), "#DIV/0!", "e", True),
        (EngineValue("error", "#N/A"), "#DIV/0!", "e", False),
        (EngineValue("error", "#N/A"), 1, "n", False),
        (EngineValue("number", 1.0), "#N/A", "e", False),
        (EngineValue("date", datetime(2026, 1, 15)), "2026-01-15T00:00:00", "d", True),
        (EngineValue("number", 46037.0), "2026-01-15T00:00:00", "d", True),  # Number under a date format.
        (EngineValue("number", 46038.0), "2026-01-15T00:00:00", "d", False),
        (EngineValue("number", 0.0625), "01:30:00", "d", True),  # Times too.
        (EngineValue("date", datetime(2026, 1, 15)), 46037, "n", True),  # A date with a number format.
    ],
)
def test_values_match(result: EngineValue, stored: Any, kind: str, same: bool) -> None:
    assert values_match(result, stored, kind) is same


def test_parity_recomputes_and_catches_a_stale_result(tmp_path: Path) -> None:
    path = tmp_path / "s.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("F")
    sheet.write_number("A1", 5)
    sheet.write_formula("B1", "=A1+1", None, 6)  # Right.
    sheet.write_formula("B2", "=A1+2", None, 999)  # Stale: a real recomputation must disagree.
    sheet.write_formula("B3", '=IF(A1>1,"oui","non")', None, "oui")
    book.close()
    builders.as_saved_by_excel(path)
    report = run_parity(path, read_file(path))
    assert (report["cells"], report["equal"]) == (3, 2)
    assert report["causes"] == {"differentNumber": 1}
    assert {item["ref"]: item["value"] for item in report["results"]}["B2"] == 7.0


def test_parity_freezes_the_clock_at_the_last_save(tmp_path: Path) -> None:
    path = tmp_path / "t.xlsx"
    book = xlsxwriter.Workbook(str(path))
    book.set_properties({"created": datetime(2020, 3, 4, 12, 0)})
    dated = book.add_format({"num_format": "dd/mm/yyyy"})
    book.add_worksheet("T").write_formula("A1", "=TODAY()", dated, to_serial(datetime(2020, 3, 4)))
    book.close()
    builders.as_saved_by_excel(path)
    moment = last_saved(path, "xlsx")
    assert moment is not None and moment.date().isoformat() == "2020-03-04"
    report = run_parity(path, read_file(path))
    assert (report["cells"], report["equal"]) == (1, 1)


def test_random_and_now_cells_are_left_out_of_the_score(tmp_path: Path) -> None:
    path = tmp_path / "r.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("R")
    sheet.write_formula("A1", "=RAND()", None, 0.123)
    sheet.write_formula("A2", "=NOW()", None, 45000.123)
    sheet.write_formula("A3", "=1+1", None, 2)
    book.close()
    builders.as_saved_by_excel(path)
    report = run_parity(path, read_file(path))
    assert (report["cells"], report["equal"], report["uncheckable"]) == (1, 1, 2)


def test_parity_reports_by_category(tmp_path: Path) -> None:
    path = tmp_path / "c.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("C")
    sheet.write_number("A1", 2)
    sheet.write_formula("B1", "=SUM(A1,1)", None, 3)
    sheet.write_formula("B2", "=A1*2", None, 4)
    sheet.write_formula("B3", "=IF(A1>1,SUM(A1,1),0)", None, 99)  # Wrong on purpose.
    book.close()
    builders.as_saved_by_excel(path)
    report = run_parity(path, read_file(path))
    assert report["categories"] == {"math": 2, "operators": 1, "logical": 1}
    assert report["categoryEqual"] == {"math": 1, "operators": 1, "logical": 0}
    assert report["wrongFunctions"] == {"IF": 1, "SUM": 1}


def test_cli_parity_keeps_counts_only_and_skips_non_excel(tmp_path: Path) -> None:
    folder = tmp_path / "wb"
    folder.mkdir()
    excel = folder / "excel.xlsx"
    book = xlsxwriter.Workbook(str(excel))
    book.add_worksheet("A").write_formula("A1", '="SECRET-NAME"&"x"', None, "SECRET-NAMEx")
    book.close()
    builders.as_saved_by_excel(excel)
    other = folder / "library.xlsx"
    book = xlsxwriter.Workbook(str(other))
    book.add_worksheet("A").write_formula("A1", "=1+1", None, 2)
    book.close()
    (folder / "plain.csv").write_text("a;b\n1;2\n", encoding="utf-8")
    (folder / "broken.xlsx").write_bytes(b"nope")
    out = tmp_path / "out"
    assert main(["parity", str(folder), "-o", str(out)]) == 0
    text = (out / "parity.json").read_text(encoding="utf-8")
    assert "SECRET-NAME" not in text
    data = json.loads(text)
    assert data["aggregate"]["cells"] == 1
    assert data["aggregate"]["equal"] == 1
    assert data["skipped"] == {"notExcel": 1, "noFormulas": 1, "unreadable": 1}
    assert "| 100.00" in (out / "parity.md").read_text(encoding="utf-8") or "100.00%" in (out / "parity.md").read_text(encoding="utf-8")


@pytest.mark.libreoffice
def test_parity_runs_on_a_converted_xls(tmp_path: Path) -> None:
    path = builders.stale_xls(tmp_path / "stale.xls", 999.0)
    report = run_parity(path, read_file(path))
    # The stored 999 is the reference; the engine recalculates 6, so the stale cell is caught.
    assert (report["cells"], report["equal"]) == (1, 0)
    assert report["results"][0]["value"] == 6.0


def test_eval_scores_parity_with_the_engine(tmp_path: Path) -> None:
    root = tmp_path / "eval"
    (root / "workbooks").mkdir(parents=True)
    (root / "labels").mkdir()
    path = _ledger(root / "workbooks" / "wb.xlsx")
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / "manifest.csv").write_text(
        f"id,source,licence,language,stratum,split,consent,sha256\nwb,synthetic,CC0,fr,ledger,dev,n/a,{sha256}\n",
        encoding="utf-8",
    )
    snapshot = read_file(path)
    formulas = [
        {"sheet": "Janvier", "ref": cell["ref"], "f": cell["f"], "result": cell["v"], "t": cell["t"]}
        for cell in snapshot["sheets"][0]["cells"]
        if "f" in cell
    ]
    label = {
        "labelVersion": 1, "id": "wb", "workbookSha256": sha256, "status": "reviewed",
        "resultsFrom": "excel", "sheets": [{"name": "Janvier", "kind": "register", "regions": [], "tables": []}],
        "relations": [], "formulas": formulas,
    }  # fmt: skip
    (root / "labels" / "wb.json").write_text(json.dumps(label), encoding="utf-8")
    report = run_evaluation(root / "labels", root / "manifest.csv", "dev", None)
    assert report["parityNotRun"] == []
    assert report["overall"]["metrics"]["parity.share"]["value"] == 1.0
    assert report["overall"]["metrics"]["parity.category.operators.share"]["value"] == 1.0


def test_serial_dates_round_trip() -> None:
    for moment in (datetime(2026, 1, 15), datetime(1900, 3, 1), datetime(1999, 12, 31)):
        assert from_serial(to_serial(moment)) == moment
    assert to_serial(datetime(2026, 1, 15)) == 46037
    assert to_serial(datetime(1900, 3, 1)) == 61
    # Excel's leap-year bug: its 29 February 1900 is serial 60, so earlier dates sit one lower.
    assert to_serial(datetime(1900, 2, 28)) == 59
    assert from_serial(59) == datetime(1900, 2, 28)

