"""Read .csv files. Every value stays a string: `0550123456` must not lose its leading zero."""

import csv
import io
from pathlib import Path
from typing import Any

from openpyxl.utils import get_column_letter

from daftar_worker.errors import WorkerError
from daftar_worker.reader.limits import MAX_CELLS, MAX_FILE_BYTES


# Tried in this order on a tie, so French `1,5;2,5` splits on the semicolon.
DELIMITERS = ("\t", ";", "|", ",")

# A valid file under the size limit must not fail on the csv module's own, smaller field limit.
csv.field_size_limit(MAX_FILE_BYTES)


def _looks_arabic(data: bytes) -> bool:
    # cp1256 keeps the French accented letters where cp1252 has them (0xE0 and up). Most Arabic
    # letters sit at 0xC1-0xDF, where cp1252 has capital accented letters, rare in French text.
    high = [byte for byte in data if byte >= 0x80]
    if not high:
        return False
    return sum(0xC1 <= byte <= 0xDF for byte in high) / len(high) > 0.4


def decode(data: bytes) -> str:
    for bom, encoding in (
        (b"\xef\xbb\xbf", "utf-8-sig"),
        (b"\xff\xfe", "utf-16"),
        (b"\xfe\xff", "utf-16"),
    ):
        if data.startswith(bom):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError as error:
                raise WorkerError("unreadable", "bad byte for its byte order mark") from error
    if b"\x00" in data:
        raise WorkerError("unreadable", "NUL bytes in a text file")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    return data.decode("cp1256" if _looks_arabic(data) else "cp1252", errors="replace")


def detect_delimiter(text: str) -> str:
    lines = [line for line in text.splitlines()[:50] if line.strip()]
    best = ","
    best_score = 0.0
    for delimiter in DELIMITERS:
        try:
            rows = list(csv.reader(lines, delimiter=delimiter))
        except csv.Error:
            continue
        counts = [len(row) for row in rows if row]
        if not counts:
            continue
        common = max(set(counts), key=lambda count: (counts.count(count), count))
        if common < 2:
            continue
        score = counts.count(common) / len(counts)
        if score > best_score:
            best, best_score = delimiter, score
    return best


def read_csv(path: Path, sheet_name: str) -> list[dict[str, Any]]:
    text = decode(path.read_bytes())
    delimiter = detect_delimiter(text)
    cells: list[dict[str, Any]] = []
    last_row = 0
    last_column = 0
    try:
        for row_index, row in enumerate(
            csv.reader(io.StringIO(text, newline=""), delimiter=delimiter), start=1
        ):
            for column_index, value in enumerate(row, start=1):
                if value == "":
                    continue
                cells.append({"ref": f"{get_column_letter(column_index)}{row_index}", "v": value, "t": "s"})
                last_row = row_index
                last_column = max(last_column, column_index)
                if len(cells) > MAX_CELLS:
                    raise WorkerError("too_large", "more non-empty cells than the limit")
    except (csv.Error, ValueError) as error:
        raise WorkerError("unreadable", "the text isn't valid CSV") from error
    dimension = f"A1:{get_column_letter(last_column)}{last_row}" if cells else None
    return [
        {
            "name": sheet_name,
            "index": 0,
            "state": "visible",
            "protected": False,
            "rtl": False,
            "dimension": dimension,
            "hiddenRows": [],
            "hiddenColumns": [],
            "cells": cells,
            "merges": [],
            "validations": [],
            "conditionalFormats": [],
            "tables": [],
        }
    ]
