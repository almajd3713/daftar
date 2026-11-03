"""Turn any supported file into a C-1 workbook snapshot."""

import hashlib
from pathlib import Path, PureWindowsPath
import tempfile
from typing import Any
import zipfile

from daftar_worker.errors import WorkerError
from daftar_worker.reader.convert import convert_to_xlsx
from daftar_worker.reader.legacy import (
    LegacyFacts,
    inspect_ods,
    inspect_xls,
    is_encrypted_ooxml,
)
from daftar_worker.reader.limits import MAX_FILE_BYTES
from daftar_worker.reader.raw import RawPackage, copy_without_pivot_links, inspect_package
from daftar_worker.reader.stored import apply_stored_results, ods_lookup, xls_lookup
from daftar_worker.reader.text import read_csv
from daftar_worker.reader.xlsx import read_workbook


SUPPORTED = {".xlsx": "xlsx", ".xlsm": "xlsm", ".xls": "xls", ".ods": "ods", ".csv": "csv"}
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = b"PK\x03\x04"


def results_from(sheets: list[dict[str, Any]], application: str | None, automatic: bool) -> str:
    """Who produced the stored results. `excel` only if Excel saved in automatic mode."""
    if not any("f" in cell for sheet in sheets for cell in sheet["cells"]):
        return "none"
    is_excel = (application or "").startswith("Microsoft Excel")
    return "excel" if is_excel and automatic else "other"


def _read_package(path: Path) -> tuple[RawPackage, dict[str, Any]]:
    try:
        package = inspect_package(str(path))
        with tempfile.TemporaryDirectory(prefix="daftar-") as work_dir:
            stripped = str(Path(work_dir) / "workbook.xlsx")
            has_pivots = copy_without_pivot_links(str(path), stripped)
            return package, read_workbook(stripped if has_pivots else str(path), package)
    except WorkerError:
        raise
    except Exception as error:  # A damaged file can fail in many ways inside these parsers.
        raise WorkerError("unreadable", type(error).__name__) from error


def _restore_results(path: Path, kind: str, sheets: list[dict[str, Any]]) -> bool:
    """Put the original's stored results back. False if a formula cell has none to restore."""
    try:
        if kind == "xls":
            lookup, date_mode = xls_lookup(path)
            return apply_stored_results(sheets, lookup, date_mode)
        return apply_stored_results(sheets, ods_lookup(path))
    except Exception as error:
        raise WorkerError("unreadable", type(error).__name__) from error


def _inspect_legacy(path: Path, kind: str) -> LegacyFacts:
    try:
        encrypted, facts = inspect_xls(path) if kind == "xls" else inspect_ods(path)
    except Exception as error:
        raise WorkerError("unreadable", type(error).__name__) from error
    if encrypted:
        raise WorkerError("protected")
    return facts


def _check_signature(path: Path, kind: str) -> None:
    with path.open("rb") as stream:
        magic = stream.read(8)
    if magic == OLE_MAGIC and kind != "xls":
        try:
            encrypted = is_encrypted_ooxml(path)
        except Exception as error:
            raise WorkerError("unreadable", type(error).__name__) from error
        if encrypted:
            raise WorkerError("protected")
    if kind == "xls" and magic != OLE_MAGIC:
        raise WorkerError("unreadable", "not an OLE file")
    if kind in ("xlsx", "xlsm", "ods") and not zipfile.is_zipfile(path):
        raise WorkerError("unreadable", "not a zip file")


def read_file(path: str | Path, file_name: str | None = None) -> dict[str, Any]:
    """Read a workbook into a snapshot. `file_name` is the name to record; it's never opened."""
    source = Path(path)
    name = PureWindowsPath(file_name or source.name).name
    kind = SUPPORTED.get(Path(name).suffix.lower())
    if kind is None:
        raise WorkerError("unsupported_format", "unknown extension")
    try:
        size = source.stat().st_size
    except OSError as error:
        raise WorkerError("unreadable", "can't open the file") from error
    if size > MAX_FILE_BYTES:
        raise WorkerError("too_large", "file is larger than the limit")
    _check_signature(source, kind)
    sha256 = hashlib.sha256(source.read_bytes()).hexdigest()

    info: dict[str, Any] = {"fileName": name, "sha256": sha256, "format": kind}
    if kind == "csv":
        sheets = read_csv(source, Path(name).stem)
        return _snapshot(info, None, "none", sheets, [], [])

    if kind in ("xlsx", "xlsm"):
        package, workbook = _read_package(source)
        application, automatic = package.application, package.automatic_calc
        unsupported = package.unsupported
    else:
        facts = _inspect_legacy(source, kind)
        with tempfile.TemporaryDirectory(prefix="daftar-") as work_dir:
            copy = Path(work_dir) / f"workbook.{kind}"
            copy.write_bytes(source.read_bytes())
            package, workbook = _read_package(convert_to_xlsx(copy, Path(work_dir)))
        restored = _restore_results(source, kind, workbook["sheets"])
        application = facts.application
        # A value we couldn't restore is LibreOffice's, so the file can't serve as the reference.
        automatic = facts.automatic_calc and restored
        unsupported = package.unsupported
        if facts.has_macros and not any(item["kind"] == "macro" for item in unsupported):
            unsupported = [{"kind": "macro"}, *unsupported]
        info["convertedFrom"] = kind

    source_results = results_from(workbook["sheets"], application, automatic)
    if kind == "ods" and source_results == "excel":
        source_results = "other"  # An .ods file was never saved by Excel with its own results.
    return _snapshot(
        info, application, source_results, workbook["sheets"], workbook["definedNames"], unsupported
    )


def _snapshot(
    info: dict[str, Any],
    application: str | None,
    source_results: str,
    sheets: list[dict[str, Any]],
    defined_names: list[dict[str, Any]],
    unsupported: list[dict[str, str]],
) -> dict[str, Any]:
    source = dict(info)
    if application:
        source["application"] = application
    source["resultsFrom"] = source_results
    return {
        "snapshotVersion": 1,
        "source": source,
        "sheets": sheets,
        "definedNames": defined_names,
        "unsupported": unsupported,
    }
