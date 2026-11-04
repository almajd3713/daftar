"""Synthetic workbooks whose right answers are known because this code wrote them.

A regression suite, not a measure of accuracy: the rules were written alongside these files. The
real measure is the labelled dev pool (WP-4).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import xlsxwriter


@dataclass
class Case:
    id: str
    stratum: str
    language: str
    build: Callable[[Path], None]
    sheets: list[dict[str, Any]]
    relations: list[dict[str, Any]]


def _field(column: str, name: str, kind: str) -> dict[str, str]:
    return {"column": column, "name": name, "type": kind}


def _sheet(name: str, kind: str, tables: list[dict[str, Any]] | None = None, reason: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": name, "kind": kind, "regions": [], "tables": tables or []}
    if reason:
        entry["reason"] = reason
    return entry


def _table(cell_range: str, headers: list[int], fields: list[dict[str, str]], totals: list[int] | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"range": cell_range, "headerRows": headers, "fields": fields}
    if totals:
        entry["totalRows"] = totals
    return entry


NAMES = ["Amina Benali", "Karim Saidi", "Sara Hamdi", "Omar Kaci", "Lina Brahimi", "Yacine Toumi",
         "Nadia Meziane", "Sofiane Ait", "Rania Khelifi", "Walid Cherif", "Imane Larbi", "Hakim Bouzid"]  # fmt: skip
PHONES = ["0550123456", "0661234567", "0771234567", "+213550987654", "0555 12 34 56", "0662111222",
          "0773334444", "0551222333", "0664555666", "0775666777", "0552888999", "0669000111"]  # fmt: skip


def _book(path: Path, write: Callable[[Any], None]) -> None:
    book = xlsxwriter.Workbook(str(path))
    write(book)
    book.close()


def register_with_title(path: Path) -> None:
    def write(book: Any) -> None:
        sheet = book.add_worksheet("Élèves")
        bold = book.add_format({"bold": True, "bg_color": "#DDDDDD"})
        dated = book.add_format({"num_format": "dd/mm/yyyy"})
        sheet.write("A1", "Centre El Nadjah : liste des élèves 2026", book.add_format({"bold": True}))
        sheet.write("A2", "Mise à jour chaque semaine")
        sheet.write_row("A4", ["N°", "Nom", "Téléphone", "Naissance", "Email", "Moyenne"], bold)
        for index, name in enumerate(NAMES):
            row = 4 + index
            sheet.write_number(row, 0, index + 1)
            sheet.write_string(row, 1, name)
            sheet.write_string(row, 2, PHONES[index])
            sheet.write_datetime(row, 3, datetime(2010, 1 + index % 12, 5 + index), dated)
            sheet.write_string(row, 4, f"eleve{index}@exemple.dz")
            sheet.write_number(row, 5, 10.5 + index)

    _book(path, write)


def ledger_with_totals(path: Path) -> None:
    def write(book: Any) -> None:
        sheet = book.add_worksheet("Janvier")
        bold = book.add_format({"bold": True})
        money = book.add_format({"num_format": '#,##0.00 "DA"'})
        dated = book.add_format({"num_format": "dd/mm/yyyy"})
        sheet.write_row("A1", ["Date", "Client", "Montant", "Payé", "Reste"], bold)
        for index in range(10):
            row = 1 + index
            sheet.write_datetime(row, 0, datetime(2026, 1, 1 + index), dated)
            sheet.write_string(row, 1, NAMES[index])
            sheet.write_number(row, 2, 1000 + index * 100, money)
            sheet.write_number(row, 3, 500, money)
            sheet.write_formula(row, 4, f"=C{row + 1}-D{row + 1}", money, 500 + index * 100)
        sheet.write_string(11, 1, "Total", bold)
        sheet.write_formula(11, 2, "=SUM(C2:C11)", money, 14500)
        sheet.write_formula(11, 3, "=SUM(D2:D11)", money, 5000)
        sheet.write_formula(11, 4, "=SUM(E2:E11)", money, 9500)

    _book(path, write)


def two_tables_side_by_side(path: Path) -> None:
    def write(book: Any) -> None:
        sheet = book.add_worksheet("Stock")
        bold = book.add_format({"bold": True})
        sheet.merge_range("A1:G1", "Inventaire du magasin", bold)
        sheet.write_row("A3", ["Article", "Quantité"], bold)
        sheet.write_row("D3", ["Fournisseur", "Téléphone", "Ville"], bold)
        for index in range(8):
            sheet.write_string(3 + index, 0, f"Article {index}")
            sheet.write_number(3 + index, 1, index * 3)
        for index in range(6):
            sheet.write_row(3 + index, 3, [f"Fournisseur {index}", PHONES[index], f"Ville {index}"])

    _book(path, write)


def two_tables_stacked(path: Path) -> None:
    def write(book: Any) -> None:
        sheet = book.add_worksheet("Atelier")
        bold = book.add_format({"bold": True})
        sheet.write_row("A1", ["Pièce", "Prix"], bold)
        for index in range(5):
            sheet.write_string(1 + index, 0, f"Pièce {index}")
            sheet.write_number(1 + index, 1, 100.5 * (index + 1))
        sheet.write_row("A9", ["Employé", "Téléphone"], bold)
        for index in range(4):
            sheet.write_string(9 + index, 0, NAMES[index])
            sheet.write_string(9 + index, 1, PHONES[index])

    _book(path, write)


def merged_two_row_header(path: Path) -> None:
    def write(book: Any) -> None:
        sheet = book.add_worksheet("Ventes")
        bold = book.add_format({"bold": True, "bg_color": "#CCE5FF"})
        sheet.merge_range("A1:A2", "Produit", bold)
        sheet.merge_range("B1:C1", "Janvier", bold)
        sheet.merge_range("D1:E1", "Février", bold)
        sheet.write_row("B2", ["Quantité", "Valeur", "Quantité", "Valeur"], bold)
        for index in range(8):
            sheet.write_string(2 + index, 0, f"Produit {index}")
            sheet.write_row(2 + index, 1, [index, index * 10.5, index + 1, index * 11.5])

    _book(path, write)


def arabic_register(path: Path) -> None:
    def write(book: Any) -> None:
        sheet = book.add_worksheet("الزبائن")
        sheet.right_to_left()
        bold = book.add_format({"bold": True})
        sheet.write_row("A1", ["الاسم", "الهاتف", "الرصيد"], bold)
        names = ["أمينة", "كريم", "سارة", "عمر", "لينة", "ياسين", "نادية", "سفيان"]
        for index, name in enumerate(names):
            sheet.write_string(1 + index, 0, name)
            sheet.write_string(1 + index, 1, PHONES[index])
            sheet.write_number(1 + index, 2, 1500.5 * index)
        sheet.write_string(9, 0, "المجموع", bold)
        sheet.write_number(9, 2, 1500.5 * 28, bold)

    _book(path, write)


def tracker_with_list(path: Path) -> None:
    def write(book: Any) -> None:
        sheet = book.add_worksheet("Réparations")
        bold = book.add_format({"bold": True})
        dated = book.add_format({"num_format": "dd/mm/yyyy"})
        sheet.write_row("A1", ["Appareil", "Client", "Technicien", "Reçu le", "État"], bold)
        statuses = ["Reçu", "En cours", "Prêt", "Livré"]
        for index in range(12):
            row = 1 + index
            sheet.write_string(row, 0, f"Téléphone {index}")
            sheet.write_string(row, 1, NAMES[index])
            sheet.write_string(row, 2, ["Ali", "Moussa"][index % 2])
            sheet.write_datetime(row, 3, datetime(2026, 2, 1 + index), dated)
            sheet.write_string(row, 4, statuses[index % 4])
        sheet.data_validation("E2:E13", {"validate": "list", "source": statuses})

    _book(path, write)


def calculator(path: Path) -> None:
    def write(book: Any) -> None:
        sheet = book.add_worksheet("Calcul")
        sheet.write_string("A1", "Prix par matière")
        sheet.write_number("B1", 3000)
        sheet.write_string("A2", "Nombre de matières")
        sheet.write_number("B2", 2)
        sheet.write_string("A3", "Frères et sœurs")
        sheet.write_number("B3", 1)
        sheet.write_string("A4", "Sous-total")
        sheet.write_formula("B4", "=B1*B2", None, 6000)
        sheet.write_string("A5", "Remise")
        sheet.write_formula("B5", "=IF(B3>=1,0.05,0)*B4", None, 300)
        sheet.write_string("A6", "À payer")
        sheet.write_formula("B6", "=B4-B5", None, 5700)

    _book(path, write)


def reference_list(path: Path) -> None:
    def write(book: Any) -> None:
        data = book.add_worksheet("Commandes")
        bold = book.add_format({"bold": True})
        data.write_row("A1", ["Commande", "Wilaya"], bold)
        wilayas = ["Alger", "Oran", "Constantine", "Blida", "Sétif", "Annaba"]
        for index in range(12):
            data.write_string(1 + index, 0, f"C-{index}")
            data.write_string(1 + index, 1, wilayas[index % 6])
        data.data_validation("B2:B13", {"validate": "list", "source": "=Wilayas!$A$2:$A$7"})
        lookup = book.add_worksheet("Wilayas")
        lookup.write_string("A1", "Wilaya", bold)
        for index, wilaya in enumerate(wilayas):
            lookup.write_string(1 + index, 0, wilaya)

    _book(path, write)


def form_empty_chart(path: Path) -> None:
    def write(book: Any) -> None:
        form = book.add_worksheet("Fiche")
        for index, label in enumerate(["Nom :", "Adresse :", "Téléphone :", "Date :"]):
            form.write_string(index, 0, label)
        book.add_worksheet("Vide")
        chart_data = book.add_worksheet("Données")
        chart_data.write_row("A1", ["Mois", "Ventes"])
        for index in range(4):
            chart_data.write_row(1 + index, 0, [f"M{index}", index * 2.5])
        chart = book.add_chart({"type": "column"})
        chart.add_series({"values": "=Données!$B$2:$B$5"})
        book.add_chartsheet("Graphique").set_chart(chart)

    _book(path, write)


def values_only_total(path: Path) -> None:
    def write(book: Any) -> None:
        sheet = book.add_worksheet("Caisse")
        bold = book.add_format({"bold": True})
        sheet.write_row("A1", ["Article", "Vendu"], bold)
        values = [120, 80, 45, 300, 15]
        for index, value in enumerate(values):
            sheet.write_string(1 + index, 0, f"Article {index}")
            sheet.write_number(1 + index, 1, value)
        sheet.write_number(6, 1, sum(values))  # A pasted total: no label and no formula.

    _book(path, write)


def text_typed_values(path: Path) -> None:
    def write(book: Any) -> None:
        sheet = book.add_worksheet("Clients")
        bold = book.add_format({"bold": True})
        sheet.write_row("A1", ["Nom", "Inscrit", "Solde", "Actif", "Remise"], bold)
        for index in range(8):
            row = [NAMES[index], f"{1 + index:02d}/03/2026", f"1 2{index}0,50 DA", "Oui" if index % 2 else "Non", f"{index + 5}%"]
            sheet.write_row(1 + index, 0, row)

    _book(path, write)


CASES = [
    Case("register-title", "register", "fr", register_with_title, [
        _sheet("Élèves", "register", [_table("A4:F16", [4], [
            _field("A", "N°", "integer"), _field("B", "Nom", "text"), _field("C", "Téléphone", "phone"),
            _field("D", "Naissance", "date"), _field("E", "Email", "email"), _field("F", "Moyenne", "decimal"),
        ])])], []),
    Case("ledger-totals", "ledger", "fr", ledger_with_totals, [
        _sheet("Janvier", "ledger", [_table("A1:E12", [1], [
            _field("A", "Date", "date"), _field("B", "Client", "text"), _field("C", "Montant", "money"),
            _field("D", "Payé", "money"), _field("E", "Reste", "computed"),
        ], [12])])], []),
    Case("side-by-side", "stress", "fr", two_tables_side_by_side, [
        _sheet("Stock", "register", [
            _table("A3:B11", [3], [_field("A", "Article", "text"), _field("B", "Quantité", "integer")]),
            _table("D3:F9", [3], [_field("D", "Fournisseur", "text"), _field("E", "Téléphone", "phone"), _field("F", "Ville", "text")]),
        ])], []),
    Case("stacked", "stress", "fr", two_tables_stacked, [
        _sheet("Atelier", "register", [
            _table("A1:B6", [1], [_field("A", "Pièce", "text"), _field("B", "Prix", "money")]),
            _table("A9:B13", [9], [_field("A", "Employé", "text"), _field("B", "Téléphone", "phone")]),
        ])], []),
    Case("merged-headers", "stress", "fr", merged_two_row_header, [
        _sheet("Ventes", "register", [_table("A1:E10", [1, 2], [
            _field("A", "Produit", "text"), _field("B", "Janvier / Quantité", "integer"),
            _field("C", "Janvier / Valeur", "decimal"), _field("D", "Février / Quantité", "integer"),
            _field("E", "Février / Valeur", "decimal"),
        ])])], []),
    Case("arabic", "register", "ar", arabic_register, [
        _sheet("الزبائن", "register", [_table("A1:C10", [1], [
            _field("A", "الاسم", "text"), _field("B", "الهاتف", "phone"), _field("C", "الرصيد", "money"),
        ], [10])])], []),
    Case("tracker", "tracker", "fr", tracker_with_list, [
        _sheet("Réparations", "tracker", [_table("A1:E13", [1], [
            _field("A", "Appareil", "text"), _field("B", "Client", "text"), _field("C", "Technicien", "choice"),
            _field("D", "Reçu le", "date"), _field("E", "État", "choice"),
        ])])], []),
    Case("calculator", "formulaModel", "fr", calculator, [_sheet("Calcul", "formulaModel")], []),
    Case("reference", "register", "fr", reference_list, [
        _sheet("Commandes", "register", [_table("A1:B13", [1], [_field("A", "Commande", "text"), _field("B", "Wilaya", "link")])]),
        _sheet("Wilayas", "referenceList", [_table("A1:A7", [1], [_field("A", "Wilaya", "text")])]),
    ], []),
    Case("not-converted", "distractor", "fr", form_empty_chart, [
        _sheet("Fiche", "notConverted", reason="form"),
        _sheet("Vide", "notConverted", reason="empty"),
        _sheet("Données", "register", [_table("A1:B5", [1], [_field("A", "Mois", "text"), _field("B", "Ventes", "decimal")])]),
        _sheet("Graphique", "notConverted", reason="chartOrPivotOnly"),
    ], []),
    Case("values-total", "register", "fr", values_only_total, [
        _sheet("Caisse", "register", [_table("A1:B7", [1], [_field("A", "Article", "text"), _field("B", "Vendu", "integer")], [7])])], []),
    Case("text-values", "register", "fr", text_typed_values, [
        # A date beside money reads as a ledger. Arguably wrong for a client list; the review decides.
        _sheet("Clients", "ledger", [_table("A1:E9", [1], [
            _field("A", "Nom", "text"), _field("B", "Inscrit", "date"), _field("C", "Solde", "money"),
            _field("D", "Actif", "boolean"), _field("E", "Remise", "percent"),
        ])])], []),
]  # fmt: skip
