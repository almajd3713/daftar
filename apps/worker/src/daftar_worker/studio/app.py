"""The Studio's API, in `docs/studio-api.md`. One operator, on their own machine, with no login.

So it answers only on 127.0.0.1, and keeps other websites in the same browser out: a wrong Host
stops a name rebound to this address, and a JSON or binary content type can't be sent across sites
without a CORS approval this server never gives.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import json
from pathlib import Path, PureWindowsPath
import re
import shutil
import tempfile
import threading
from typing import Any
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from jsonschema import Draft202012Validator
from openpyxl.utils import range_boundaries

from daftar_worker.client_routes import add_error_handler
from daftar_worker.errors import WorkerError
from daftar_worker.llm.client import settings_from_env
from daftar_worker.project.decisions import accept_high_confidence, decide
from daftar_worker.project.files import (
    project_answer,
    project_generate,
    project_init,
    project_reanalyze,
)
from daftar_worker.reader.limits import MAX_FILE_BYTES
from daftar_worker.sheet.grid import REF, column_index


HOST = "127.0.0.1"
PROJECT_ID = re.compile(r"^[0-9a-f]{32}\Z")
MAX_RANGE_CELLS = 20_000
MAX_JOBS = 64
UPLOADS = re.compile(r"^/api/projects(/[0-9a-f]{32}/reanalyze)?$")
PROJECT_FILE = "project.json"
SHEET_SUMMARY_DROPPED = ("cells", "merges", "validations", "conditionalFormats", "hiddenRows", "hiddenColumns")
SCHEMA_PATH = Path(__file__).parent.parent / "analyser" / "analysis.schema.json"
BUSY = {"fr": "Une analyse est en cours sur ce projet. Attendez la fin.", "ar": "يجري تحليل هذا المشروع. انتظر حتى ينتهي."}
GONE = {"fr": "Cet élément a disparu après la nouvelle analyse.", "ar": "اختفى هذا العنصر بعد التحليل الجديد."}
BAD_EDIT = {"fr": "Cette modification n'a pas la forme attendue.", "ar": "هذا التعديل ليس بالشكل المطلوب."}
BAD_ANSWER = {"fr": "Cette réponse n'est pas valable.", "ar": "هذه الإجابة غير صالحة."}
BAD_RANGE = {"fr": "Cette plage de cellules n'est pas valable ou est trop grande.", "ar": "نطاق الخلايا هذا غير صالح أو كبير جدا."}


class Refused(Exception):
    def __init__(self, status: int, reason: dict[str, str]) -> None:
        super().__init__(reason["fr"])
        self.status = status
        self.reason = reason


class Missing(Exception):
    pass


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: Any) -> None:
    partial = path.with_name(f"{path.name}.partial")
    partial.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    partial.replace(path)


def _finding_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator({"$ref": "#/$defs/finding", "$defs": schema["$defs"]})


class Jobs:
    """One at a time, so a large workbook can't starve the machine. A job holds its project busy."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._busy: dict[str, str] = {}
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="studio")

    def _run(self, job_id: str, project: str, work: Callable[[], dict[str, Any]], after: Callable[[], None]) -> None:
        job = self._jobs[job_id]
        job["status"] = "running"
        try:
            job["result"] = work()
            job["progress"] = 1.0
            job["status"] = "done"
        except WorkerError as error:
            job["error"] = error.to_json()
            job["status"] = "failed"
        except Exception as error:
            job["error"] = WorkerError("unreadable", type(error).__name__).to_json()
            job["status"] = "failed"
        finally:
            with self._lock:
                self._busy.pop(project, None)
            after()

    def start(self, project: str, work: Callable[[], dict[str, Any]], after: Callable[[], None] = lambda: None) -> str:
        job_id = uuid.uuid4().hex
        with self._lock:
            if project in self._busy:
                raise Refused(409, BUSY)
            finished = [key for key, job in self._jobs.items() if job["status"] in ("done", "failed")]
            while len(self._jobs) >= MAX_JOBS and finished:
                del self._jobs[finished.pop(0)]
            self._jobs[job_id] = {"status": "queued", "progress": 0.0}
            self._busy[project] = job_id
        self._pool.submit(self._run, job_id, project, work, after)
        return job_id

    def is_busy(self, project: str) -> bool:
        with self._lock:
            return project in self._busy

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self._jobs.get(job_id)


class Store:
    """Projects on disk. A folder counts as a project once its first analysis has finished."""

    def __init__(self, root: Path, who: str, jobs: Jobs) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.who = who
        self.jobs = jobs
        self.lock = threading.RLock()
        self.validator = _finding_validator()

    def folder(self, project: str) -> Path:
        path = self.root / project
        if not PROJECT_ID.match(project) or not (path / PROJECT_FILE).exists():
            raise Missing
        return path

    def _editable(self, project: str) -> Path:
        folder = self.folder(project)
        if self.jobs.is_busy(project):
            raise Refused(409, BUSY)
        return folder

    def summaries(self) -> list[dict[str, Any]]:
        out = []
        for path in sorted(self.root.iterdir()):
            if not (path / PROJECT_FILE).exists():
                continue
            counts = dict.fromkeys(("pending", "accepted", "edited", "rejected"), 0)
            with self.lock:
                findings = _read(path / "analysis.json")["findings"]
            for finding in findings:
                counts[finding["decision"]["status"]] += 1
            modified = (path / "analysis.json").stat().st_mtime
            out.append({**_read(path / PROJECT_FILE), "updatedAt": datetime.fromtimestamp(modified, UTC).isoformat(timespec="seconds"), "counts": counts})
        return sorted(out, key=lambda item: item["updatedAt"], reverse=True)

    def decide(self, project: str, finding_id: str, status: Any, value: Any) -> dict[str, Any]:
        folder = self._editable(project)
        if status not in ("accepted", "edited", "rejected", "pending"):
            raise Refused(400, BAD_EDIT)
        with self.lock:
            analysis = _read(folder / "analysis.json")
            finding = next((item for item in analysis["findings"] if item["id"] == finding_id), None)
            if finding is None:
                raise self._no_finding(folder, finding_id)
            if status == "edited":
                self._check_edit(finding, value)
            decide(finding, status, self.who, value if status == "edited" else None)
            _write(folder / "analysis.json", analysis)
        return dict(finding)

    def _check_edit(self, finding: dict[str, Any], value: Any) -> None:
        if not isinstance(value, dict):
            raise Refused(400, BAD_EDIT)
        # An edit overlays the proposal, as the generator reads it, so that's what has to be valid.
        merged = {**finding, "proposal": {**finding["proposal"], **value}}
        if next(self.validator.iter_errors(merged), None) is not None:
            raise Refused(400, BAD_EDIT)

    @staticmethod
    def _no_finding(folder: Path, finding_id: str) -> Exception:
        conflicts = _read(folder / "conflicts.json") if (folder / "conflicts.json").exists() else []
        if any(item["finding"]["id"] == finding_id for item in conflicts):
            return Refused(409, GONE)
        return Missing()

    def accept_high(self, project: str) -> dict[str, int]:
        folder = self._editable(project)
        with self.lock:
            analysis = _read(folder / "analysis.json")
            accepted = accept_high_confidence(analysis, self.who)
            _write(folder / "analysis.json", analysis)
        statuses = [item["decision"]["status"] for item in analysis["findings"]]
        return {
            "acceptedHigh": accepted,
            "accepted": statuses.count("accepted"),
            "rejected": statuses.count("rejected"),
            "pending": statuses.count("pending"),
        }

    def answer(self, project: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        folder = self._editable(project)
        kind = body.get("kind")
        if kind == "periodYear":
            valid = isinstance(body.get("sheet"), str) and isinstance(body.get("year"), int) and 1900 <= body["year"] <= 2100
        elif kind == "confirmRetention":
            valid = isinstance(body.get("entity"), str) and isinstance(body.get("months"), int) and 1 <= body["months"] <= 1200
        else:
            valid = False
        if not valid:
            raise Refused(400, BAD_ANSWER)
        with self.lock:
            answers = project_answer(folder, body)
        report = folder / "generation-report.json"
        questions: list[dict[str, Any]] = _read(report)["questions"] if report.exists() else []
        return [
            item
            for item in questions
            if not (item["kind"] == "periodYear" and item["sheet"] in answers["periodYears"])
            and not (item["kind"] == "confirmRetention" and item["entity"] in answers["retention"])
        ]

    def snapshot(self, project: str) -> dict[str, Any]:
        snapshot: dict[str, Any] = _read(self.folder(project) / "snapshot.json")
        for sheet in snapshot["sheets"]:
            sheet["cellCount"] = len(sheet["cells"])
            for name in SHEET_SUMMARY_DROPPED:
                sheet.pop(name, None)
        return snapshot

    def sheet(self, project: str, index: int, cell_range: str) -> dict[str, Any]:
        sheets = _read(self.folder(project) / "snapshot.json")["sheets"]
        if not 0 <= index < len(sheets):
            raise Missing
        try:
            left, top, right, bottom = range_boundaries(cell_range)
        except ValueError as error:
            raise Refused(400, BAD_RANGE) from error
        if None in (left, top, right, bottom) or (int(right or 0) - int(left or 0) + 1) * (int(bottom or 0) - int(top or 0) + 1) > MAX_RANGE_CELLS:
            raise Refused(400, BAD_RANGE)
        sheet = sheets[index]

        def inside(reference: str) -> bool:
            match = REF.match(reference)
            if match is None:
                return False
            return int(top or 0) <= int(match.group(2)) <= int(bottom or 0) and int(left or 0) <= column_index(match.group(1)) <= int(right or 0)

        def overlaps(merged: str) -> bool:
            first, high, last, low = range_boundaries(merged)
            return not (int(last or 0) < int(left or 0) or int(first or 0) > int(right or 0) or int(low or 0) < int(top or 0) or int(high or 0) > int(bottom or 0))

        return {
            "name": sheet["name"],
            "index": index,
            "range": cell_range,
            "rtl": sheet["rtl"],
            "dimension": sheet["dimension"],
            "hiddenRows": sheet["hiddenRows"],
            "hiddenColumns": sheet["hiddenColumns"],
            "cells": [cell for cell in sheet["cells"] if inside(cell["ref"])],
            "merges": [item for item in sheet["merges"] if overlaps(item)],
            "validations": sheet["validations"],
            "conditionalFormats": sheet["conditionalFormats"],
        }


def _settings(llm: str | None) -> Any:
    if llm not in (None, "on", "off"):
        raise Refused(400, BAD_ANSWER)
    return settings_from_env() if llm == "on" else None


async def _save_upload(request: Request, directory: str, file_name: str) -> Path | None:
    """The body is the file. Its name only says what format it is, and is never used as a path."""
    target = Path(directory) / f"upload{Path(file_name).suffix.lower()}"
    written = 0
    with target.open("wb") as stream:
        async for chunk in request.stream():
            written += len(chunk)
            if written > MAX_FILE_BYTES:
                raise WorkerError("too_large", "upload is larger than the limit")
            stream.write(chunk)
    return target if written else None


def create_studio_app(root: Path, who: str, port: int) -> FastAPI:
    jobs = Jobs()
    store = Store(root, who, jobs)
    app = FastAPI(title="Daftar Studio", docs_url=None, redoc_url=None, openapi_url=None)
    origins = {f"http://{HOST}:{port}", f"http://localhost:{port}"}
    hosts = {f"{HOST}:{port}", f"localhost:{port}"}
    add_error_handler(app)

    @app.middleware("http")
    async def guard(request: Request, call_next: Any) -> Response:
        if request.headers.get("host") not in hosts:
            return JSONResponse({"detail": "wrong host"}, status_code=403)
        origin = request.headers.get("origin")
        if origin is not None and origin not in origins:
            return JSONResponse({"detail": "wrong origin"}, status_code=403)
        if request.method not in ("GET", "HEAD"):
            kind = request.headers.get("content-type", "").split(";")[0].strip().casefold()
            allowed = {"application/json"}
            if UPLOADS.match(request.url.path):
                allowed.add("application/octet-stream")
            if request.url.path == "/api/projects":
                allowed = {"application/octet-stream"}
            if kind not in allowed:
                return JSONResponse({"error": "wrong_content_type"}, status_code=415)
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Refused)
    def refused(_: Request, error: Refused) -> JSONResponse:
        return JSONResponse({"reason": error.reason}, status_code=error.status)

    @app.exception_handler(Missing)
    def missing(_: Request, __: Missing) -> JSONResponse:
        return JSONResponse({"error": "not_found"}, status_code=404)

    @app.get("/api/projects")
    def projects() -> list[dict[str, Any]]:
        return store.summaries()

    @app.post("/api/projects", status_code=202)
    async def create(request: Request, fileName: str, name: str | None = None, llm: str | None = None) -> dict[str, str]:  # noqa: N803
        settings = _settings(llm)
        clean = PureWindowsPath(fileName).name
        project = uuid.uuid4().hex
        holding = tempfile.TemporaryDirectory(prefix="daftar-studio-")
        try:
            upload = await _save_upload(request, holding.name, clean)
        except BaseException:
            holding.cleanup()
            raise
        if upload is None:
            holding.cleanup()
            raise WorkerError("unreadable", "the request has no file")
        folder = root / project

        def work() -> dict[str, Any]:
            result = project_init(upload, folder, settings, clean)
            _write(folder / PROJECT_FILE, {"id": project, "name": name or Path(clean).stem, "fileName": clean, "createdAt": datetime.now(UTC).isoformat(timespec="seconds")})
            return {"id": project, **result}

        def after() -> None:
            holding.cleanup()
            # A file that failed leaves nothing behind (R-1).
            if not (folder / PROJECT_FILE).exists():
                shutil.rmtree(folder, ignore_errors=True)

        return {"id": project, "jobId": jobs.start(project, work, after)}

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        if job is None:
            raise Missing
        return job

    @app.get("/api/projects/{project}/snapshot")
    def snapshot(project: str) -> dict[str, Any]:
        return store.snapshot(project)

    @app.get("/api/projects/{project}/sheets/{index}")
    def sheet(project: str, index: int, range: str) -> dict[str, Any]:  # noqa: A002
        return store.sheet(project, index, range)

    @app.get("/api/projects/{project}/analysis")
    def analysis(project: str) -> dict[str, Any]:
        with store.lock:
            result: dict[str, Any] = _read(store.folder(project) / "analysis.json")
        return result

    @app.put("/api/projects/{project}/findings/{finding_id}/decision")
    def decision(project: str, finding_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return store.decide(project, finding_id, body.get("status"), body.get("value"))

    @app.post("/api/projects/{project}/decisions/accept-high")
    def accept_high(project: str) -> dict[str, int]:
        return store.accept_high(project)

    @app.post("/api/projects/{project}/reanalyze", status_code=202)
    async def reanalyze(request: Request, project: str, fileName: str | None = None, llm: str | None = None) -> dict[str, str]:  # noqa: N803
        folder = store.folder(project)
        settings = _settings(llm)
        has_file = request.headers.get("content-type", "").startswith("application/octet-stream")
        if has_file and not fileName:
            raise WorkerError("unreadable", "a file needs its fileName")
        holding = tempfile.TemporaryDirectory(prefix="daftar-studio-")
        clean = PureWindowsPath(fileName).name if fileName else None
        try:
            upload = await _save_upload(request, holding.name, clean) if has_file and clean else None
            if has_file and upload is None:
                raise WorkerError("unreadable", "the request has no file")
        except BaseException:
            holding.cleanup()
            raise

        def work() -> dict[str, Any]:
            result = project_reanalyze(folder, upload, settings, clean)
            if clean:
                meta = _read(folder / PROJECT_FILE)
                _write(folder / PROJECT_FILE, {**meta, "fileName": clean})
            return result

        return {"jobId": jobs.start(project, work, holding.cleanup)}

    @app.get("/api/projects/{project}/conflicts")
    def conflicts(project: str) -> list[dict[str, Any]]:
        path = store.folder(project) / "conflicts.json"
        result: list[dict[str, Any]] = _read(path) if path.exists() else []
        return result

    @app.post("/api/projects/{project}/generate", status_code=202)
    def generate(project: str) -> dict[str, str]:
        folder = store.folder(project)

        def work() -> dict[str, Any]:
            project_generate(folder)
            report: dict[str, Any] = _read(folder / "generation-report.json")
            return report

        return {"jobId": jobs.start(project, work)}

    @app.post("/api/projects/{project}/answers")
    def answers(project: str, body: dict[str, Any]) -> dict[str, Any]:
        return {"questions": store.answer(project, body)}

    return app


__all__ = ["HOST", "create_studio_app"]
