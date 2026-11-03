"""`daftar census`: count workbook features over folders of files (R-26).

The output holds counts and function names, never cell values, so it's safe to keep and share.
"""

from collections import Counter
from collections.abc import Iterable, Iterator
import os
from pathlib import Path
import statistics
from typing import Any

from openpyxl.formula import Tokenizer

from daftar_worker.errors import WorkerError
from daftar_worker.reader import SUPPORTED, read_file


LOOKUP = {"VLOOKUP", "HLOOKUP", "XLOOKUP", "LOOKUP", "INDEX", "MATCH", "XMATCH"}
VOLATILE = {"TODAY", "NOW", "RAND", "RANDBETWEEN", "OFFSET", "INDIRECT", "CELL", "INFO"}
DYNAMIC_ARRAY = {"FILTER", "UNIQUE", "SORT", "SORTBY", "SEQUENCE", "RANDARRAY", "XLOOKUP", "XMATCH",
                 "TEXTSPLIT", "VSTACK", "HSTACK", "TAKE", "DROP", "CHOOSECOLS", "CHOOSEROWS",
                 "BYROW", "BYCOL", "MAP", "REDUCE", "SCAN", "MAKEARRAY"}  # fmt: skip
LET_LAMBDA = {"LET", "LAMBDA"}
COVERAGE_MARKS = (0.8, 0.9, 0.95, 0.99)

# Yes-or-no features reported as a share of workbooks.
FLAGS = (
    "multipleSheets", "hiddenSheets", "hiddenRowsOrColumns", "protectedSheets", "merges", "validations",
    "conditionalFormats", "tables", "definedNames", "comments", "formulas", "crossSheetFormulas",
    "arrayFormulas", "errorValues", "macros", "pivots", "charts", "images", "shapes",
    "externalLinks", "otherUnsupported",
)  # fmt: skip
# Reported as a share of the workbooks that use formulas; OQ-3 is decided on this denominator.
FORMULA_FLAGS = ("lookupFunctions", "volatileFunctions", "dynamicArrayFunctions", "letOrLambda",
                 "passingFormulas")  # fmt: skip


def iter_files(paths: Iterable[str | Path]) -> Iterator[Path]:
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            yield path
            continue
        for directory, subdirs, names in os.walk(path):
            subdirs.sort()
            for name in sorted(names):
                if Path(name).suffix.lower() in SUPPORTED and not name.startswith("~$"):
                    yield Path(directory) / name


def analyse_formula(formula: str) -> dict[str, Any]:
    """Return the functions a formula calls and what its references look like."""
    text = formula[1:-1] if formula.startswith("{") and formula.endswith("}") else formula
    tokens = Tokenizer(text).items
    functions = [
        token.value[:-1].upper()
        for token in tokens
        if token.type == "FUNC" and token.subtype == "OPEN"
    ]
    ranges = [
        token.value for token in tokens if token.type == "OPERAND" and token.subtype == "RANGE"
    ]
    meaningful = [token for token in tokens if token.type != "WHITE-SPACE"]
    return {
        "functions": functions,
        "crossSheet": any("!" in value for value in ranges),
        "passing": len(meaningful) == 1 and bool(ranges),
    }


def census_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    functions: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    sheets = snapshot["sheets"]
    rows_per_sheet: list[int] = []
    for sheet in sheets:
        counts["hiddenSheets"] += sheet["state"] != "visible"
        counts["hiddenRowsOrColumns"] += bool(sheet["hiddenRows"] or sheet["hiddenColumns"])
        counts["protectedSheets"] += bool(sheet["protected"])
        counts["merges"] += len(sheet["merges"])
        counts["validations"] += len(sheet["validations"])
        counts["conditionalFormats"] += len(sheet["conditionalFormats"])
        counts["tables"] += len(sheet["tables"])
        rows_per_sheet.append(_row_count(sheet["dimension"]))
        for cell in sheet["cells"]:
            counts["nonEmptyCells"] += cell["v"] is not None or "f" in cell
            counts["comments"] += "comment" in cell
            counts["errorValues"] += cell["t"] == "e"
            formula = cell.get("f")
            if formula is None:
                continue
            counts["formulas"] += 1
            counts["arrayFormulas"] += formula.startswith("{")
            try:
                facts = analyse_formula(formula)
            except Exception:
                counts["unparsedFormulas"] += 1
                continue
            functions.update(facts["functions"])
            counts["crossSheetFormulas"] += facts["crossSheet"]
            counts["passingFormulas"] += facts["passing"]
    used = set(functions)
    counts["definedNames"] = len(snapshot["definedNames"])
    counts["lookupFunctions"] = sum(functions[name] for name in used & LOOKUP)
    counts["volatileFunctions"] = sum(functions[name] for name in used & VOLATILE)
    counts["dynamicArrayFunctions"] = sum(functions[name] for name in used & DYNAMIC_ARRAY)
    counts["letOrLambda"] = sum(functions[name] for name in used & LET_LAMBDA)
    unsupported = Counter(item["kind"] for item in snapshot["unsupported"])
    counts["macros"] = unsupported["macro"]
    counts["pivots"] = unsupported["pivot"]
    counts["charts"] = unsupported["chart"]
    counts["images"] = unsupported["image"]
    counts["shapes"] = unsupported["shape"]
    counts["externalLinks"] = unsupported["externalLink"]
    counts["otherUnsupported"] = unsupported["other"]
    counts["multipleSheets"] = int(len(sheets) > 1)
    return {
        "format": snapshot["source"]["format"],
        "resultsFrom": snapshot["source"]["resultsFrom"],
        "application": snapshot["source"].get("application"),
        "sheets": len(sheets),
        "maxRowsPerSheet": max(rows_per_sheet, default=0),
        "counts": {name: counts[name] for name in sorted(counts)},
        "functions": dict(sorted(functions.items())),
    }


def _row_count(dimension: str | None) -> int:
    if not dimension:
        return 0
    from openpyxl.utils import range_boundaries

    _, low, _, high = range_boundaries(dimension)
    return int(high) - int(low) + 1


def function_coverage(functions: Counter[str]) -> dict[str, int]:
    """How many distinct functions it takes to cover each share of all function calls."""
    total = sum(functions.values())
    marks: dict[str, int] = {}
    if total == 0:
        return marks
    running = 0
    ordered = sorted(functions.items(), key=lambda item: (-item[1], item[0]))
    for position, (_, count) in enumerate(ordered, start=1):
        running += count
        for mark in COVERAGE_MARKS:
            key = f"{round(mark * 100)}%"
            # Compare in integers so 0.8 * 5 can't land just above 4 through float rounding.
            if key not in marks and running * 100 >= round(mark * 100) * total:
                marks[key] = position
    return marks


def _share(count: int, total: int) -> dict[str, Any]:
    return {"workbooks": count, "percent": round(100 * count / total, 1) if total else 0.0}


def aggregate(workbooks: list[dict[str, Any]], errors: Counter[str]) -> dict[str, Any]:
    total = len(workbooks)
    functions: Counter[str] = Counter()
    workbooks_using: Counter[str] = Counter()
    for record in workbooks:
        functions.update(record["functions"])
        workbooks_using.update(record["functions"].keys())
    with_formulas = sum(1 for record in workbooks if record["counts"].get("formulas", 0) > 0)
    sheets = [record["sheets"] for record in workbooks]
    rows = [record["maxRowsPerSheet"] for record in workbooks]
    top = sorted(functions.items(), key=lambda item: (-item[1], item[0]))[:30]
    call_total = sum(functions.values())
    return {
        "workbooks": total,
        "unreadable": dict(sorted(errors.items())),
        "formats": dict(sorted(Counter(record["format"] for record in workbooks).items())),
        "resultsFrom": dict(sorted(Counter(record["resultsFrom"] for record in workbooks).items())),
        "applications": dict(
            sorted(Counter(record["application"] or "unknown" for record in workbooks).items())
        ),
        "features": {
            name: _share(sum(1 for r in workbooks if r["counts"].get(name, 0) > 0), total)
            for name in FLAGS
        },
        "formulaFeatures": {
            name: _share(sum(1 for r in workbooks if r["counts"].get(name, 0) > 0), with_formulas)
            for name in FORMULA_FLAGS
        },
        "workbooksWithFormulas": with_formulas,
        "sheetsPerWorkbook": _summary(sheets),
        "maxRowsPerWorkbook": _summary(rows),
        "functionCalls": call_total,
        "distinctFunctions": len(functions),
        "functionCoverage": function_coverage(functions),
        "topFunctions": [
            {
                "name": name,
                "calls": calls,
                "percent": round(100 * calls / call_total, 1),
                "workbooks": workbooks_using[name],
            }
            for name, calls in top
        ],
    }


def _summary(values: list[int]) -> dict[str, float]:
    if not values:
        return {"median": 0, "mean": 0, "max": 0}
    return {
        "median": statistics.median(values),
        "mean": round(statistics.fmean(values), 2),
        "max": max(values),
    }


def run_census(paths: Iterable[str | Path]) -> dict[str, Any]:
    """Count features per workbook and in aggregate. Byte-identical files count once."""
    workbooks: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    errors: Counter[str] = Counter()
    seen: dict[str, str] = {}
    duplicates = 0
    for path in iter_files(paths):
        try:
            snapshot = read_file(path)
        except WorkerError as error:
            errors[error.code] += 1
            failures.append({"file": str(path), "code": error.code})
            continue
        sha256 = snapshot["source"]["sha256"]
        if sha256 in seen:
            duplicates += 1
            continue
        seen[sha256] = str(path)
        workbooks.append({"file": str(path), "sha256": sha256, **census_snapshot(snapshot)})
    return {
        "censusVersion": 1,
        "aggregate": {**aggregate(workbooks, errors), "duplicatesSkipped": duplicates},
        "workbooks": workbooks,
        "failures": failures,
    }


def render_markdown(census: dict[str, Any]) -> str:
    data = census["aggregate"]
    lines = [
        "# Workbook census",
        "",
        f"- Workbooks counted: **{data['workbooks']}**",
        f"- Identical copies skipped: {data['duplicatesSkipped']}",
        f"- Couldn't be read: {sum(data['unreadable'].values())} {data['unreadable'] or ''}".rstrip(),
        f"- Formats: {data['formats']}",
        f"- Stored results from: {data['resultsFrom']}",
        f"- Last saved by: {data['applications']}",
        f"- Sheets per workbook: {data['sheetsPerWorkbook']}",
        f"- Most rows on a sheet, per workbook: {data['maxRowsPerWorkbook']}",
        "",
        "## Features, share of all workbooks",
        "",
        "| Feature | Workbooks | % |",
        "|---|---:|---:|",
    ]
    for name, share in data["features"].items():
        lines.append(f"| {name} | {share['workbooks']} | {share['percent']} |")
    lines += [
        "",
        f"## Features, share of the {data['workbooksWithFormulas']} workbooks with formulas",
        "",
        "| Feature | Workbooks | % |",
        "|---|---:|---:|",
    ]
    for name, share in data["formulaFeatures"].items():
        lines.append(f"| {name} | {share['workbooks']} | {share['percent']} |")
    lines += [
        "",
        "## Function coverage",
        "",
        f"{data['functionCalls']} calls to {data['distinctFunctions']} distinct functions.",
        "",
        "| Share of calls | Distinct functions needed |",
        "|---:|---:|",
    ]
    for mark, needed in data["functionCoverage"].items():
        lines.append(f"| {mark} | {needed} |")
    lines += ["", "| Function | Calls | % of calls | Workbooks |", "|---|---:|---:|---:|"]
    for item in data["topFunctions"]:
        lines.append(f"| {item['name']} | {item['calls']} | {item['percent']} | {item['workbooks']} |")
    return "\n".join(lines) + "\n"
