"""R-8: tabs with the same columns, whose names give a period, are one entity with a period field."""

from collections import defaultdict
from dataclasses import dataclass
import re
from typing import Any

from rapidfuzz import fuzz

from daftar_worker.analyser import explain
from daftar_worker.analyser.names import fingerprint
from daftar_worker.analyser.regions import Table
from daftar_worker.analyser.workbook_view import SheetView


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


def _same_columns(left: list[str], right: list[str]) -> float:
    return float(fuzz.token_sort_ratio(" ".join(left), " ".join(right)))


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
            tabs.append((view, period, table, labels, [fingerprint(label) for _, label in sorted(labels.items())]))

    groups: list[list[Any]] = []
    for tab in tabs:
        for group in groups:
            first = group[0]
            same_kind = first[1].granularity == tab[1].granularity
            if same_kind and _same_columns(first[4], tab[4]) >= SIMILAR_COLUMNS:
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
        findings.append(
            make(
                "periodUnion",
                first[0].grid.name,
                [first[2].rect.a1],
                {
                    "granularity": first[1].granularity,
                    "tabs": [{"sheet": tab[0].grid.name, "period": tab[1].text, "table": tab[2].rect.a1} for tab in ordered],
                    "columns": [label for _, label in sorted(first[3].items())],
                    "identicalColumns": identical,
                },
                score,
                explain.period_union(names, first[1].granularity, len(first[3])),
                extra="|".join(names),
            )
        )
    return findings


__all__ = ["Period", "parse_period", "period_findings"]
