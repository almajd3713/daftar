"""What the model does to an analysis: names, ties and wording. Nothing else (local_llm.md §8).

Prompts hold profiles and samples, never whole sheets. Every answer is checked in code, and a bad
one leaves the rules' answer in place. `needsReview` marks a tie the model couldn't settle.
"""

from collections import Counter
from collections.abc import Callable
import copy
import re
from typing import Any

from openpyxl.utils import range_boundaries

from daftar_worker.analyser import confidence_level, explain
from daftar_worker.llm.client import LlmClient, LlmSettings, ModelUnavailable
from daftar_worker.llm.glossary import gloss
from daftar_worker.sheet.grid import Grid, column_index, text_of


PROMPT_VERSION = "1"
TIE_MARGIN = 0.15
TITLE_ROWS_ABOVE = 3
MAX_FIELDS_PER_PROMPT = 40
MAX_SAMPLES = 4
MAX_SAMPLE_CHARS = 40
REWORDED_KINDS = {"entityMerge", "relation", "periodUnion", "calculator", "statusColours"}
ARABIC = re.compile(r"[؀-ۿ]")
LATIN = re.compile(r"[A-Za-z\u00c0-\u024f]")
# Says nothing about what a row holds: "Ligne" is the model's way of not knowing.
GENERIC_NAMES = re.compile(
    r"^(ligne|lignes|row|rows|enregistrement|enregistrements|donn[ée]es?|سطر|أسطر|صف|صفوف|بيانات)(\s|$)", re.IGNORECASE
)
NUMBER = re.compile(r"[0-9]+(?:[.,][0-9]+)*")
QUOTED = re.compile(r"«\s*(.+?)\s*»")
CELL_RANGE = re.compile(r"\b[A-Z]{1,3}[0-9]+(?::[A-Z]{1,3}[0-9]+)?\b")
OUTCOME_MEANING = {
    "register": "a list of records such as students or clients",
    "ledger": "amounts recorded over time, such as payments",
    "tracker": "work items moving through statuses",
    "referenceList": "a lookup list that other sheets draw on",
    "formulaModel": "a calculation from input cells to results",
}
NAMING_SYSTEM = (
    "You name the parts of a small Algerian firm's spreadsheet for a business app. "
    "Give short, plain names a shop owner would use, in French and in Arabic. "
    "Keep the meaning of the column title. Don't invent facts. Answer with JSON only, in the given shape."
)
TIE_SYSTEM = (
    "You choose among the given options for a spreadsheet, from the description you are given. "
    "Answer with JSON only: {\"answer\": <one of the options>}."
)
WORDING_SYSTEM = (
    "You reword a sentence for a shop owner, in the same language, keeping it short and friendly. "
    "Keep every number, cell reference and every name in « » exactly as written. Add no facts, no numbers "
    "and no names. Answer with JSON only: {\"text\": <the sentence>}."
)


def _right(proposal: dict[str, Any]) -> int:
    return int(range_boundaries(proposal["range"])[2])


def _is_named(value: Any, arabic: bool) -> bool:
    if not isinstance(value, str) or not value.strip() or len(value) > 80:
        return False
    return bool(ARABIC.search(value)) if arabic else not ARABIC.search(value)


def _samples(grid: Grid, column: int, rows: list[int]) -> list[str]:
    seen: Counter[str] = Counter()
    for row in rows[:50]:
        cell = grid.get(row, column)
        if cell is not None:
            seen[text_of(cell)[:MAX_SAMPLE_CHARS]] += 1
    return [value for value, _ in seen.most_common(MAX_SAMPLES)]


def _name_table(client: LlmClient, grid: Grid, table: dict[str, Any], fields: list[dict[str, Any]]) -> None:
    proposal = table["proposal"]
    left, top, _, bottom = (int(part) for part in range_boundaries(proposal["dataRange"]))
    rows = list(range(top, bottom + 1))
    lines = []
    letters = []
    for finding in fields[:MAX_FIELDS_PER_PROMPT]:
        item = finding["proposal"]
        letters.append(item["column"])
        samples = ", ".join(_samples(grid, column_index(item["column"]), rows))
        lines.append(f"- column {item['column']}: title \"{gloss(item['name'])}\", type {item['type']}, examples: {samples}")
    if not letters:
        return
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["entity_fr", "entity_ar", "fields"],
        "properties": {
            "entity_fr": {"type": "string"},
            "entity_ar": {"type": "string"},
            "fields": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["column", "fr", "ar"],
                    "properties": {
                        "column": {"type": "string", "enum": letters},
                        "fr": {"type": "string"},
                        "ar": {"type": "string"},
                    },
                },
            },
        },
    }
    # The title often sits above a blank row, in a block of its own, so look just above the table.
    table_top = int(range_boundaries(proposal["range"])[1])
    titles = [
        " ".join(text_of(cell) for cell in grid.row_cells(row, 1, _right(proposal)) if cell.is_text)
        for row in range(max(1, table_top - TITLE_ROWS_ABOVE), table_top)
        if len(grid.row_cells(row, 1, _right(proposal))) == 1
    ]
    heading = f"Sheet \"{gloss(grid.name)}\"." + (f" Its title: \"{gloss(' / '.join(titles))}\"." if titles else "")
    prompt = (
        heading + " Columns:\n" + "\n".join(lines) + "\n\n"
        "Say what the rows hold, as a plural noun that comes from the title and columns; never Ligne or Row. "
        "Give that name (entity_fr, entity_ar, plural), and a French and Arabic name "
        'for each column: {"entity_fr": "...", "entity_ar": "...", "fields": [{"column": "A", "fr": "...", "ar": "..."}]}.'
    )

    def valid(answer: dict[str, Any]) -> bool:
        return (
            _is_named(answer["entity_fr"], False)
            and _is_named(answer["entity_ar"], True)
            and not GENERIC_NAMES.match(answer["entity_fr"].strip())
            and not GENERIC_NAMES.match(answer["entity_ar"].strip())
            and all(_is_named(item["fr"], False) and _is_named(item["ar"], True) for item in answer["fields"])
        )

    answer = client.ask("name_table", NAMING_SYSTEM, prompt, schema, valid)
    if answer is None:
        return
    proposal["entityLabel"] = {"fr": answer["entity_fr"].strip(), "ar": answer["entity_ar"].strip()}
    names = {item["column"]: item for item in answer["fields"]}
    for finding in fields:
        item = names.get(finding["proposal"]["column"])
        if item is not None:
            finding["proposal"]["label"] = {"fr": item["fr"].strip(), "ar": item["ar"].strip()}


def _describe_sheet(analysis: dict[str, Any], sheet: str) -> str:
    lines = [f"Sheet name: {gloss(sheet)}"]
    for finding in analysis["findings"]:
        if finding["sheet"] != sheet:
            continue
        if finding["kind"] == "fieldType":
            item = finding["proposal"]
            lines.append(f"- column \"{gloss(item['name'])}\": {item['type']}")
        elif finding["kind"] == "totalRow":
            lines.append(f"- a total row at {finding['proposal']['row']}")
        elif finding["kind"] == "statusColours":
            lines.append(f"- coloured statuses in column {finding['proposal']['column']}")
    return "\n".join(lines[:MAX_FIELDS_PER_PROMPT])


def _vote_score(agreement: float) -> float:
    """All votes agreeing is high confidence; a bare majority is low."""
    return round(0.55 + 0.35 * (agreement - 0.5) * 2, 3)


def _break_kind_ties(client: LlmClient, analysis: dict[str, Any]) -> None:
    entries = {entry["name"]: entry for entry in analysis["sheets"]}
    for finding in analysis["findings"]:
        if finding["kind"] != "sheetKind" or finding["proposal"]["outcome"] == "notConverted":
            continue
        close = [
            option["outcome"]
            for option in finding["alternatives"]
            if option["outcome"] in OUTCOME_MEANING and _margin(finding, option) <= TIE_MARGIN
        ]
        if not close:
            continue
        current = finding["proposal"]["outcome"]
        options = sorted({current, *close})
        meanings = "\n".join(f"- {name}: {OUTCOME_MEANING[name]}" for name in options)
        prompt = f"{_describe_sheet(analysis, finding['sheet'])}\n\nWhich best describes this sheet?\n{meanings}"
        vote = client.vote("sheet_kind", TIE_SYSTEM, prompt, options)
        if vote is None:
            finding["proposal"]["needsReview"] = True
            continue
        finding["proposal"]["outcome"] = vote.answer
        entries[finding["sheet"]]["outcome"] = vote.answer
        _set_confidence(finding, _vote_score(vote.agreement))


def _margin(finding: dict[str, Any], option: dict[str, Any]) -> float:
    return float(finding["proposal"]["score"]) - float(option["score"])


def _set_confidence(finding: dict[str, Any], score: float) -> None:
    finding["confidence"] = {"level": confidence_level(score), "score": score, "source": "votes"}


def _check_low_headers(client: LlmClient, analysis: dict[str, Any], grids: dict[str, Grid]) -> None:
    for finding in analysis["findings"]:
        if finding["kind"] != "header" or finding["confidence"]["level"] != "low":
            continue
        grid = grids[finding["sheet"]]
        left, top, right, bottom = (int(part) for part in range_boundaries(finding["proposal"]["table"]))
        def row_text(row: int) -> str:
            return " | ".join(text_of(cell)[:MAX_SAMPLE_CHARS] for cell in grid.row_cells(row, left, right))
        row = finding["proposal"]["rows"][-1]
        prompt = (
            f"Sheet \"{gloss(grid.name)}\". First row: {row_text(finding['proposal']['rows'][0])}\n"
            f"Next rows:\n{row_text(row + 1)}\n{row_text(min(row + 2, bottom))}\n\n"
            "Is the first row column titles (yes), or is it already a record of data (no)?"
        )
        vote = client.vote("header_check", TIE_SYSTEM, prompt, ["yes", "no"])
        if vote is None or vote.answer == "no":
            finding["proposal"]["needsReview"] = True
        else:
            _set_confidence(finding, _vote_score(vote.agreement))


def _check_possible_names(client: LlmClient, analysis: dict[str, Any]) -> None:
    """Only borderline spellings go to the model. It can remove a proposal, never merge anything."""
    for finding in analysis["findings"]:
        if finding["kind"] != "entityMerge":
            continue
        kept = []
        for cluster in finding["proposal"]["clusters"]:
            if cluster["match"] != "possible":
                kept.append(cluster)
                continue
            names = [item["value"] for item in cluster["variants"]]
            prompt = (
                f"Column \"{gloss(finding['proposal']['name'])}\" holds these spellings: {names}.\n"
                "Are they the same person or thing (same), or different ones (different)?"
            )
            vote = client.vote("same_name", TIE_SYSTEM, prompt, ["same", "different"])
            if vote is None or vote.answer == "same":
                kept.append(cluster)
        finding["proposal"]["clusters"] = kept


def keeps_facts(original: str, reworded: str) -> bool:
    """R-10: the model may reword but never adds facts. Numbers, cells and quoted names must match."""
    def facts(text: str) -> tuple[Counter[str], set[str], set[str]]:
        cells = set(CELL_RANGE.findall(text))
        without_cells = CELL_RANGE.sub(" ", text)
        return Counter(NUMBER.findall(without_cells)), cells, set(QUOTED.findall(text))

    before, after = facts(original), facts(reworded)
    return before[0] == after[0] and before[1] == after[1] and before[2] <= after[2]


def keeps_language(original: str, reworded: str) -> bool:
    """A real run turned an Arabic sentence into English, with every fact intact. Names can be in
    either script, so this compares what's left outside them."""

    def letters(text: str) -> tuple[int, int]:
        rest = QUOTED.sub(" ", text)
        return len(ARABIC.findall(rest)), len(LATIN.findall(rest))

    source_arabic, source_latin = letters(original)
    new_arabic, new_latin = letters(reworded)
    return (new_arabic >= new_latin) == (source_arabic >= source_latin)


def _reword(client: LlmClient, analysis: dict[str, Any]) -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["text"],
        "properties": {"text": {"type": "string"}},
    }
    for finding in analysis["findings"]:
        if finding["kind"] not in REWORDED_KINDS:
            continue
        for language in ("fr", "ar"):
            template = finding["explanation"][language]
            original = explain.plain(template)

            def valid(answer: dict[str, Any], source: str = original) -> bool:
                text = answer["text"]
                return bool(text.strip()) and keeps_facts(source, text) and keeps_language(source, text)

            answer = client.ask("reword", WORDING_SYSTEM, original, schema, valid)
            if answer is not None:
                finding["explanation"][language] = explain.isolate_again(template, answer["text"].strip())


def _fields_of(analysis: dict[str, Any], table: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in analysis["findings"]
        if item["kind"] == "fieldType"
        and item["sheet"] == table["sheet"]
        and item["proposal"]["table"] == table["proposal"]["range"]
    ]


def _series_followers(analysis: dict[str, Any]) -> dict[str, str]:
    """Later tabs of a series, mapped to its first tab: they're one table, so they get one name."""
    followers: dict[str, str] = {}
    for finding in analysis["findings"]:
        if finding["kind"] == "periodUnion":
            tabs = [tab["sheet"] for tab in finding["proposal"]["tabs"]]
            followers.update(dict.fromkeys(tabs[1:], tabs[0]))
    return followers


def _share_series_names(analysis: dict[str, Any], tables: list[dict[str, Any]], followers: dict[str, str]) -> None:
    by_sheet = {table["sheet"]: table for table in reversed(tables)}
    for table in tables:
        leader = by_sheet.get(followers.get(table["sheet"], ""))
        if leader is None or "entityLabel" not in leader["proposal"]:
            continue
        table["proposal"]["entityLabel"] = leader["proposal"]["entityLabel"]
        names = {
            item["proposal"]["name"]: item["proposal"].get("label")
            for item in _fields_of(analysis, leader)
        }
        for field in _fields_of(analysis, table):
            label = names.get(field["proposal"]["name"])
            if label:
                field["proposal"]["label"] = label


def apply_model(
    analysis: dict[str, Any],
    snapshot: dict[str, Any],
    settings: LlmSettings,
    progress: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Improve a rules-only analysis. If the model can't be reached, the result is wholly rules-only.

    It says so in `engine.modelUnavailable`, since a model was asked for and none of it is in here.
    Answers already received stay cached, so a rerun carries on from where this one stopped.
    """
    rules_only = copy.deepcopy(analysis)
    client = LlmClient(settings, PROMPT_VERSION)
    grids = {sheet["name"]: Grid(sheet) for sheet in snapshot["sheets"]}
    try:
        _break_kind_ties(client, analysis)
        _check_low_headers(client, analysis, grids)
        _check_possible_names(client, analysis)
        tables = [item for item in analysis["findings"] if item["kind"] == "table"]
        followers = _series_followers(analysis)
        for position, table in enumerate(tables, start=1):
            if table["sheet"] in followers:
                continue
            _name_table(client, grids[table["sheet"]], table, _fields_of(analysis, table))
            if progress:
                progress(position / len(tables))
        _share_series_names(analysis, tables, followers)
        if settings.reword:
            _reword(client, analysis)
    except ModelUnavailable:
        rules_only["engine"]["modelUnavailable"] = True
        return rules_only
    if client.stats.calls or client.stats.cached:
        analysis["engine"]["model"] = settings.model
        if client.quant:
            analysis["engine"]["quant"] = client.quant
    return analysis


__all__ = ["apply_model", "keeps_facts"]
