"""WP-4's labelling screen: correct a workbook's label beside the workbook. It serves this machine only."""

from collections import OrderedDict
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from openpyxl.utils import column_index_from_string

from daftar_worker.analyser import analyze_snapshot
from daftar_worker.errors import WorkerError
from daftar_worker.evaluation.labels import (
    EvalError,
    ManifestRow,
    check_against_workbook,
    check_label,
    read_manifest,
    schema_problems,
)
from daftar_worker.evaluation.run import draft_label, workbook_path
from daftar_worker.reader import read_file


HOST = "127.0.0.1"
SNAPSHOTS_KEPT = 3
MAX_BEAT_SECONDS = 60
REF = re.compile(r"([A-Z]+)([0-9]+)")
POLICY = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'"
# What a person edits. The rest stays as it was read from the workbook, above all the formula results.
EDITABLE = ("status", "workbook", "sheets", "relations")


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(text)
    os.replace(temporary, path)


def _compact_sheet(sheet: dict[str, Any]) -> dict[str, Any]:
    cells = []
    for cell in sheet["cells"]:
        match = REF.fullmatch(cell["ref"])
        if match is None:
            continue
        style = cell.get("style") or {}
        cells.append(
            {
                "r": int(match.group(2)),
                "c": column_index_from_string(match.group(1)),
                "v": cell.get("v"),
                "t": cell.get("t"),
                "f": cell.get("f"),
                "fmt": cell.get("fmt"),
                "fill": style.get("fill"),
                "bold": style.get("bold"),
                "note": cell.get("comment"),
            }
        )
    return {
        "name": sheet["name"],
        "state": sheet["state"],
        "dimension": sheet["dimension"],
        "hiddenRows": sheet["hiddenRows"],
        "hiddenColumns": sheet["hiddenColumns"],
        "merges": sheet["merges"],
        "listRanges": [range_ for item in sheet["validations"] if item["type"] == "list" for range_ in item["ranges"]],
        "colourRanges": [range_ for item in sheet["conditionalFormats"] for range_ in item["ranges"]],
        "cells": cells,
    }


class _Store:
    def __init__(self, labels_dir: Path, manifest_path: Path, who: str) -> None:
        self.labels_dir = labels_dir
        self.manifest_path = manifest_path
        self.who = who
        self.times_path = manifest_path.parent / "private" / "label-times.json"
        self.lock = threading.RLock()
        self.snapshots: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def row(self, workbook_id: str) -> ManifestRow:
        # The manifest is the only way in: an id never reaches the file system unless it's listed there.
        for row in read_manifest(self.manifest_path):
            if row.id == workbook_id:
                return row
        raise HTTPException(404, "not in the manifest")

    def snapshot(self, row: ManifestRow) -> dict[str, Any]:
        with self.lock:
            kept = self.snapshots.get(row.id)
            if kept is not None:
                self.snapshots.move_to_end(row.id)
                return kept
        path = workbook_path(self.manifest_path, row)
        if path is None:
            raise HTTPException(404, f"no file for {row.id} in eval/workbooks or eval/private")
        try:
            snapshot = read_file(path)
        except WorkerError as error:
            raise HTTPException(422, f"{error.code}: {error.detail}") from error
        if snapshot["source"]["sha256"] != row.sha256:
            raise HTTPException(422, "the file doesn't match the sha256 in the manifest")
        with self.lock:
            self.snapshots[row.id] = snapshot
            while len(self.snapshots) > SNAPSHOTS_KEPT:
                self.snapshots.popitem(last=False)
        return snapshot

    def path_of(self, row: ManifestRow) -> Path:
        return self.labels_dir / f"{row.id}.json"

    def label(self, row: ManifestRow) -> dict[str, Any]:
        """The label, starting one if there's none. Only dev starts from the analyser's guesses."""
        path = self.path_of(row)
        with self.lock:
            if path.exists():
                label: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
                return label
        snapshot = self.snapshot(row)
        analysis = analyze_snapshot(snapshot) if row.split == "dev" else None
        draft = draft_label(row, snapshot, analysis)
        with self.lock:
            if not path.exists():  # Existing labels are never overwritten.
                self.write(row, draft)
        return draft

    def write(self, row: ManifestRow, label: dict[str, Any]) -> None:
        _write_atomic(self.path_of(row), json.dumps(label, ensure_ascii=False, indent=1) + "\n")

    def times(self) -> dict[str, dict[str, int]]:
        if not self.times_path.exists():
            return {}
        times: dict[str, dict[str, int]] = json.loads(self.times_path.read_text(encoding="utf-8"))
        return times

    def add_time(self, workbook_id: str, seconds: int) -> None:
        with self.lock:
            times = self.times()
            entry = times.setdefault(workbook_id, {})
            entry[self.who] = entry.get(self.who, 0) + seconds
            _write_atomic(self.times_path, json.dumps(times, ensure_ascii=False, indent=1) + "\n")

    def status_of(self, row: ManifestRow) -> str:
        path = self.path_of(row)
        if not path.exists():
            return "new"
        try:
            return str(json.loads(path.read_text(encoding="utf-8")).get("status"))
        except ValueError:
            return "broken"


def _public_label(label: dict[str, Any]) -> dict[str, Any]:
    """A workbook can hold 100,000 formulas, and nobody edits their results here."""
    return {**{key: value for key, value in label.items() if key != "formulas"}, "formulaCount": len(label["formulas"])}


def create_label_app(labels_dir: Path, manifest_path: Path, who: str, port: int) -> FastAPI:
    store = _Store(labels_dir, manifest_path, who)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    page = Path(__file__).with_name("label_screen.html").read_text(encoding="utf-8")

    @app.middleware("http")
    async def guard(request: Request, call_next: Any) -> Response:
        # A web page in the same browser could otherwise read these workbooks by rebinding a name to
        # this address, or post to it. A custom header can't be sent across sites without our consent.
        if request.headers.get("host") not in allowed_hosts:
            return JSONResponse({"detail": "wrong host"}, status_code=403)
        if request.method not in ("GET", "HEAD") and request.headers.get("x-daftar-label") != "1":
            return JSONResponse({"detail": "missing header"}, status_code=403)
        response: Response = await call_next(request)
        response.headers["Content-Security-Policy"] = POLICY
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(EvalError)
    def manifest_error(_: Request, error: EvalError) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=422)

    @app.get("/")
    def index() -> HTMLResponse:
        return HTMLResponse(page)

    @app.get("/api/workbooks")
    def workbooks() -> dict[str, Any]:
        times = store.times()
        return {
            "who": who,
            "workbooks": [
                {
                    "id": row.id,
                    "split": row.split,
                    "stratum": row.stratum,
                    "language": row.language,
                    "source": row.source,
                    "status": store.status_of(row),
                    "seconds": times.get(row.id, {}),
                }
                for row in read_manifest(manifest_path)
            ],
        }

    @app.get("/api/workbooks/{workbook_id}")
    def workbook(workbook_id: str) -> dict[str, Any]:
        row = store.row(workbook_id)
        label = store.label(row)
        snapshot = store.snapshot(row)
        return {
            "split": row.split,
            "fileName": snapshot["source"]["fileName"],
            "sheets": [_compact_sheet(sheet) for sheet in snapshot["sheets"]],
            "label": _public_label(label),
        }

    @app.put("/api/workbooks/{workbook_id}/label")
    def save(workbook_id: str, body: dict[str, Any]) -> JSONResponse:
        row = store.row(workbook_id)
        with store.lock:
            label = {**store.label(row), **{key: body[key] for key in EDITABLE if key in body}}
            problems = schema_problems(label)
            if problems:
                # Nothing is written: a label that breaks the format would stop every later score.
                return JSONResponse({"saved": False, "problems": problems, "warnings": []}, status_code=422)
            found, warnings = check_against_workbook(label, store.snapshot(row))
            wanted = label["status"]
            if wanted == "reviewed" and found:
                label["status"] = "draft"
            if label["status"] == "reviewed":
                names = list(label.get("labelledBy", []))
                label["labelledBy"] = names if who in names else [*names, who]
                found = check_label(label, row)
            store.write(row, label)
            return JSONResponse({"saved": True, "status": label["status"], "problems": found, "warnings": warnings})

    @app.post("/api/workbooks/{workbook_id}/time")
    def beat(workbook_id: str, body: dict[str, Any]) -> dict[str, bool]:
        store.row(workbook_id)
        seconds = body.get("seconds")
        if not isinstance(seconds, int) or isinstance(seconds, bool) or not 0 < seconds <= MAX_BEAT_SECONDS:
            raise HTTPException(422, "seconds")
        store.add_time(workbook_id, seconds)
        return {"ok": True}

    @app.get("/api/workbooks/{workbook_id}/file")
    def original(workbook_id: str) -> FileResponse:
        row = store.row(workbook_id)
        path = workbook_path(manifest_path, row)
        if path is None:
            raise HTTPException(404, "no file")
        return FileResponse(path, filename=path.name)

    return app
