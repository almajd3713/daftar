"""Build the French and Arabic SME replicas (WP-4). Everything in them is invented.

Run from the repository root: uv run python eval/replicas/build.py
They imitate how small firms keep their books, not any real firm. The stored formula results are
worked out here, so no real spreadsheet program made them, and the reader reports that: these files
stay out of the formula-parity score.
"""

from datetime import date, datetime
from pathlib import Path

import xlsxwriter


OUT = Path(__file__).resolve().parents[1] / "workbooks"
BUILT = datetime(2026, 1, 1)


def quincaillerie(path: Path) -> None:
    """A hardware shop's credit sales: price list, customers, one tab a month, an order form, a recap."""
    book = xlsxwriter.Workbook(str(path))
    book.set_properties({"created": BUILT, "title": "Ventes a credit"})
    bold = book.add_format({"bold": True})
    title = book.add_format({"bold": True, "font_size": 14})
    head = book.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1, "align": "center", "text_wrap": True})
    money = book.add_format({"num_format": '#,##0.00 "DA"'})
    money_bold = book.add_format({"num_format": '#,##0.00 "DA"', "bold": True, "top": 1})
    day = book.add_format({"num_format": "dd/mm/yyyy"})
    label_total = book.add_format({"bold": True, "top": 1})
    paid = book.add_format({"bg_color": "#C6EFCE"})
    partial = book.add_format({"bg_color": "#FFEB9C"})
    unpaid = book.add_format({"bg_color": "#FFC7CE"})

    notes = book.add_worksheet("Lisez-moi")
    notes.write("A1", "Cahier des ventes à crédit", title)
    notes.write("A3", "Mettre à jour le stock chaque samedi.")
    notes.write("A4", "Ne pas toucher aux colonnes en bleu : elles se calculent seules.")
    notes.write("A5", "Tahar passe vérifier les bons la dernière semaine du mois.")

    articles = [
        ("R-101", "Robinet mitigeur", "Plomberie", 1800, 2600, 14),
        ("R-102", "Flexible 50 cm", "Plomberie", 250, 400, 60),
        ("E-201", "Disjoncteur 16 A", "Électricité", 650, 950, 35),
        ("E-202", "Câble 2,5 mm (rouleau)", "Électricité", 4200, 5600, 9),
        ("E-203", "Prise murale", "Électricité", 180, 300, 120),
        ("P-301", "Peinture blanche 25 kg", "Peinture", 3900, 5200, 22),
        ("P-302", "Rouleau 18 cm", "Peinture", 220, 380, 45),
        ("O-401", "Perceuse 750 W", "Outillage", 8200, 10500, 6),
        ("O-402", "Marteau", "Outillage", 600, 900, 30),
        ("O-403", "Niveau à bulle", "Outillage", 750, 1150, 12),
    ]
    prices = book.add_worksheet("Articles")
    prices.merge_range("A1:G1", "Liste des articles 2026", title)
    for column, text in enumerate(["Réf", "Désignation", "Famille", "Prix achat", "Prix vente", "Marge", "Stock"]):
        prices.write(2, column, text, head)
    for row, (ref, name, family, cost, sale, stock) in enumerate(articles, start=3):
        prices.write(row, 0, ref)
        prices.write(row, 1, name)
        prices.write(row, 2, family)
        prices.write_number(row, 3, cost, money)
        prices.write_number(row, 4, sale, money)
        prices.write_formula(row, 5, f"=E{row + 1}-D{row + 1}", money, sale - cost)
        prices.write_number(row, 6, stock)

    customers = [
        ("C01", "Entreprise Benmoussa BTP", "0550 10 00 01", "Blida", 200000),
        ("C02", "M. Hamidi Karim", "0661 20 00 02", "Boufarik", 50000),
        ("C03", "Sarl Atlas Rénovation", "0770 30 00 03", "Blida", 150000),
        ("C04", "Mme Zerrouki", "0552 40 00 04", "Chiffa", 30000),
        ("C05", "Peintres Associés", "0663 50 00 05", "Mouzaïa", 80000),
        ("C06", "Oussama électricité", "0771 60 00 06", "Boufarik", 60000),
    ]
    clients = book.add_worksheet("Clients")
    for column, text in enumerate(["Code", "Client", "Téléphone", "Commune", "Plafond crédit"]):
        clients.write(0, column, text, head)
    for row, (code, name, phone, town, ceiling) in enumerate(customers, start=1):
        clients.write(row, 0, code)
        clients.write(row, 1, name)
        clients.write_string(row, 2, phone)
        clients.write(row, 3, town)
        clients.write_number(row, 4, ceiling, money)

    prices_by_ref = {item[0]: item for item in articles}
    names = {item[0]: item[1] for item in customers}
    months = [
        ("Janvier 2026", 1, [("C01", "E-202", 3, 16800), ("C02", "R-101", 1, 1000), ("C03", "P-301", 5, 26000), ("C04", "E-203", 4, 0), ("C01", "O-401", 1, 10500), ("C05", "P-302", 10, 3800), ("C06", "E-201", 6, 2000)]),
        ("Février 2026", 2, [("C03", "P-301", 2, 10400), ("C02", "O-402", 2, 0), ("C06", "E-202", 1, 5600), ("C01", "R-102", 8, 3200), ("C05", "P-301", 3, 5000), ("C04", "O-403", 1, 1150)]),
        ("Mars 2026", 3, [("C01", "E-201", 10, 9500), ("C05", "P-302", 6, 0), ("C03", "O-401", 1, 5000), ("C06", "E-203", 12, 3600), ("C02", "R-101", 2, 5200), ("C04", "P-301", 1, 0), ("C03", "E-202", 2, 11200), ("C05", "O-402", 1, 900)]),
    ]
    number = 100
    # A quarter's recap reads every month, so remember where each one's totals land.
    totals: list[tuple[str, int, float, float]] = []
    for name, month, sales in months:
        sheet = book.add_worksheet(name)
        sheet.merge_range("A1:K1", f"Ventes à crédit, {name}", title)
        sheet.merge_range("A2:A3", "N° bon", head)
        sheet.merge_range("B2:B3", "Date", head)
        sheet.merge_range("C2:D2", "Client", head)
        sheet.write("C3", "Code", head)
        sheet.write("D3", "Nom", head)
        sheet.merge_range("E2:H2", "Article", head)
        for column, text in zip("EFGH", ["Réf", "Qté", "P.U.", "Montant"], strict=True):
            sheet.write(f"{column}3", text, head)
        sheet.merge_range("I2:K2", "Règlement", head)
        for column, text in zip("IJK", ["Versé", "Reste", "Statut"], strict=True):
            sheet.write(f"{column}3", text, head)
        first = 4
        amount_total = 0.0
        paid_total = 0.0
        for index, (code, ref, quantity, payment) in enumerate(sales):
            row = first + index
            number += 1
            sale_price = prices_by_ref[ref][4]
            amount = quantity * sale_price
            rest = amount - payment
            status = "Payé" if rest == 0 else ("Partiel" if payment else "Impayé")
            amount_total += amount
            paid_total += payment
            sheet.write_number(row - 1, 0, number)
            sheet.write_datetime(row - 1, 1, date(2026, month, 3 + index * 3), day)
            sheet.write(row - 1, 2, code)
            sheet.write_formula(row - 1, 3, f"=VLOOKUP(C{row},Clients!$A$2:$B$7,2,FALSE)", None, names[code])
            sheet.write(row - 1, 4, ref)
            sheet.write_number(row - 1, 5, quantity)
            sheet.write_formula(row - 1, 6, f"=VLOOKUP(E{row},Articles!$A$4:$E$13,5,FALSE)", money, sale_price)
            sheet.write_formula(row - 1, 7, f"=F{row}*G{row}", money, amount)
            sheet.write_number(row - 1, 8, payment, money)
            sheet.write_formula(row - 1, 9, f"=H{row}-I{row}", money, rest)
            sheet.write(row - 1, 10, status, {"Payé": paid, "Partiel": partial, "Impayé": unpaid}[status])
        last = first + len(sales) - 1
        sheet.data_validation(f"K{first}:K{last + 20}", {"validate": "list", "source": ["Payé", "Partiel", "Impayé"]})
        sheet.data_validation(f"C{first}:C{last + 20}", {"validate": "list", "source": "=Clients!$A$2:$A$7"})
        total = last + 1
        sheet.write(total - 1, 0, "TOTAL", label_total)
        sheet.write_formula(total - 1, 7, f"=SUM(H{first}:H{last})", money_bold, amount_total)
        sheet.write_formula(total - 1, 8, f"=SUM(I{first}:I{last})", money_bold, paid_total)
        sheet.write_formula(total - 1, 9, f"=SUM(J{first}:J{last})", money_bold, amount_total - paid_total)
        totals.append((name, total, amount_total, paid_total))

    recap = book.add_worksheet("Bilan T1")
    recap.write("A1", "Bilan du premier trimestre", title)
    for column, text in enumerate(["Mois", "Ventes", "Encaissé", "Reste à encaisser"]):
        recap.write(2, column, text, head)
    for row, (name, total, sold, cashed) in enumerate(totals, start=3):
        recap.write(row, 0, name)
        recap.write_formula(row, 1, f"='{name}'!H{total}", money, sold)
        recap.write_formula(row, 2, f"='{name}'!I{total}", money, cashed)
        recap.write_formula(row, 3, f"=B{row + 1}-C{row + 1}", money, sold - cashed)
    recap.write(6, 0, "Total", label_total)
    all_sold = sum(item[2] for item in totals)
    all_cashed = sum(item[3] for item in totals)
    recap.write_formula(6, 1, "=SUM(B4:B6)", money_bold, all_sold)
    recap.write_formula(6, 2, "=SUM(C4:C6)", money_bold, all_cashed)
    recap.write_formula(6, 3, "=SUM(D4:D6)", money_bold, all_sold - all_cashed)
    chart = book.add_chart({"type": "column"})
    chart.add_series({"categories": "='Bilan T1'!$A$4:$A$6", "values": "='Bilan T1'!$B$4:$B$6", "name": "Ventes"})
    recap.insert_chart("F2", chart)

    form = book.add_worksheet("Bon de commande")
    form.merge_range("A1:D1", "BON DE COMMANDE", title)
    form.write("A3", "Client :", bold)
    form.write("A4", "Date :", bold)
    form.write("C3", "N° :", bold)
    for column, text in enumerate(["Désignation", "Qté", "P.U.", "Montant"]):
        form.write(5, column, text, head)
    form.write("C12", "Total à payer", bold)
    form.write_formula("D12", "=SUM(D7:D11)", money, 0)
    form.write("A14", "Signature du client :", bold)
    book.close()


def atelier(path: Path) -> None:
    """A repair workshop in Arabic, right to left: customers, job tracking, a price list, an invoice sum."""
    book = xlsxwriter.Workbook(str(path))
    book.set_properties({"created": BUILT, "title": "ورشة التصليح"})
    title = book.add_format({"bold": True, "font_size": 14, "align": "right"})
    head = book.add_format({"bold": True, "bg_color": "#FCE4D6", "border": 1, "align": "center"})
    money = book.add_format({"num_format": '#,##0 "دج"'})
    money_bold = book.add_format({"num_format": '#,##0 "دج"', "bold": True, "top": 1})
    day = book.add_format({"num_format": "dd/mm/yyyy"})
    bold = book.add_format({"bold": True})
    entry = book.add_format({"bg_color": "#FFF2CC", "border": 1})
    entry_money = book.add_format({"bg_color": "#FFF2CC", "border": 1, "num_format": '#,##0 "دج"'})
    percent = book.add_format({"bg_color": "#FFF2CC", "border": 1, "num_format": "0%"})

    customers = [
        ("Z01", "عبد القادر بن علي", "0550 11 22 01", "البليدة"),
        ("Z02", "سمية حمدي", "0660 11 22 02", "بوفاريك"),
        ("Z03", "مقهى النخيل", "0770 11 22 03", "البليدة"),
        ("Z04", "رشيد زروقي", "٠٥٥١١١٢٢٠٤", "الشفة"),
        ("Z05", "مدرسة الأمل الخاصة", "0661 11 22 05", "موزاية"),
    ]
    people = book.add_worksheet("الزبائن")
    people.right_to_left()
    for column, text in enumerate(["الرمز", "الاسم", "الهاتف", "البلدية"]):
        people.write(0, column, text, head)
    for row, item in enumerate(customers, start=1):
        for column, value in enumerate(item):
            people.write_string(row, column, value)

    price_rows = [("تغيير شاشة هاتف", 3500), ("تغيير بطارية", 1500), ("تنظيف حاسوب", 1000), ("تثبيت ويندوز", 1200), ("تصليح طابعة", 2500), ("فحص فقط", 500)]
    prices = book.add_worksheet("التسعيرة")
    prices.right_to_left()
    prices.write("A1", "نوع الخدمة", head)
    prices.write("B1", "السعر", head)
    for row, (name, price) in enumerate(price_rows, start=1):
        prices.write(row, 0, name)
        prices.write_number(row, 1, price, money)

    jobs = [
        (501, date(2026, 2, 2), "عبد القادر بن علي", "هاتف سامسونج", "تغيير شاشة هاتف", "ياسين", "تم التسليم", 3500),
        (502, date(2026, 2, 3), "سمية حمدى", "حاسوب محمول", "تثبيت ويندوز", "ياسين", "تم التسليم", 1200),
        (503, date(2026, 2, 5), "مقهى النخيل", "طابعة", "تصليح طابعة", "أمين", "جاهز", 1000),
        (504, date(2026, 2, 8), "ع. القادر بن علي", "هاتف شاومي", "تغيير بطارية", "أمين", "جاهز", 0),
        (505, date(2026, 2, 10), "رشيد زروقي", "حاسوب مكتبي", "تنظيف حاسوب", "ياسين", "قيد التصليح", 0),
        (506, date(2026, 2, 12), "مدرسة الأمل الخاصة", "طابعة", "تصليح طابعة", "أمين", "قيد التصليح", 1500),
        (507, date(2026, 2, 14), "مدرسة الأمل", "حاسوب محمول", "تثبيت ويندوز", "ياسين", "في الانتظار", 0),
        (508, date(2026, 2, 15), "سمية حمدي", "هاتف ايفون", "فحص فقط", "أمين", "في الانتظار", 500),
    ]
    lookup = dict(price_rows)
    track = book.add_worksheet("متابعة التصليح")
    track.right_to_left()
    track.merge_range("A1:J1", "متابعة الأجهزة في الورشة", title)
    for column, text in enumerate(["رقم الوصل", "تاريخ الدخول", "الزبون", "الجهاز", "الخدمة", "التقني", "الحالة", "السعر", "المدفوع", "الباقي"]):
        track.write(2, column, text, head)
    for index, (number, entered, who, device, service, technician, status, advance) in enumerate(jobs):
        row = 4 + index
        price = lookup[service]
        track.write_number(row - 1, 0, number)
        track.write_datetime(row - 1, 1, entered, day)
        track.write(row - 1, 2, who)
        track.write(row - 1, 3, device)
        track.write(row - 1, 4, service)
        track.write(row - 1, 5, technician)
        track.write(row - 1, 6, status)
        track.write_formula(row - 1, 7, f"=VLOOKUP(E{row},التسعيرة!$A$2:$B$7,2,FALSE)", money, price)
        track.write_number(row - 1, 8, advance, money)
        track.write_formula(row - 1, 9, f"=H{row}-I{row}", money, price - advance)
    last = 3 + len(jobs)
    track.data_validation(f"G4:G{last + 30}", {"validate": "list", "source": ["في الانتظار", "قيد التصليح", "جاهز", "تم التسليم"]})
    track.data_validation(f"E4:E{last + 30}", {"validate": "list", "source": "=التسعيرة!$A$2:$A$7"})
    for status, colour in (("في الانتظار", "#D9D9D9"), ("قيد التصليح", "#FFEB9C"), ("جاهز", "#BDD7EE"), ("تم التسليم", "#C6EFCE")):
        track.conditional_format(f"G4:G{last + 30}", {"type": "cell", "criteria": "==", "value": f'"{status}"', "format": book.add_format({"bg_color": colour})})

    invoice = book.add_worksheet("حساب الفاتورة")
    invoice.right_to_left()
    invoice.write("A1", "حساب الفاتورة", title)
    invoice.write("A3", "ثمن القطع", bold)
    invoice.write_number("B3", 2000, entry_money)
    invoice.write("A4", "ساعات العمل", bold)
    invoice.write_number("B4", 2, entry)
    invoice.write("A5", "ثمن الساعة", bold)
    invoice.write_number("B5", 800, entry_money)
    invoice.write("A6", "نسبة الرسم", bold)
    invoice.write_number("B6", 0.19, percent)
    invoice.write("A8", "اليد العاملة", bold)
    invoice.write_formula("B8", "=B4*B5", money, 1600)
    invoice.write("A9", "المجموع دون رسم", bold)
    invoice.write_formula("B9", "=B3+B8", money, 3600)
    invoice.write("A10", "الرسم", bold)
    invoice.write_formula("B10", "=ROUND(B9*B6,0)", money, 684)
    invoice.write("A11", "المجموع للدفع", bold)
    invoice.write_formula("B11", "=B9+B10", money_bold, 4284)
    book.close()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    quincaillerie(OUT / "rp_fr_quincaillerie.xlsx")
    atelier(OUT / "rp_ar_atelier.xlsx")
