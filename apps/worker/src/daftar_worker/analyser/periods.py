"""R-8: tabs with the same columns, whose names give a period, are one entity with a period field."""

from collections import defaultdict
from dataclasses import dataclass
import re
from typing import Any

from openpyxl.utils import get_column_letter
from rapidfuzz import fuzz

from daftar_worker.analyser import explain
from daftar_worker.analyser.regions import Table
from daftar_worker.analyser.workbook_view import SheetView
from daftar_worker.sheet.names import fingerprint


MONTHS: dict[str, int] = {}
for number, spellings in enumerate(
    (
        ("janvier", "jan", "january", "جانفي", "يناير"),
        ("fevrier", "fev", "february", "feb", "فيفري", "فبراير"),
        ("mars", "mar", "march", "مارس"),
        ("avril", "avr", "april", "apr", "افريل", "ابريل"),
        ("mai", "may", "ماي", "مايو"),
        ("juin", "june", "jun", "جوان", "يونيو"),
        ("juillet", "juil", "july", "jul", "جويليه", "يوليو"),
        ("aout", "august", "aug", "اوت", "اغسطس"),
        ("septembre", "sept", "sep", "september", "سبتمبر"),
        ("octobre", "oct", "october", "اكتوبر"),
        ("novembre", "nov", "november", "نوفمبر"),
        ("decembre", "dec", "december", "ديسمبر"),
    ),
    start=1,
):
    for spelling in spellings:
        MONTHS[spelling] = number

YEAR = re.compile(r"\b(19[0-9]{2}|20[0-9]{2})\b")
SHORT_YEAR = re.compile(r"\b([0-9]{2})\b")
NUMERIC_MONTH = re.compile(r"\b(?:(20[0-9]{2})[-_/. ](0?[1-9]|1[0-2])|(0?[1-9]|1[0-2])[-_/. ](20[0-9]{2}))\b")
QUARTER = re.compile(r"\b(?:t|q|trim(?:estre)?)\s*([1-4])\b|\b([1-4])\s*(?:er|e|eme|ème)?\s*trim", re.IGNORECASE)
SIMILAR_COLUMNS = 80
# Share of the narrower tab's columns that must be known, and of the wider tab's: a tab may gain a
# column or two, but a list of two columns isn't the same table as one of ten.
SHARED_OF_NARROWER = 0.8
SHARED_OF_WIDER = 0.5
MIN_TABS = 2


@dataclass(frozen=True)
class Period:
    granularity: str  # month, quarter or year
    year: int | None
    number: int | None  # The month or the quarter.

    @property
    def text(self) -> str:
        """YYYY-MM, YYYY-Qn or YYYY when the year is known, else --MM or --Qn."""
        year = str(self.year) if self.year else "-"
        if self.granularity == "year":
            return year
        if self.granularity == "quarter":
            return f"{year}-Q{self.number}"
        return f"{year}-{self.number:02d}"

    @property
    def order(self) -> tuple[int, int]:
        return (self.year or 0, self.number or 0)


def parse_period(name: str) -> Period | None:
    """A sheet name as a period: Janvier 2026, جانفي, 2026-01, T1 2025, 2024."""
    numeric = NUMERIC_MONTH.search(name)
    if numeric:
        return Period("month", int(numeric.group(1) or numeric.group(4)), int(numeric.group(2) or numeric.group(3)))
    year_match = YEAR.search(name)
    year = int(year_match.group(1)) if year_match else None
    for word in fingerprint(re.sub(r"[-_/.]", " ", name)).split():
        month = MONTHS.get(word)
        if month is not None:
            short = SHORT_YEAR.search(name)
            if year is None and short:
                year = 2000 + int(short.group(1))
            return Period("month", year, month)
    quarter = QUARTER.search(name)
    if quarter:
        return Period("quarter", year, int(quarter.group(1) or quarter.group(2)))
    remainder = YEAR.sub("", name).strip(" -_/.")
    if year is not None and len(remainder) <= 12:
        return Period("year", year, None)
    return None


def _main_table(view: SheetView) -> tuple[int, Table] | None:
    tables = view.layout.tables
    if not tables:
        return None
    index = max(range(len(tables)), key=lambda item: tables[item].rect.width * tables[item].rect.height)
    return index, tables[index]


def _signature(labels: dict[int, str]) -> str:
    return " | ".join(fingerprint(label) for _, label in sorted(labels.items()))


def _without_periods(label: str) -> str:
    """A header without its dates: "Etudiants 2011/2012" and "Etudiants 2012/2013" are one column."""
    return " ".join(word for word in fingerprint(label).split() if word not in MONTHS and not any(char.isdigit() for char in word))


def align_columns(known: list[str], labels: dict[int, str]) -> dict[int, int]:
    """Which of the known columns each of a tab's columns is, by name and never by position.

    Same name first, then the same name but for its dates, then the closest. Each is used once.
    """
    matched: dict[int, int] = {}
    free = list(range(len(known)))
    for form in (fingerprint, _without_periods):
        for column, label in sorted(labels.items()):
            wanted = form(label)
            if column in matched or not wanted:
                continue
            place = next((item for item in free if form(known[item]) == wanted), None)
            if place is not None:
                matched[column] = place
                free.remove(place)
    close = []
    for column, label in labels.items():
        if column not in matched and _without_periods(label):
            for place in free:
                if _without_periods(known[place]):
                    score = fuzz.token_sort_ratio(_without_periods(label), _without_periods(known[place]))
                    if score >= SIMILAR_COLUMNS:
                        close.append((-score, column, place))
    for _, column, place in sorted(close):
        if column not in matched and place in free:
            matched[column] = place
            free.remove(place)
    return matched


def _same_table(left: dict[int, str], right: dict[int, str]) -> bool:
    shared = len(align_columns([label for _, label in sorted(left.items())], right))
    narrower, wider = sorted((len(left), len(right)))
    return shared >= SHARED_OF_NARROWER * narrower and shared >= SHARED_OF_WIDER * wider


def _series_columns(ordered: list[Any]) -> tuple[list[str], list[list[dict[str, Any]]]]:
    """The columns of a whole series, in order of first appearance, and each tab's own layout."""
    columns: list[str] = []
    layouts = []
    for tab in ordered:
        labels = tab[3]
        matched = align_columns(columns, labels)
        layout = []
        for column, label in sorted(labels.items()):
            if column not in matched:
                matched[column] = len(columns)
                columns.append(label)
            layout.append({"column": get_column_letter(column), "header": label, "position": matched[column]})
        layouts.append(layout)
    return columns, layouts


def period_findings(make: Any, views: list[SheetView]) -> list[dict[str, Any]]:
    tabs = []
    for view in views:
        if view.outcome == "notConverted":
            continue
        period = parse_period(view.grid.name)
        main = _main_table(view)
        if period is None or main is None:
            continue
        index, table = main
        labels = view.labels[index]
        if labels:
            tabs.append((view, period, table, labels))

    groups: list[list[Any]] = []
    for tab in tabs:
        for group in groups:
            first = group[0]
            if first[1].granularity == tab[1].granularity and _same_table(first[3], tab[3]):
                group.append(tab)
                break
        else:
            groups.append([tab])

    findings = []
    for group in groups:
        by_period = defaultdict(list)
        for tab in group:
            by_period[tab[1].text].append(tab)
        if len(group) < MIN_TABS or len(by_period) < MIN_TABS:
            continue
        ordered = sorted(group, key=lambda tab: tab[1].order)
        first = ordered[0]
        identical = all(_signature(tab[3]) == _signature(first[3]) for tab in group)
        all_years = all(tab[1].year is not None or tab[1].granularity == "year" for tab in group)
        score = 0.9 if identical and all_years else (0.75 if identical else 0.65)
        names = [tab[0].grid.name for tab in ordered]
        columns, layouts = _series_columns(ordered)
        in_every_tab = sum(1 for place in range(len(columns)) if all(any(item["position"] == place for item in layout) for layout in layouts))
        findings.append(
            make(
                "periodUnion",
                first[0].grid.name,
                [first[2].rect.a1],
                {
                    "granularity": first[1].granularity,
                    "tabs": [
                        {"sheet": tab[0].grid.name, "period": tab[1].text, "table": tab[2].rect.a1, "columns": layout}
                        for tab, layout in zip(ordered, layouts, strict=True)
                    ],
                    "columns": columns,
                    "identicalColumns": identical,
                },
                score,
                explain.period_union(names, first[1].granularity, in_every_tab, len(columns) - in_every_tab, identical),
                extra="|".join(names),
            )
        )
    return findings


__all__ = ["Period", "align_columns", "parse_period", "period_findings"]
