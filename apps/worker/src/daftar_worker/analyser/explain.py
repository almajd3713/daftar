"""R-10: explanations in French and Arabic, built from facts: counts, sheet names, cells.

Written for a shop owner. A language model may reword these later but never adds facts.
"""

from collections.abc import Iterable
import re
from typing import Any


Explanation = dict[str, str]

FSI, PDI = "\u2068", "\u2069"
# In a cell's text these could reorder or leak out of the sentence around it.
_BIDI_CONTROLS = re.compile("[\u202a-\u202e\u2066-\u2069]")
_ISOLATED = re.compile(f"{FSI}(.*?){PDI}", re.DOTALL)

# One, two (subject form), three to ten, eleven to ninety-nine, and hundreds. Arabic counts by these.
ARABIC_NOUNS: dict[str, tuple[str, str, str, str, str]] = {
    "row": ("صف واحد", "صفان", "صفوف", "صفا", "صف"),
    "column": ("عمود واحد", "عمودان", "أعمدة", "عمودا", "عمود"),
    "cell": ("خلية واحدة", "خليتان", "خلايا", "خلية", "خلية"),
    "table": ("جدول واحد", "جدولان", "جداول", "جدولا", "جدول"),
    "value": ("قيمة واحدة", "قيمتان", "قيم", "قيمة", "قيمة"),
    "result": ("نتيجة واحدة", "نتيجتان", "نتائج", "نتيجة", "نتيجة"),
    "sheet": ("ورقة واحدة", "ورقتان", "أوراق", "ورقة", "ورقة"),
    "choice": ("اختيار واحد", "اختياران", "اختيارات", "اختيارا", "اختيار"),
    "colour": ("لون واحد", "لونان", "ألوان", "لونا", "لون"),
}

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


def _x(fact: object) -> str:
    """A fact from the workbook, isolated so its script can't reorder the sentence around it."""
    return f"{FSI}{_BIDI_CONTROLS.sub('', str(fact))}{PDI}"


def _list(facts: Iterable[object], separator: str = ", ") -> str:
    return separator.join(_x(fact) for fact in facts)


def plain(text: str) -> str:
    """The sentence without its isolates, for a language model, which can't be trusted to keep them."""
    return text.replace(FSI, "").replace(PDI, "")


def isolate_again(original: str, reworded: str) -> str:
    """Put back the isolates of `original` around the same facts in a model's rewording."""
    facts = sorted({fact for fact in _ISOLATED.findall(original) if fact}, key=len, reverse=True)
    if not facts:
        return reworded
    pattern = "|".join(re.escape(fact) for fact in facts)
    return re.sub(rf"(?<!\w)(?:{pattern})(?!\w)", lambda found: f"{FSI}{found.group(0)}{PDI}", reworded)


def _fr(count: int, one: str, many: str | None = None) -> str:
    """French takes the singular for 0 and 1."""
    return f"{count} {one if count <= 1 else many or one + 's'}"


def _ar(count: int, noun: str, object_form: bool = False) -> str:
    """`object_form` is for a dual after a preposition or as an object: صفين rather than صفان."""
    one, two, few, some, hundreds = ARABIC_NOUNS[noun]
    if count == 1:
        return one
    if count == 2:
        return f"{two[:-2]}ين" if object_form else two
    rest = count % 100
    if 3 <= rest <= 10:
        return f"{count} {few}"
    return f"{count} {some if rest >= 11 else hundreds}"


def sheet_kind(sheet: str, outcome: str, reason: str | None, facts: dict[str, Any]) -> Explanation:
    tables = facts.get("tables", 0)
    cells = facts.get("cells", 0)
    filled = _fr(cells, "cellule remplie", "cellules remplies")
    if outcome == "notConverted":
        fr, ar = REASONS[reason or "outOfScope"]
        return {
            "fr": f"La feuille « {_x(sheet)} » ne sera pas convertie : {fr} ({filled}).",
            "ar": f"لن تُحوَّل الورقة «{_x(sheet)}»: {ar} (الخلايا الممتلئة: {cells}).",
        }
    fr, ar = OUTCOME_NAMES[outcome]
    return {
        "fr": f"La feuille « {_x(sheet)} » ressemble à {fr} : {_fr(tables, 'tableau', 'tableaux')}, {filled}.",
        "ar": f"الورقة «{_x(sheet)}» تشبه {ar}: {_ar(tables, 'table')}، الخلايا الممتلئة: {cells}.",
    }


def table(sheet: str, cell_range: str, rows: int, columns: int) -> Explanation:
    return {
        "fr": f"Tableau trouvé dans « {_x(sheet)} », cellules {_x(cell_range)} : {_fr(rows, 'ligne')} et {_fr(columns, 'colonne')}.",
        "ar": f"وُجد جدول في «{_x(sheet)}»، الخلايا {_x(cell_range)}: {_ar(rows, 'row')} و{_ar(columns, 'column')}.",
    }


def group_column(sheet: str, labels: list[str]) -> Explanation:
    sample = _list(labels[:4]) + ("…" if len(labels) > 4 else "")
    sample_ar = _list(labels[:4], "، ") + ("…" if len(labels) > 4 else "")
    if len(labels) == 1:
        return {
            "fr": f"Dans « {_x(sheet)} », 1 ligne ({sample}) sert de titre aux lignes en dessous. Garder ce titre dans une colonne, pour chaque ligne ?",
            "ar": f"في «{_x(sheet)}»، صف واحد ({sample_ar}) هو عنوان للصفوف التي تحته. هل نحتفظ بهذا العنوان في عمود لكل صف؟",
        }
    return {
        "fr": f"Dans « {_x(sheet)} », {_fr(len(labels), 'ligne')} ({sample}) servent de titre aux lignes en dessous. Garder ces titres dans une colonne, pour chaque ligne ?",
        "ar": f"في «{_x(sheet)}»، {_ar(len(labels), 'row')} ({sample_ar}) هي عناوين للصفوف التي تحتها. هل نحتفظ بهذه العناوين في عمود لكل صف؟",
    }


def header(sheet: str, rows: list[int], count: int) -> Explanation:
    numbers = _x(", ".join(str(row) for row in rows))
    return {
        "fr": f"Titres de colonnes dans « {_x(sheet)} », {'ligne' if len(rows) == 1 else 'lignes'} {numbers} : {_fr(count, 'colonne')}.",
        "ar": f"عناوين الأعمدة في «{_x(sheet)}»، {'الصف' if len(rows) == 1 else 'الصفوف'} {numbers}: {_ar(count, 'column')}.",
    }


def total_row(sheet: str, row: int, source: str, columns: int) -> Explanation:
    why = {
        "formula": ("elle additionne les lignes au-dessus", "يجمع الصفوف التي فوقه"),
        "keyword": ("son libellé indique un total", "عنوانه يدل على مجموع"),
        "arithmetic": ("ses valeurs égalent la somme des lignes au-dessus", "قيمه تساوي مجموع الصفوف التي فوقه"),
        "afterTotal": ("elle suit la ligne de total et sa première colonne est vide", "يأتي بعد صف المجموع وعموده الأول فارغ"),
    }[source]
    return {
        "fr": f"La ligne {row} de « {_x(sheet)} » est un total, pas une donnée : {why[0]} ({_fr(columns, 'colonne')}).",
        "ar": f"الصف {row} في «{_x(sheet)}» مجموع وليس بيانات: {why[1]} ({_ar(columns, 'column')}).",
    }


def field_type(header_text: str, field: str, kind: str, reason: str, matched: int, total: int) -> Explanation:
    type_fr, type_ar = TYPE_NAMES[kind]
    evidence_fr, evidence_ar = TYPE_EVIDENCE[reason]
    name = _x(header_text or field)
    return {
        "fr": f"« {name} » ({_x(field)}) est un champ {type_fr} : {evidence_fr} ({_fr(matched, 'valeur')} sur {total}).",
        "ar": f"«{name}» ({_x(field)}) حقل من نوع {type_ar}: {evidence_ar} (القيم المطابقة: {matched} من أصل {total}).",
    }


def choice_list(header_text: str, field: str, values: list[dict[str, Any]], source: str) -> Explanation:
    shown = [item["value"] for item in values[:5]]
    name = _x(header_text or field)
    if source == "validationList":
        return {
            "fr": f"« {name} » : la liste déroulante propose {len(values)} choix ({_list(shown)}).",
            "ar": f"«{name}»: القائمة المنسدلة تقترح {_ar(len(values), 'choice', object_form=True)} ({_list(shown, '، ')}).",
        }
    return {
        "fr": f"« {name} » : seulement {_fr(len(values), 'valeur différente', 'valeurs différentes')} ({_list(shown)}). En faire une liste de choix ?",
        "ar": f"«{name}»: عدد القيم المختلفة {len(values)} فقط ({_list(shown, '، ')}). هل نجعلها قائمة اختيارات؟",
    }


def computed_field(
    header_text: str, field: str, formula: str, matching: int, total: int, translated: bool, missing: list[str]
) -> Explanation:
    name = _x(header_text or field)
    if missing:
        return {
            "fr": f"« {name} » utilise {_list(missing)}, que Daftar ne sait pas calculer. Cette colonne doit être vérifiée.",
            "ar": f"«{name}» يستعمل {_list(missing, '، ')}، ولا يستطيع دفتر حسابها. يجب التحقق من هذا العمود.",
        }
    how_fr = "elle sera recalculée à chaque modification" if translated else "elle sera calculée par le moteur de formules"
    how_ar = "سيُعاد حسابه عند كل تعديل" if translated else "سيحسبه محرك الصيغ"
    return {
        "fr": f"« {name} » ({_x(field)}) est calculée par la formule {_x(formula)} sur {_fr(matching, 'ligne')} sur {total} : {how_fr}.",
        "ar": f"«{name}» ({_x(field)}) يُحسب بالصيغة {_x(formula)} في {matching} من أصل {_ar(total, 'row', object_form=True)}: {how_ar}.",
    }


def inconsistent_formula(header_text: str, field: str, cells: list[str], count: int) -> Explanation:
    name = _x(header_text or field)
    sample = cells[:5]
    verb = "ne suit" if count == 1 else "ne suivent"
    return {
        "fr": f"Dans « {name} », {_fr(count, 'cellule')} {verb} pas la formule de la colonne : {_list(sample)}.",
        "ar": f"في «{name}»، عدد الخلايا التي لا تتبع صيغة العمود: {count} ({_list(sample, '، ')}).",
    }


def relation_from_lookup(sheet: str, source: str, to_sheet: str, target: str) -> Explanation:
    return {
        "fr": f"La colonne {_x(source)} de « {_x(sheet)} » va chercher ses valeurs dans la colonne {_x(target)} de « {_x(to_sheet)} ». En faire un lien entre les deux listes ?",
        "ar": f"العمود {_x(source)} في «{_x(sheet)}» يبحث عن قيمه في العمود {_x(target)} من «{_x(to_sheet)}». هل نجعله رابطا بين القائمتين؟",
    }


def relation_from_aggregate(sheet: str, source: str, to_sheet: str, target: str) -> Explanation:
    return {
        "fr": f"Une formule de « {_x(to_sheet)} » additionne les lignes de « {_x(sheet)} » qui ont la même valeur en colonne {_x(source)} que sa colonne {_x(target)}. Ces deux feuilles sont donc liées, sans que cette colonne identifie une seule ligne.",
        "ar": f"صيغة في «{_x(to_sheet)}» تجمع صفوف «{_x(sheet)}» التي لها في العمود {_x(source)} القيمة نفسها الموجودة في عمودها {_x(target)}. فالورقتان مرتبطتان، دون أن يحدد هذا العمود صفا واحدا.",
    }


def calculator(sheet: str, inputs: list[str], outputs: list[str]) -> Explanation:
    given = len(inputs)
    verb_fr = "donne" if given == 1 else "donnent"
    verb_ar = "تعطيان" if given == 2 else "تعطي"
    return {
        "fr": f"« {_x(sheet)} » est un calcul : {_fr(given, 'valeur')} à saisir ({_list(inputs[:5])}) {verb_fr} {_fr(len(outputs), 'résultat')} ({_list(outputs[:5])}).",
        "ar": f"«{_x(sheet)}» ورقة حساب: {_ar(given, 'value')} للإدخال ({_list(inputs[:5], '، ')}) {verb_ar} {_ar(len(outputs), 'result', object_form=True)} ({_list(outputs[:5], '، ')}).",
    }


def entity_merge(name: str, sheets: list[str], distinct: int, clusters: list[dict[str, Any]]) -> Explanation:
    where_fr = ", ".join(f"« {_x(sheet)} »" for sheet in dict.fromkeys(sheets))
    where_ar = "، ".join(f"«{_x(sheet)}»" for sheet in dict.fromkeys(sheets))
    if clusters:
        first = clusters[0]
        sample = _list((item["value"] for item in first["variants"][:3]), " / ")
        written = _fr(len(clusters), "écrite", "écrites")
        return {
            "fr": f"« {_x(name)} » revient dans {where_fr} : {_fr(distinct, 'valeur')}, dont {written} de plusieurs façons ({sample}). En faire une seule liste ?",
            "ar": f"«{_x(name)}» يتكرر في {where_ar}: {_ar(distinct, 'value')}، وعدد المكتوب منها بعدة طرق: {len(clusters)} ({sample}). هل نجعلها قائمة واحدة؟",
        }
    return {
        "fr": f"« {_x(name)} » revient dans {where_fr} : {_fr(distinct, 'valeur')}. En faire une liste à part ?",
        "ar": f"«{_x(name)}» يتكرر في {where_ar}: {_ar(distinct, 'value')}. هل نجعلها قائمة منفصلة؟",
    }


def relation_from_validation(sheet: str, source: str, to_sheet: str, target: str) -> Explanation:
    return {
        "fr": f"La colonne {_x(source)} de « {_x(sheet)} » a une liste déroulante tirée de la colonne {_x(target)} de « {_x(to_sheet)} ». En faire un lien entre les deux listes ?",
        "ar": f"العمود {_x(source)} في «{_x(sheet)}» له قائمة منسدلة من العمود {_x(target)} في «{_x(to_sheet)}». هل نجعله رابطا بين القائمتين؟",
    }


def relation_from_inclusion(sheet: str, source: str, to_sheet: str, target: str, inclusion: float) -> Explanation:
    share = round(inclusion * 100)
    return {
        "fr": f"{share} % des valeurs de la colonne {_x(source)} de « {_x(sheet)} » se trouvent dans la colonne {_x(target)} de « {_x(to_sheet)} », où chacune est unique. Est-ce un lien entre les deux listes ?",
        "ar": f"{share}% من قيم العمود {_x(source)} في «{_x(sheet)}» موجودة في العمود {_x(target)} من «{_x(to_sheet)}»، حيث كل قيمة فريدة. هل هذا رابط بين القائمتين؟",
    }


def period_union(sheets: list[str], granularity: str, columns: int, partial: int = 0, identical: bool = True) -> Explanation:
    unit_fr = {"month": "mois", "quarter": "trimestre", "year": "année"}[granularity]
    unit_ar = {"month": "الشهر", "quarter": "الفصل", "year": "السنة"}[granularity]
    more = "…" if len(sheets) > 4 else ""
    names, names_ar = _list(sheets[:4]) + more, _list(sheets[:4], "، ") + more
    count_fr, count_ar = _fr(len(sheets), "feuille"), _ar(len(sheets), "sheet")
    verb_ar = "لهما" if len(sheets) == 2 else "لها"
    share_ar = "تشتركان" if len(sheets) == 2 else "تشترك"
    if identical:
        same = "la même colonne" if columns == 1 else f"les mêmes {columns} colonnes"
        return {
            "fr": f"{count_fr} ({names}) ont {same}. En faire une seule liste, avec un champ {unit_fr} ?",
            "ar": f"{count_ar} ({names_ar}) {verb_ar} نفس الأعمدة وعددها {columns}. هل نجعلها قائمة واحدة مع حقل {unit_ar}؟",
        }
    # Their titles or order differ, so a person should look: it's a match by name, not a certainty.
    extra_fr = f", et {_fr(partial, 'colonne présente', 'colonnes présentes')} dans certaines seulement" if partial else ""
    extra_ar = f"، وعدد الأعمدة الموجودة في بعضها فقط: {partial}" if partial else ""
    return {
        "fr": f"{count_fr} ({names}) ont {_fr(columns, 'colonne')} en commun, aux titres ou à l'ordre parfois différents{extra_fr}. En faire une seule liste, avec un champ {unit_fr} ?",
        "ar": f"{count_ar} ({names_ar}) {share_ar} في {_ar(columns, 'column', object_form=True)} قد تختلف عناوينها أو ترتيبها{extra_ar}. هل نجعلها قائمة واحدة مع حقل {unit_ar}؟",
    }


def status_colours(name: str, choices: list[dict[str, Any]], source: str) -> Explanation:
    shown = [item["value"] for item in choices[:5] if item["value"] is not None]
    how_fr = "des couleurs automatiques" if source == "conditionalFormat" else "des couleurs de cellule"
    how_ar = "ألوانا تلقائية" if source == "conditionalFormat" else "ألوان الخلايا"
    if not shown:
        return {
            "fr": f"« {_x(name)} » utilise {_fr(len(choices), 'couleur')} sans texte. Que veut dire chaque couleur ?",
            "ar": f"«{_x(name)}» يستعمل {_ar(len(choices), 'colour', object_form=True)} بدون نص. ماذا يعني كل لون؟",
        }
    return {
        "fr": f"« {_x(name)} » utilise {how_fr} pour {_fr(len(choices), 'état')} ({_list(shown)}). En faire des choix colorés ?",
        "ar": f"«{_x(name)}» يستعمل {how_ar} لتمييز الحالات، وعددها {len(choices)} ({_list(shown, '، ')}). هل نجعلها اختيارات ملونة؟",
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
    where_fr = f" dans « {_x(sheet)} »" if sheet else ""
    where_ar = f" في «{_x(sheet)}»" if sheet else ""
    if ref:
        where_fr += f", cellule {_x(ref)}"
        where_ar += f"، الخلية {_x(ref)}"
    times_fr = f" (× {count})" if count > 1 else ""
    times_ar = f" (× {count})" if count > 1 else ""
    return {
        "fr": f"Le fichier contient {fr}{where_fr}{times_fr}. Il ne sera pas repris dans l'application.",
        "ar": f"يحتوي الملف على {ar}{where_ar}{times_ar}. لن يُنقل إلى التطبيق.",
    }
