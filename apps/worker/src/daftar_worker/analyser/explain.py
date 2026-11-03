"""R-10: explanations in French and Arabic, built from facts: counts, sheet names, cells.

Written for a shop owner. A language model may reword these later but never adds facts.
"""

from typing import Any


Explanation = dict[str, str]

TYPE_NAMES: dict[str, tuple[str, str]] = {
    "text": ("texte", "نص"),
    "longtext": ("texte long", "نص طويل"),
    "integer": ("nombre entier", "عدد صحيح"),
    "decimal": ("nombre à virgule", "عدد عشري"),
    "money": ("montant en dinars", "مبلغ بالدينار"),
    "percent": ("pourcentage", "نسبة مئوية"),
    "date": ("date", "تاريخ"),
    "datetime": ("date et heure", "تاريخ ووقت"),
    "boolean": ("oui ou non", "نعم أو لا"),
    "choice": ("liste de choix", "قائمة اختيارات"),
    "multichoice": ("plusieurs choix", "اختيارات متعددة"),
    "phone": ("numéro de téléphone", "رقم هاتف"),
    "email": ("adresse e-mail", "بريد إلكتروني"),
    "link": ("lien vers une autre liste", "رابط إلى قائمة أخرى"),
    "computed": ("valeur calculée", "قيمة محسوبة"),
}

OUTCOME_NAMES: dict[str, tuple[str, str]] = {
    "register": ("une liste d'enregistrements", "سجل من البيانات"),
    "ledger": ("un registre de montants", "سجل مبالغ"),
    "formulaModel": ("un calcul", "ورقة حساب"),
    "tracker": ("un suivi d'avancement", "متابعة تقدم"),
    "referenceList": ("une liste de référence", "قائمة مرجعية"),
}

REASONS: dict[str, tuple[str, str]] = {
    "form": ("c'est un formulaire à remplir", "إنها استمارة للملء"),
    "report": ("c'est un rapport qui résume d'autres données", "إنها تقرير يلخص بيانات أخرى"),
    "chartOrPivotOnly": (
        "elle ne contient qu'un graphique ou un tableau croisé",
        "لا تحتوي إلا على رسم بياني أو جدول محوري",
    ),
    "empty": ("elle est vide", "إنها فارغة"),
    "outOfScope": ("elle ne contient pas de données à convertir", "لا تحتوي على بيانات قابلة للتحويل"),
}

TYPE_EVIDENCE: dict[str, tuple[str, str]] = {
    "percentFormat": ("les cellules sont au format pourcentage", "الخلايا بتنسيق النسبة المئوية"),
    "currencyFormat": ("les cellules sont au format monétaire en dinars", "الخلايا بتنسيق العملة بالدينار"),
    "dateFormat": ("les cellules sont au format date", "الخلايا بتنسيق التاريخ"),
    "serialDate": ("les nombres correspondent à des dates Excel", "الأرقام تطابق تواريخ إكسل"),
    "phoneLostZero": (
        "les nombres ressemblent à des téléphones sans le 0 du début",
        "الأرقام تشبه هواتف بدون الصفر الأول",
    ),
    "moneyHeader": ("le titre de la colonne indique un montant", "عنوان العمود يدل على مبلغ"),
    "wholeNumbers": ("les valeurs sont des nombres entiers", "القيم أعداد صحيحة"),
    "decimalNumbers": ("les valeurs sont des nombres", "القيم أرقام"),
    "phonePattern": ("les valeurs ressemblent à des numéros algériens", "القيم تشبه أرقام هواتف جزائرية"),
    "emailPattern": ("les valeurs ressemblent à des adresses e-mail", "القيم تشبه عناوين بريد إلكتروني"),
    "textDate": ("les valeurs sont écrites comme des dates", "القيم مكتوبة كتواريخ"),
    "moneyText": ("les valeurs sont écrites avec DA", "القيم مكتوبة مع دج"),
    "percentText": ("les valeurs sont écrites avec %", "القيم مكتوبة مع %"),
    "booleanWords": ("les valeurs sont du type oui ou non", "القيم من نوع نعم أو لا"),
    "numericText": ("les valeurs sont des nombres écrits en texte", "القيم أرقام مكتوبة كنص"),
    "trueFalse": ("les valeurs sont vrai ou faux", "القيم صحيح أو خطأ"),
    "longValues": ("les valeurs sont de longs textes", "القيم نصوص طويلة"),
    "fewValues": ("peu de valeurs différentes se répètent", "قيم قليلة مختلفة تتكرر"),
    "fewValuesSeparated": ("les valeurs combinent quelques choix", "القيم تجمع بين اختيارات قليلة"),
    "plainText": ("les valeurs sont du texte", "القيم نص"),
    "validationList": ("la colonne a une liste déroulante", "للعمود قائمة منسدلة"),
    "validationOtherSheet": (
        "sa liste déroulante vient d'une autre feuille",
        "قائمته المنسدلة تأتي من ورقة أخرى",
    ),
    "formulaColumn": ("la colonne est remplie par une formule", "العمود يُملأ بصيغة"),
}


def sheet_kind(sheet: str, outcome: str, reason: str | None, facts: dict[str, Any]) -> Explanation:
    tables = facts.get("tables", 0)
    cells = facts.get("cells", 0)
    if outcome == "notConverted":
        fr, ar = REASONS[reason or "outOfScope"]
        return {
            "fr": f"La feuille « {sheet} » ne sera pas convertie : {fr} ({cells} cellules remplies).",
            "ar": f"لن تُحوَّل الورقة «{sheet}»: {ar} ({cells} خلية ممتلئة).",
        }
    fr, ar = OUTCOME_NAMES[outcome]
    return {
        "fr": f"La feuille « {sheet} » ressemble à {fr} : {tables} tableau(x), {cells} cellules remplies.",
        "ar": f"الورقة «{sheet}» تشبه {ar}: {tables} جدول، {cells} خلية ممتلئة.",
    }


def table(sheet: str, cell_range: str, rows: int, columns: int) -> Explanation:
    return {
        "fr": f"Tableau trouvé dans « {sheet} », cellules {cell_range} : {rows} lignes et {columns} colonnes.",
        "ar": f"وُجد جدول في «{sheet}»، الخلايا {cell_range}: {rows} صف و{columns} عمود.",
    }


def header(sheet: str, rows: list[int], count: int) -> Explanation:
    numbers = ", ".join(str(row) for row in rows)
    return {
        "fr": f"Titres de colonnes dans « {sheet} », ligne(s) {numbers} : {count} colonnes.",
        "ar": f"عناوين الأعمدة في «{sheet}»، الصف {numbers}: {count} عمود.",
    }


def total_row(sheet: str, row: int, source: str, columns: int) -> Explanation:
    why = {
        "formula": ("elle additionne les lignes au-dessus", "يجمع الصفوف التي فوقه"),
        "keyword": ("son libellé indique un total", "عنوانه يدل على مجموع"),
        "arithmetic": ("ses valeurs égalent la somme des lignes au-dessus", "قيمه تساوي مجموع الصفوف التي فوقه"),
        "afterTotal": ("elle suit la ligne de total et sa première colonne est vide", "يأتي بعد صف المجموع وعموده الأول فارغ"),
    }[source]
    return {
        "fr": f"La ligne {row} de « {sheet} » est un total, pas une donnée : {why[0]} ({columns} colonne(s)).",
        "ar": f"الصف {row} في «{sheet}» مجموع وليس بيانات: {why[1]} ({columns} عمود).",
    }


def field_type(header_text: str, field: str, kind: str, reason: str, matched: int, total: int) -> Explanation:
    type_fr, type_ar = TYPE_NAMES[kind]
    evidence_fr, evidence_ar = TYPE_EVIDENCE[reason]
    name = header_text or field
    return {
        "fr": f"« {name} » ({field}) est un champ {type_fr} : {evidence_fr} ({matched} valeurs sur {total}).",
        "ar": f"«{name}» ({field}) حقل من نوع {type_ar}: {evidence_ar} ({matched} قيمة من {total}).",
    }


def choice_list(header_text: str, field: str, values: list[dict[str, Any]], source: str) -> Explanation:
    sample = ", ".join(str(item["value"]) for item in values[:5])
    if source == "validationList":
        return {
            "fr": f"« {header_text or field} » : la liste déroulante propose {len(values)} choix ({sample}).",
            "ar": f"«{header_text or field}»: القائمة المنسدلة تقترح {len(values)} اختيار ({sample}).",
        }
    return {
        "fr": f"« {header_text or field} » : seulement {len(values)} valeurs différentes ({sample}). En faire une liste de choix ?",
        "ar": f"«{header_text or field}»: {len(values)} قيم مختلفة فقط ({sample}). هل نجعلها قائمة اختيارات؟",
    }


UNSUPPORTED_NAMES: dict[str, tuple[str, str]] = {
    "pivot": ("un tableau croisé dynamique", "جدول محوري"),
    "chart": ("un graphique", "رسم بياني"),
    "image": ("une image", "صورة"),
    "shape": ("une forme", "شكل"),
    "macro": ("une macro", "ماكرو"),
    "externalLink": ("un lien vers un autre fichier", "رابط إلى ملف آخر"),
    "other": ("un élément spécial", "عنصر خاص"),
}


def unsupported(kind: str, sheet: str | None, ref: str | None, count: int) -> Explanation:
    fr, ar = UNSUPPORTED_NAMES[kind]
    where_fr = f" dans « {sheet} »" if sheet else ""
    where_ar = f" في «{sheet}»" if sheet else ""
    if ref:
        where_fr += f", cellule {ref}"
        where_ar += f"، الخلية {ref}"
    times_fr = f" (× {count})" if count > 1 else ""
    times_ar = f" (× {count})" if count > 1 else ""
    return {
        "fr": f"Le fichier contient {fr}{where_fr}{times_fr}. Il ne sera pas repris dans l'application.",
        "ar": f"يحتوي الملف على {ar}{where_ar}{times_ar}. لن يُنقل إلى التطبيق.",
    }
