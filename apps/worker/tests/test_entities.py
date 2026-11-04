from collections import Counter
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import pytest
import workbook_builders as builders
import xlsxwriter

from daftar_worker import analyser
from daftar_worker.analyser import analyze_snapshot
from daftar_worker.analyser.entities import cluster_names
from daftar_worker.analyser.periods import Period, parse_period
from daftar_worker.evaluation.metrics import compute_metrics, score_workbook
from daftar_worker.evaluation.predictions import from_analysis
from daftar_worker.reader import read_file
from daftar_worker.sheet.names import fingerprint, same_with_initial, spelling_similarity, tokens


SCHEMA = json.loads(Path(analyser.__file__).with_name("analysis.schema.json").read_text(encoding="utf-8"))


def by_kind(analysis: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [item for item in analysis["findings"] if item["kind"] == kind]


def analyse(path: Path) -> dict[str, Any]:
    analysis = analyze_snapshot(read_file(path))
    assert [error.message for error in Draft202012Validator(SCHEMA).iter_errors(analysis)] == []
    return analysis


# --- Names --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Benali Ahmed", "ahmed BENALI"),
        ("Élodie Hamdi", "elodie hamdi"),
        ("M. Benali", "Benali"),
        ("Mme Saidi", "SAIDI"),
        ("أحمد", "احمد"),
        ("فاطمة", "فاطمه"),
        ("مصطفى", "مصطفي"),
        ("السيد كريم", "كريم"),
        ("Sarl Atlas", "ATLAS"),
        ("3li", "ali"),
        ("7assan", "hassan"),
        ("Ben-Ali", "Ben Ali"),
    ],
)
def test_spellings_that_share_a_fingerprint(left: str, right: str) -> None:
    assert fingerprint(left) == fingerprint(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [("Client 1", "Client 2"), ("Ahmed", "Ali"), ("client2", "client3"), ("Lot 2026", "Lot 2025")],
)
def test_different_names_stay_different(left: str, right: str) -> None:
    assert fingerprint(left) != fingerprint(right)


def test_a_trailing_number_isnt_arabizi() -> None:
    assert tokens("client2") == ["client2"]
    assert tokens("2026") == ["2026"]


def test_a_name_that_is_only_a_title_is_kept() -> None:
    assert tokens("Madame") == ["madame"]


def test_initials() -> None:
    assert same_with_initial(["a", "benali"], ["ahmed", "benali"])
    assert not same_with_initial(["b", "benali"], ["ahmed", "benali"])
    assert not same_with_initial(["ahmed", "benali"], ["ahmed", "saidi"])
    assert not same_with_initial(["a"], ["ahmed"])


def test_clusters_list_every_spelling_with_counts() -> None:
    clusters = cluster_names(Counter({"M. Benali": 5, "Mr Benali": 3, "BENALI": 2, "Saidi": 7, "Hamdi": 1}))
    assert len(clusters) == 1
    assert clusters[0]["canonical"] == "M. Benali"
    assert clusters[0]["variants"] == [
        {"value": "M. Benali", "count": 5},
        {"value": "Mr Benali", "count": 3},
        {"value": "BENALI", "count": 2},
    ]
    assert clusters[0]["match"] == "normalised"


def test_typos_cluster_as_close_and_initials_as_possible() -> None:
    assert cluster_names(Counter({"Mohamed Benali": 3, "Mohammed Benali": 2}))[0]["match"] == "close"
    assert cluster_names(Counter({"A. Benali": 3, "Ahmed Benali": 2}))[0]["match"] == "possible"


@pytest.mark.parametrize(
    "names",
    [
        {"Client 1": 2, "Client 2": 2, "Client 3": 2},  # Numbers tell them apart.
        {"Ali": 3, "Ala": 3},  # Too short to judge by spelling.
        {"Ahmed Benali": 2, "Karim Saidi": 2},
    ],
)
def test_near_names_arent_clustered_without_cause(names: dict[str, int]) -> None:
    assert cluster_names(Counter(names)) == []


# --- Periods ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("Janvier", "--01"),
        ("janvier 2026", "2026-01"),
        ("Février 26", "2026-02"),
        ("FEV 2025", "2025-02"),
        ("Août", "--08"),
        ("جانفي", "--01"),
        ("فيفري 2026", "2026-02"),
        ("أفريل", "--04"),
        ("جويلية", "--07"),
        ("يناير", "--01"),
        ("March", "--03"),
        ("2026-01", "2026-01"),
        ("01-2026", "2026-01"),
        ("2026_12", "2026-12"),
        ("Paiements Mars", "--03"),
        ("T1 2025", "2025-Q1"),
        ("Q3", "--Q3"),
        ("2e trimestre 2024", "2024-Q2"),
        ("2024", "2024"),
    ],
)
def test_parse_period(name: str, text: str) -> None:
    period = parse_period(name)
    assert period is not None
    assert period.text == text


@pytest.mark.parametrize("name", ["Clients", "Feuil1", "Marseille", "Maison", "Stock 2024 du magasin central", "Sheet1", "Décembrement"])
def test_not_a_period(name: str) -> None:
    assert parse_period(name) is None


def test_periods_order_by_year_then_number() -> None:
    assert Period("month", 2025, 12).order < Period("month", 2026, 1).order


# --- The blueprint's tutoring-centre workbook ---------------------------------------------------


def tutoring(path: Path) -> Path:
    book = xlsxwriter.Workbook(str(path))
    bold = book.add_format({"bold": True})
    money = book.add_format({"num_format": '#,##0 "DA"'})
    red = book.add_format({"bg_color": "#FF0000"})
    green = book.add_format({"bg_color": "#00FF00"})
    parents = ["M. Benali", "Mr Benali", "BENALI", "Mme Saidi", "SAIDI", "Hamdi Karim", "Karim Hamdi", "Kaci Omar"]
    register = book.add_worksheet("Élèves")
    register.write_row("A1", ["Matricule", "Élève", "Parent", "Téléphone parent"], bold)
    phones = {"benali": "0550123456", "saidi": "0661234567", "hamdi karim": "0771234567", "kaci omar": "0552222222"}
    for index in range(16):
        parent = parents[index % len(parents)]
        key = "benali" if "enali" in parent.lower() else ("saidi" if "aidi" in parent.lower() else ("kaci omar" if "aci" in parent else "hamdi karim"))
        register.write_row(1 + index, 0, [f"E{index:03d}", f"Élève {index}", parent, phones[key]])
    for tab in ("Janvier 2026", "Février 2026", "Mars 2026"):
        sheet = book.add_worksheet(tab)
        sheet.merge_range("A1:D1", f"Paiements {tab}", bold)
        sheet.write_row("A3", ["Matricule", "Montant", "Statut", "Date"], bold)
        for index in range(12):
            sheet.write_string(3 + index, 0, f"E{index:03d}")
            sheet.write_number(3 + index, 1, 3000 + index * 100, money)
            sheet.write_string(3 + index, 2, ["Payé", "Impayé"][index % 2])
        sheet.conditional_format("C4:C15", {"type": "cell", "criteria": "==", "value": '"Impayé"', "format": red})
        sheet.conditional_format("C4:C15", {"type": "cell", "criteria": "==", "value": '"Payé"', "format": green})
        sheet.write_string(15, 0, "TOTAL", bold)
        sheet.write_formula(15, 1, "=SUM(B4:B15)", money, 42600)
    book.close()
    builders.as_saved_by_excel(path)
    return path


def test_retyped_parents_are_proposed_never_merged(tmp_path: Path) -> None:
    analysis = analyse(tutoring(tmp_path / "t.xlsx"))
    finding = next(item for item in by_kind(analysis, "entityMerge") if item["proposal"]["name"] == "Parent")
    assert finding["decision"] == {"status": "pending"}
    spellings = [{item["value"] for item in cluster["variants"]} for cluster in finding["proposal"]["clusters"]]
    assert {"M. Benali", "Mr Benali", "BENALI"} in spellings
    assert {"Mme Saidi", "SAIDI"} in spellings
    assert {"Hamdi Karim", "Karim Hamdi"} in spellings
    sample = finding["proposal"]["clusters"][0]["variants"][0]["value"]
    assert sample in finding["explanation"]["fr"] and sample in finding["explanation"]["ar"]


def test_a_retyped_name_finds_what_it_determines(tmp_path: Path) -> None:
    analysis = analyse(tutoring(tmp_path / "t.xlsx"))
    finding = next(item for item in by_kind(analysis, "entityMerge") if item["proposal"]["name"] == "Parent")
    assert finding["proposal"]["attributes"] == [{"column": "D", "name": "Téléphone parent"}]


def test_monthly_tabs_are_one_entity_with_a_period(tmp_path: Path) -> None:
    finding = by_kind(analyse(tutoring(tmp_path / "t.xlsx")), "periodUnion")[0]
    assert [(tab["sheet"], tab["period"], tab["table"]) for tab in finding["proposal"]["tabs"]] == [
        ("Janvier 2026", "2026-01", "A3:D16"),
        ("Février 2026", "2026-02", "A3:D16"),
        ("Mars 2026", "2026-03", "A3:D16"),
    ]
    assert finding["proposal"]["granularity"] == "month"
    assert finding["confidence"]["level"] == "high"


def test_each_tab_reads_as_a_ledger_with_a_status(tmp_path: Path) -> None:
    analysis = analyse(tutoring(tmp_path / "t.xlsx"))
    outcomes = {sheet["name"]: sheet["outcome"] for sheet in analysis["sheets"]}
    assert outcomes["Janvier 2026"] == "ledger"
    assert outcomes["Élèves"] == "register"


def test_conditional_format_becomes_coloured_choices(tmp_path: Path) -> None:
    finding = by_kind(analyse(tutoring(tmp_path / "t.xlsx")), "statusColours")[0]
    assert finding["proposal"]["source"] == "conditionalFormat"
    assert finding["proposal"]["choices"] == [
        {"value": "Impayé", "colour": "#FF0000", "count": 6},
        {"value": "Payé", "colour": "#00FF00", "count": 6},
    ]
    assert finding["confidence"]["level"] == "high"


def test_key_inclusion_gives_a_medium_relation(tmp_path: Path) -> None:
    analysis = analyse(tutoring(tmp_path / "t.xlsx"))
    relations = {
        (item["proposal"]["from"]["sheet"], item["proposal"]["from"]["column"]): item
        for item in by_kind(analysis, "relation")
    }
    relation = relations[("Janvier 2026", "A")]
    assert relation["proposal"]["to"] == {"sheet": "Élèves", "column": "A"}
    assert relation["proposal"]["evidence"] == "keyInclusion"
    assert relation["confidence"]["level"] == "medium"
    assert relation["confidence"]["score"] <= 0.84


def test_scorer_reports_relations_and_monthly_tabs(tmp_path: Path) -> None:
    analysis = analyse(tutoring(tmp_path / "t.xlsx"))
    label = {
        "resultsFrom": "none",
        "formulas": [],
        "relations": [{"from": {"sheet": "Janvier 2026", "column": "A"}, "to": {"sheet": "Élèves", "column": "A"}}],
        "sheets": [
            {"name": "Élèves", "kind": "register", "regions": [], "tables": []},
            {"name": "Janvier 2026", "kind": "ledger", "periodGroup": "paie", "regions": [], "tables": []},
            {"name": "Février 2026", "kind": "ledger", "periodGroup": "paie", "regions": [], "tables": []},
            {"name": "Mars 2026", "kind": "ledger", "regions": [], "tables": []},
        ],
    }
    metrics = compute_metrics([score_workbook("t", "ledger", label, from_analysis(analysis))])
    # Gold has one pair of tabs; the analyser proposes three pairs, one of them right.
    assert metrics["periodTabs.precision"] == pytest.approx(1 / 3)
    assert metrics["periodTabs.recall"] == 1.0
    # Gold has one relation, found; the Février and Mars links are extra.
    assert metrics["relations.recall"] == 1.0
    assert metrics["relations.precision"] == pytest.approx(1 / 3)


# --- Rules on their own -------------------------------------------------------------------------


def _two_sheets(path: Path, left: list[Any], right: list[Any], left_head: str = "Code", right_head: str = "Code") -> Path:
    book = xlsxwriter.Workbook(str(path))
    bold = book.add_format({"bold": True})
    first = book.add_worksheet("Ventes")
    first.write_row("A1", [left_head, "Qté"], bold)
    for index, value in enumerate(left):
        first.write(1 + index, 0, value)
        first.write_number(1 + index, 1, index + 0.5)
    second = book.add_worksheet("Articles")
    second.write_row("A1", [right_head, "Libellé"], bold)
    for index, value in enumerate(right):
        second.write(1 + index, 0, value)
        second.write_string(1 + index, 1, f"Libellé {index}")
    book.close()
    return path


CODES = ["AX1", "BX2", "CX3", "DX4", "EX5"]


def test_inclusion_needs_a_unique_key_on_the_other_side(tmp_path: Path) -> None:
    path = _two_sheets(tmp_path / "a.xlsx", CODES * 2, CODES * 2)
    assert by_kind(analyse(path), "relation") == []


def test_inclusion_tolerates_a_stray_value_but_not_many(tmp_path: Path) -> None:
    many = [f"K{index}" for index in range(40)]
    one_stray = analyse(_two_sheets(tmp_path / "a.xlsx", [*many[:30], "ZZZ"], many))
    assert len(by_kind(one_stray, "relation")) == 1
    several = analyse(_two_sheets(tmp_path / "b.xlsx", [*many[:5], "Y1", "Y2", "Y3"], many))
    assert by_kind(several, "relation") == []


def test_a_counter_doesnt_link_to_another_counter(tmp_path: Path) -> None:
    numbers = list(range(1, 9))
    path = _two_sheets(tmp_path / "a.xlsx", numbers[:5], numbers, "Rang", "Ligne")
    assert by_kind(analyse(path), "relation") == []


def test_a_numeric_id_with_a_name_can_link(tmp_path: Path) -> None:
    ids = [1001, 1002, 1003, 1005, 1008]
    path = _two_sheets(tmp_path / "a.xlsx", ids * 2, ids, "Code client", "Code client")
    relation = by_kind(analyse(path), "relation")[0]
    assert relation["proposal"]["from"] == {"sheet": "Ventes", "column": "A"}


def test_tabs_of_one_series_never_relate_to_each_other(tmp_path: Path) -> None:
    analysis = analyse(tutoring(tmp_path / "t.xlsx"))
    tabs = {"Janvier 2026", "Février 2026", "Mars 2026"}
    for relation in by_kind(analysis, "relation"):
        assert relation["proposal"]["to"]["sheet"] not in tabs


def test_relations_form_no_loop(tmp_path: Path) -> None:
    # Both columns are unique over the same values, so each could point at the other.
    path = _two_sheets(tmp_path / "a.xlsx", CODES, CODES, "Code", "Réf")
    assert len(by_kind(analyse(path), "relation")) == 1


def test_a_copy_of_a_table_isnt_a_relation(tmp_path: Path) -> None:
    path = tmp_path / "c.xlsx"
    book = xlsxwriter.Workbook(str(path))
    for tab in ("Résultat obtenu", "Résultat attendu"):
        sheet = book.add_worksheet(tab)
        sheet.write_row("A1", ["Code", "Qté"], book.add_format({"bold": True}))
        for index, code in enumerate(CODES):
            sheet.write_row(1 + index, 0, [code, index + 0.5])
    book.close()
    assert by_kind(analyse(path), "relation") == []


def test_a_few_shared_values_under_different_names_arent_a_relation(tmp_path: Path) -> None:
    path = _two_sheets(tmp_path / "a.xlsx", CODES[:3], CODES, "Couleur", "Réf")
    assert by_kind(analyse(path), "relation") == []


def test_values_shared_with_a_column_that_cant_be_a_key_arent_a_relation(tmp_path: Path) -> None:
    path = tmp_path / "n.xlsx"
    book = xlsxwriter.Workbook(str(path))
    first = book.add_worksheet("Ventes")
    first.write_row("A1", ["Rang", "Marque"], book.add_format({"bold": True}))
    second = book.add_worksheet("Divers")
    second.write_row("A1", ["N°", "Couleur"], book.add_format({"bold": True}))
    for index, code in enumerate(CODES):
        first.write_row(1 + index, 0, [index + 200, code])
        second.write_row(1 + index, 0, [index + 100, code])
    book.close()
    assert by_kind(analyse(path), "relation") == []


def test_similar_email_addresses_arent_one_name(tmp_path: Path) -> None:
    path = tmp_path / "m.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("M")
    sheet.write_row("A1", ["N°", "Contact"], book.add_format({"bold": True}))
    for row, name in enumerate(["head@willows.dz", "head@walton.dz", "head@waltonlane.dz", "head@wilton.dz", "head@willows.dz"], start=2):
        sheet.write_row(f"A{row}", [row, name])
    book.close()
    assert by_kind(analyse(path), "entityMerge") == []


def test_a_column_that_moves_with_another_isnt_an_entity_by_itself(tmp_path: Path) -> None:
    path = tmp_path / "e.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("E")
    sheet.write_row("A1", ["Mercredi", "Jeudi"], book.add_format({"bold": True}))
    for row in range(2, 8):
        sheet.write_row(f"A{row}", ["Oui" if row % 2 else "Peut-être", "Ali" if row % 2 else "Omar"])
    book.close()
    assert by_kind(analyse(path), "entityMerge") == []


def test_validation_list_from_another_sheet_is_a_high_relation(tmp_path: Path) -> None:
    path = tmp_path / "v.xlsx"
    book = xlsxwriter.Workbook(str(path))
    orders = book.add_worksheet("Commandes")
    orders.write_row("A1", ["Commande", "Wilaya"], book.add_format({"bold": True}))
    for row in range(2, 8):
        orders.write_row(f"A{row}", [f"C{row}", "Alger"])
    orders.data_validation("B2:B7", {"validate": "list", "source": "=Wilayas!$A$2:$A$4"})
    lookup = book.add_worksheet("Wilayas")
    lookup.write_column("A1", ["Wilaya", "Alger", "Oran", "Blida"])
    book.close()
    relation = by_kind(analyse(path), "relation")[0]
    assert relation["proposal"]["evidence"] == "validationList"
    assert relation["proposal"]["to"] == {"sheet": "Wilayas", "column": "A"}
    assert relation["confidence"]["level"] == "high"


def _status_sheet(path: Path, fills: dict[str, str | None], header: str = "État") -> Path:
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("S")
    sheet.write_row("A1", ["N°", header], book.add_format({"bold": True}))
    formats = {colour: book.add_format({"bg_color": colour}) for colour in set(fills.values()) if colour}
    values = list(fills.items())
    for row in range(2, 14):
        value, colour = values[row % len(values)]
        sheet.write_number(f"A{row}", row)
        if value:
            sheet.write_string(f"B{row}", value, formats[colour] if colour else None)
        elif colour:
            sheet.write_blank(f"B{row}", None, formats[colour])
    book.close()
    return path


def test_fill_colours_on_a_status_become_choices(tmp_path: Path) -> None:
    path = _status_sheet(tmp_path / "s.xlsx", {"En cours": "#FFFF00", "Fini": "#00FF00"})
    finding = by_kind(analyse(path), "statusColours")[0]
    assert finding["proposal"]["source"] == "fill"
    assert {item["value"]: item["colour"] for item in finding["proposal"]["choices"]} == {
        "En cours": "#FFFF00",
        "Fini": "#00FF00",
    }
    assert finding["confidence"]["level"] == "medium"


def test_one_colour_across_a_column_is_decoration(tmp_path: Path) -> None:
    path = _status_sheet(tmp_path / "s.xlsx", {"En cours": "#FFFF00", "Fini": "#FFFF00"})
    assert by_kind(analyse(path), "statusColours") == []


def test_white_and_black_fills_arent_states(tmp_path: Path) -> None:
    path = _status_sheet(tmp_path / "s.xlsx", {"En cours": "#FFFFFF", "Fini": "#000000"})
    assert by_kind(analyse(path), "statusColours") == []


def test_a_single_highlight_is_a_status_only_if_the_title_says_so(tmp_path: Path) -> None:
    def build(path: Path, header: str) -> Path:
        book = xlsxwriter.Workbook(str(path))
        sheet = book.add_worksheet("S")
        sheet.write_row("A1", ["N°", header], book.add_format({"bold": True}))
        for row in range(2, 14):
            sheet.write_number(f"A{row}", row)
            sheet.write_string(f"B{row}", ["N/A", "Oui"][row % 2])
        sheet.conditional_format("B2:B13", {"type": "cell", "criteria": "==", "value": '"N/A"', "format": book.add_format({"bg_color": "#FF0000"})})
        book.close()
        return path

    assert by_kind(analyse(build(tmp_path / "a.xlsx", "Remarque")), "statusColours") == []
    assert len(by_kind(analyse(build(tmp_path / "b.xlsx", "Statut")), "statusColours")) == 1


def test_colour_with_no_text_is_asked_about_at_low_confidence(tmp_path: Path) -> None:
    path = tmp_path / "s.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("S")
    sheet.write_row("A1", ["N°", "Priorité"])
    red, green = book.add_format({"bg_color": "#FF0000"}), book.add_format({"bg_color": "#00FF00"})
    for row in range(2, 14):
        sheet.write_number(f"A{row}", row)
        sheet.write_blank(f"B{row}", None, red if row % 2 else green)
    book.close()
    finding = by_kind(analyse(path), "statusColours")[0]
    assert finding["confidence"]["level"] == "low"
    assert {item["colour"] for item in finding["proposal"]["choices"]} == {"#FF0000", "#00FF00"}
    assert "couleurs sans texte" in finding["explanation"]["fr"]


def test_a_coloured_status_makes_a_tracker(tmp_path: Path) -> None:
    path = tmp_path / "t.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("Atelier")
    sheet.write_row("A1", ["Appareil", "Note"], book.add_format({"bold": True}))
    yellow, green = book.add_format({"bg_color": "#FFFF00"}), book.add_format({"bg_color": "#00FF00"})
    for row in range(2, 14):
        sheet.write_string(f"A{row}", f"Téléphone {row}")
        sheet.write_string(f"B{row}", ["En cours", "Fini"][row % 2], [yellow, green][row % 2])
    book.close()
    assert analyse(path)["sheets"][0]["outcome"] == "tracker"


def test_tabs_with_other_columns_stay_apart(tmp_path: Path) -> None:
    path = tmp_path / "t.xlsx"
    book = xlsxwriter.Workbook(str(path))
    for tab, heads in (("Janvier", ["Client", "Montant"]), ("Février", ["Client", "Montant"]), ("Mars", ["Produit", "Stock", "Fournisseur", "Ville"])):
        sheet = book.add_worksheet(tab)
        sheet.write_row("A1", heads, book.add_format({"bold": True}))
        for row in range(2, 7):
            sheet.write_row(f"A{row}", [f"V{row}"] + [row * 1.5] * (len(heads) - 1))
    book.close()
    tabs = [tab["sheet"] for tab in by_kind(analyse(path), "periodUnion")[0]["proposal"]["tabs"]]
    assert tabs == ["Janvier", "Février"]


def test_one_period_tab_alone_isnt_a_union(tmp_path: Path) -> None:
    path = tmp_path / "t.xlsx"
    book = xlsxwriter.Workbook(str(path))
    for tab in ("Janvier", "Clients"):
        sheet = book.add_worksheet(tab)
        sheet.write_row("A1", ["Client", "Montant"], book.add_format({"bold": True}))
        for row in range(2, 7):
            sheet.write_row(f"A{row}", [f"V{row}", row * 1.5])
    book.close()
    assert by_kind(analyse(path), "periodUnion") == []


def test_analysis_stays_identical_across_runs(tmp_path: Path) -> None:
    path = tutoring(tmp_path / "t.xlsx")
    snapshot = read_file(path)
    assert json.dumps(analyze_snapshot(snapshot)) == json.dumps(analyze_snapshot(snapshot))


def _book_of(path: Path, first: dict[str, list[list[Any]]]) -> Path:
    book = xlsxwriter.Workbook(str(path))
    for name, rows in first.items():
        sheet = book.add_worksheet(name)
        for row_number, row in enumerate(rows):
            for column, value in enumerate(row):
                if isinstance(value, str) and value.startswith("="):
                    sheet.write_formula(row_number, column, value, None, 1)
                elif value is not None:
                    sheet.write(row_number, column, value)
    book.close()
    return path


def _relations(path: Path) -> dict[tuple[str, str, str, str], str]:
    found = {}
    for item in by_kind(analyze_snapshot(read_file(path)), "relation"):
        proposal = item["proposal"]
        key = (proposal["from"]["sheet"], proposal["from"]["column"], proposal["to"]["sheet"], proposal["to"]["column"])
        found[key] = proposal["evidence"]
    return found


def test_sumifs_ties_the_rows_it_adds_to_the_sheet_holding_it(tmp_path: Path) -> None:
    path = _book_of(tmp_path / "s.xlsx", {
        "Commandes": [
            ["Commande", "Article", "Reçu"],
            ["C1", "Vis", "=SUMIFS(Lignes!C:C,Lignes!A:A,A2,Lignes!B:B,B2)"],
            ["C1", "Clou", "=SUMIFS(Lignes!C:C,Lignes!A:A,A3,Lignes!B:B,B3)"],
            ["C2", "Vis", "=SUMIFS(Lignes!C:C,Lignes!A:A,A4,Lignes!B:B,B4)"],
        ],
        "Lignes": [["Commande", "Article", "Qté"], ["C1", "Vis", 2.5], ["C1", "Clou", 3.5], ["C2", "Vis", 1.5]],
    })  # fmt: skip
    relations = _relations(path)
    assert relations[("Lignes", "A", "Commandes", "A")] == "aggregateFormula"
    assert relations[("Lignes", "B", "Commandes", "B")] == "aggregateFormula"


def test_retyped_names_link_when_the_column_names_the_sheet(tmp_path: Path) -> None:
    path = _book_of(tmp_path / "n.xlsx", {
        "Suivi": [
            ["Dossier", "Client", "Montant"],
            ["D1", "Abdelkader Benali", 10.5],
            ["D2", "Samia Hamdi", 20.5],
            ["D3", "Abdelkader Benalli", 30.5],
            ["D4", "Rachid Zerrouki", 40.5],
            ["D5", "Cafe Palmier", 50.5],
        ],
        "Clients": [
            ["Code", "Nom", "Ville"],
            ["Z1", "Abdelkader Benali", "Blida"],
            ["Z2", "Samia Hamdi", "Oran"],
            ["Z3", "Rachid Zerrouki", "Alger"],
            ["Z4", "Cafe Palmier", "Tizi"],
            ["Z5", "Nora Saidi", "Bejaia"],
        ],
    })  # fmt: skip
    assert _relations(path)[("Suivi", "B", "Clients", "B")] == "keyInclusion"


def test_names_that_merely_look_alike_dont_link(tmp_path: Path) -> None:
    path = _book_of(tmp_path / "x.xlsx", {
        "Suivi": [
            ["Dossier", "Client", "Montant"],
            ["D1", "Karim Bensalah", 10.5],
            ["D2", "Lina Mansouri", 20.5],
            ["D3", "Yacine Toumi", 30.5],
            ["D4", "Meriem Haddad", 40.5],
            ["D5", "Sofiane Rahal", 50.5],
        ],
        "Clients": [
            ["Code", "Nom"],
            ["Z1", "Abdelkader Benali"],
            ["Z2", "Samia Hamdi"],
            ["Z3", "Rachid Zerrouki"],
            ["Z4", "Cafe Palmier"],
            ["Z5", "Nora Saidi"],
        ],
    })  # fmt: skip
    assert ("Suivi", "B", "Clients", "B") not in _relations(path)


def test_a_name_with_words_left_out_counts_as_the_same_spelling() -> None:
    assert spelling_similarity(fingerprint("Ecole Al Amal"), fingerprint("Ecole Al Amal Privee")) == 100
    assert spelling_similarity(fingerprint("Karim"), fingerprint("Karim Bensalah")) < 88
