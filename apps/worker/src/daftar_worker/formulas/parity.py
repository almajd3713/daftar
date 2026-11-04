"""Recompute every formula in the engine and compare with the results stored in the file (R-19)."""

from collections import Counter
from datetime import datetime, time, timezone
from pathlib import Path
import tempfile
from typing import Any
import zipfile

from defusedxml import ElementTree
import olefile
from openpyxl.utils.datetime import from_excel, to_excel

from daftar_worker.census import analyse_formula
from daftar_worker.errors import WorkerError
from daftar_worker.evaluation.metrics import function_categories
from daftar_worker.formulas.engine import EngineError, EngineValue, EngineWorkbook
from daftar_worker.reader.convert import convert_to_xlsx
from daftar_worker.sheet.grid import REF, column_index


TOLERANCE = 1e-9
ONE_SECOND_IN_DAYS = 1 / 86400
# These can't match by design, so they are counted apart and left out of the score. NOW() stored
# the instant of the last calculation, which no frozen clock reproduces to the second. TODAY() is
# only as precise as the day, so the last-saved clock can check it.
UNCHECKABLE = {"RAND", "RANDBETWEEN", "RANDARRAY", "NOW"}


def last_saved(path: Path, source_format: str) -> datetime | None:
    """When the file was last saved. TODAY() and NOW() stored the clock of about that moment."""
    try:
        if source_format == "xls":
            with olefile.OleFileIO(str(path)) as ole:
                moment = ole.get_metadata().last_saved_time
            return moment.replace(tzinfo=timezone.utc) if isinstance(moment, datetime) else None
        with zipfile.ZipFile(path) as archive:
            for node in ElementTree.fromstring(archive.read("docProps/core.xml")):
                if node.tag.endswith("modified") and node.text:
                    return datetime.fromisoformat(node.text.replace("Z", "+00:00"))
    except Exception:
        return None
    return None


def _stored_serial(value: Any) -> float | None:
    """A stored date or time as a serial number, or None if it isn't one."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value)
    try:
        return float(to_excel(datetime.fromisoformat(text)))
    except (ValueError, TypeError):
        pass
    if text == "1900-02-29":
        return 60.0
    try:
        parts = [float(part) for part in text.split(":")]
        return (parts[0] * 3600 + parts[1] * 60 + (parts[2] if len(parts) > 2 else 0)) / 86400
    except (ValueError, IndexError):
        return None


def _engine_serial(result: EngineValue) -> float | None:
    if result.kind == "number":
        return float(result.value)
    if result.kind == "date":
        return float(to_excel(result.value))
    if result.kind == "time":
        moment: time = result.value
        return (moment.hour * 3600 + moment.minute * 60 + moment.second) / 86400
    return None


def _same_moment(result: EngineValue, stored: Any) -> bool:
    actual, expected = _engine_serial(result), _stored_serial(stored)
    return actual is not None and expected is not None and abs(actual - expected) <= ONE_SECOND_IN_DAYS


def values_match(result: EngineValue, stored: Any, stored_kind: str) -> bool:
    """R-19: numbers within a relative tolerance of 1e-9. Excel's own display is the reference."""
    if stored_kind == "d" or result.kind in ("date", "time"):
        return _same_moment(result, stored)
    if stored_kind == "e" or result.kind == "error":
        return stored_kind == "e" and result.kind == "error" and result.value == stored
    if stored_kind == "b" or result.kind == "boolean":
        return stored_kind == "b" and result.kind == "boolean" and bool(result.value) == bool(stored)
    if stored_kind == "n" and result.kind == "number":
        return abs(float(result.value) - float(stored)) <= TOLERANCE * max(abs(float(result.value)), abs(float(stored)))
    if stored is None and result.kind == "text":
        # A stored result of only spaces reads back as empty, so that's all we can compare.
        return not str(result.value).strip()
    if stored is None or result.kind == "empty":
        return (stored or "") == (result.value or "")
    return stored_kind == "s" and result.kind == "text" and result.value == stored


def reportable(result: EngineValue, stored: Any, kind: str, equal: bool) -> Any:
    """The value for `<id>.parity.json`, in the form the scorer compares with the stored result."""
    if equal:
        return stored
    if result.kind == "date":
        return result.value.isoformat()
    if result.kind == "time":
        return result.value.isoformat()
    if kind == "d" and result.kind == "number":
        try:
            moment = from_excel(result.value)
            return moment.isoformat() if isinstance(moment, (datetime, time)) else result.value
        except (ValueError, OverflowError, TypeError):
            return result.value
    return result.value


def _cause(result: EngineValue, stored_kind: str) -> str:
    if result.kind == "error":
        return f"engine{result.value}"
    if stored_kind == "e":
        return "excelErrorEngineValue"
    if stored_kind == "n" and result.kind == "number":
        return "differentNumber"
    if stored_kind == "s" and result.kind == "text":
        return "differentText"
    return f"differentType:{stored_kind}/{result.kind}"


def _engine_for(path: Path, source_format: str, clock: datetime | None, work_dir: str) -> EngineWorkbook:
    if source_format in ("xlsx", "xlsm"):
        return EngineWorkbook(str(path), clock)
    copy = Path(work_dir) / f"workbook.{source_format}"
    copy.write_bytes(path.read_bytes())
    return EngineWorkbook(str(convert_to_xlsx(copy, Path(work_dir))), clock)


def run_parity(path: str | Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Compare the engine with each stored result. `results` holds cell values: keep it private."""
    source = Path(path)
    source_format = snapshot["source"]["format"]
    clock = last_saved(source, source_format)
    tallies: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    category_equal: Counter[str] = Counter()
    causes: Counter[str] = Counter()
    wrong_functions: Counter[str] = Counter()
    results: list[dict[str, Any]] = []
    mismatches: dict[str, list[str]] = {}
    with tempfile.TemporaryDirectory(prefix="daftar-") as work_dir:
        try:
            engine = _engine_for(source, source_format, clock, work_dir)
        except (EngineError, WorkerError) as error:
            return {"results": [], "loadError": str(error) or type(error).__name__, "cells": 0, "equal": 0}
        for sheet in snapshot["sheets"]:
            for cell in sheet["cells"]:
                if "f" not in cell:
                    continue
                match = REF.match(cell["ref"])
                if match is None:
                    continue
                formula = cell["f"]
                try:
                    functions = set(analyse_formula(formula)["functions"])
                except Exception:
                    functions = set()
                if functions & UNCHECKABLE:
                    tallies["uncheckable"] += 1
                    continue
                try:
                    result = engine.value(sheet["name"], int(match.group(2)), column_index(match.group(1)))
                except EngineError:
                    result = EngineValue("error", "#ENGINE!")
                equal = values_match(result, cell["v"], cell["t"])
                tallies["cells"] += 1
                tallies["equal"] += equal
                for category in function_categories(formula):
                    categories[category] += 1
                    category_equal[category] += equal
                if not equal:
                    causes[_cause(result, cell["t"])] += 1
                    mismatches.setdefault(sheet["name"], []).append(cell["ref"])
                    wrong_functions.update(functions)
                results.append(
                    {
                        "sheet": sheet["name"],
                        "ref": cell["ref"],
                        "value": reportable(result, cell["v"], cell["t"], equal),
                    }
                )
    return {
        "results": results,
        "cells": tallies["cells"],
        "equal": tallies["equal"],
        "uncheckable": tallies["uncheckable"],
        "clock": clock.isoformat() if clock else None,
        "categories": dict(categories),
        "categoryEqual": dict(category_equal),
        "causes": dict(causes),
        "wrongFunctions": dict(wrong_functions),
        "mismatches": mismatches,
    }


def aggregate_parity(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine workbook results into a report that holds counts and function names only."""
    total: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    category_equal: Counter[str] = Counter()
    causes: Counter[str] = Counter()
    wrong: Counter[str] = Counter()
    perfect = 0
    for record in records:
        total["cells"] += record.get("cells", 0)
        total["equal"] += record.get("equal", 0)
        total["uncheckable"] += record.get("uncheckable", 0)
        categories.update(record.get("categories", {}))
        category_equal.update(record.get("categoryEqual", {}))
        causes.update(record.get("causes", {}))
        wrong.update(record.get("wrongFunctions", {}))
        perfect += bool(record.get("cells")) and record.get("cells") == record.get("equal")
    with_cells = sum(1 for record in records if record.get("cells"))
    return {
        "workbooks": with_cells,
        "workbooksAllEqual": perfect,
        "loadFailures": sum(1 for record in records if record.get("loadError")),
        "cells": total["cells"],
        "equal": total["equal"],
        "share": total["equal"] / total["cells"] if total["cells"] else None,
        "uncheckableCellsLeftOut": total["uncheckable"],
        "byCategory": {
            name: {
                "cells": count,
                "equal": category_equal[name],
                "share": category_equal[name] / count,
            }
            for name, count in sorted(categories.items())
        },
        "causes": dict(causes.most_common()),
        "functionsInWrongCells": dict(wrong.most_common(40)),
    }


def render_parity(report: dict[str, Any], skipped: dict[str, int]) -> str:
    lines = [
        "# Formula parity against Excel's stored results",
        "",
        f"- Formula cells compared: **{report['cells']}**",
        f"- Equal to Excel: **{report['equal']}** ({(report['share'] or 0) * 100:.2f}%)",
        f"- Workbooks compared: {report['workbooks']}, of which {report['workbooksAllEqual']} match on every cell",
        f"- Engine couldn't load: {report['loadFailures']}",
        f"- Left out, results not from Excel: {skipped.get('notExcel', 0)}",
        f"- Left out, no formulas: {skipped.get('noFormulas', 0)}",
        f"- Left out, unreadable: {skipped.get('unreadable', 0)}",
        f"- Left out, RAND or NOW, which can't match by design: {report['uncheckableCellsLeftOut']}",
        "",
        "These are not confidence intervals. `daftar eval` reports those on the labelled set.",
        "",
        "## By function category",
        "",
        "| Category | Cells | Equal | % |",
        "|---|---:|---:|---:|",
    ]
    for name, item in report["byCategory"].items():
        lines.append(f"| {name} | {item['cells']} | {item['equal']} | {item['share'] * 100:.2f} |")
    lines += ["", "## Why cells differ", "", "| Cause | Cells |", "|---|---:|"]
    lines += [f"| {name} | {count} |" for name, count in report["causes"].items()]
    lines += ["", "## Functions in cells that differ", "", "| Function | Calls |", "|---|---:|"]
    lines += [f"| {name} | {count} |" for name, count in report["functionsInWrongCells"].items()]
    return "\n".join(lines) + "\n"

