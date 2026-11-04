"""Darja and Arabizi words glossed in French before the model sees a label.

Small models know little Darja, so a label like "drahem khlas" gets its meaning alongside it. This
list is a hand-written start, not reviewed by a linguist; grow it from what real workbooks use.
"""

import re


GLOSSARY: dict[str, str] = {
    "drahem": "argent",
    "dra7em": "argent",
    "دراهم": "argent",
    "khlas": "paiement",
    "5las": "paiement",
    "خلاص": "paiement",
    "kridi": "crédit",
    "كريدي": "crédit",
    "dine": "dette",
    "dayn": "dette",
    "دين": "dette",
    "sel3a": "marchandise",
    "sal3a": "marchandise",
    "سلعة": "marchandise",
    "zboun": "client",
    "zbon": "client",
    "zaboun": "client",
    "زبون": "client",
    "lma3lem": "patron",
    "الراس": "patron",
    "chehria": "salaire",
    "شهرية": "salaire",
    "khedam": "employé",
    "5dam": "employé",
    "خدام": "employé",
    "ta3": "de",
    "num": "numéro",
    "tel": "téléphone",
    "tlf": "téléphone",
    "tilifoun": "téléphone",
    "تيليفون": "téléphone",
    "wilaya": "province",
    "dzd": "dinars",
}
WORD = re.compile(r"[\w؀-ۿ]+", re.UNICODE)


def gloss(label: str) -> str:
    """The label, with the meaning of any word the glossary knows: `khlas (paiement)`."""
    found = []
    for word in WORD.findall(label):
        meaning = GLOSSARY.get(word.casefold())
        if meaning and meaning not in found:
            found.append(meaning)
    return f"{label} ({', '.join(found)})" if found else label
