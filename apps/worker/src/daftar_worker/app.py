"""Worker HTTP app (C-4). The remaining endpoints arrive with their work packages."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path, PureWindowsPath
import re
import tempfile
import threading
from typing import Any
import uuid

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile

from daftar_worker.analyser import analyze
from daftar_worker.client_routes import CHUNK_BYTES, MAX_BODY_BYTES, add_error_handler, router
from daftar_worker.errors import WorkerError
from daftar_worker.llm.client import settings_from_env
from daftar_worker.reader import read_file
from daftar_worker.reader.limits import MAX_FILE_BYTES


app = FastAPI(title="Daftar worker", docs_url=None, redoc_url=None, openapi_url=None)

SHA256 = re.compile(r"^[0-9a-f]{64}\Z")
MAX_SNAPSHOTS = 16
MAX_JOBS = 64


class SnapshotStore:
    """Snapshots waiting to be analysed, on disk: a large one is about 1 GB in memory.

    They hold client data, so they live in a private temporary folder and only the newest are kept.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._directory: tempfile.TemporaryDirectory[str] | None = None
        self._order: list[str] = []

    def save(self, snapshot: dict[str, Any]) -> None:
        sha256 = snapshot["source"]["sha256"]
        with self._lock:
            if self._directory is None:
                self._directory = tempfile.TemporaryDirectory(prefix="worker-snapshots-")
            root = Path(self._directory.name)
            (root / f"{sha256}.json").write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            if sha256 in self._order:
                self._order.remove(sha256)
            self._order.append(sha256)
            while len(self._order) > MAX_SNAPSHOTS:
                (root / f"{self._order.pop(0)}.json").unlink(missing_ok=True)

    def load(self, sha256: str) -> dict[str, Any] | None:
        with self._lock:
            if self._directory is None or sha256 not in self._order:
                return None
            path = Path(self._directory.name) / f"{sha256}.json"
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data


class Jobs:
    """Analyses run one at a time, so a large workbook can't starve the machine."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analyse")

    def _run(self, job_id: str, snapshot: dict[str, Any], settings: Any) -> None:
        job = self._jobs[job_id]
        job["status"] = "running"

        def on_progress(share: float) -> None:
            job["progress"] = round(share, 3)

        try:
            job["result"] = analyze(snapshot, settings, on_progress)
            job["progress"] = 1.0
            job["status"] = "done"
        except Exception as error:
            job["error"] = WorkerError("unreadable", type(error).__name__).to_json()
            job["status"] = "failed"

    def start(self, snapshot: dict[str, Any], settings: Any = None) -> str:
        job_id = uuid.uuid4().hex
        with self._lock:
            finished = [key for key, job in self._jobs.items() if job["status"] in ("done", "failed")]
            while len(self._jobs) >= MAX_JOBS and finished:
                del self._jobs[finished.pop(0)]
            self._jobs[job_id] = {"status": "queued", "progress": 0.0}
        self._pool.submit(self._run, job_id, snapshot, settings)
        return job_id

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self._jobs.get(job_id)


snapshots = SnapshotStore()
jobs = Jobs()


add_error_handler(app)
app.include_router(router)


@app.post("/v1/read")
async def read(request: Request) -> dict[str, Any]:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise WorkerError("too_large", "request is larger than the limit")
    try:
        async with request.form(max_files=1, max_fields=1) as form:
            upload = form.get("file")
            if not isinstance(upload, UploadFile) or not upload.filename:
                raise WorkerError("unreadable", "no file in the request")
            name = PureWindowsPath(upload.filename).name
            # The upload's own name is never used as a path.
            with tempfile.TemporaryDirectory(prefix="daftar-upload-") as directory:
                target = Path(directory) / f"upload{Path(name).suffix.lower()}"
                written = 0
                with target.open("wb") as stream:
                    while chunk := await upload.read(CHUNK_BYTES):
                        written += len(chunk)
                        if written > MAX_FILE_BYTES:
                            raise WorkerError("too_large", "upload is larger than the limit")
                        stream.write(chunk)
                snapshot: dict[str, Any] = await run_in_threadpool(read_file, target, name)
                await run_in_threadpool(snapshots.save, snapshot)
                return snapshot
    except WorkerError:
        raise
    except Exception as error:  # A malformed multipart body.
        raise WorkerError("unreadable", type(error).__name__) from error


@app.post("/v1/analyze")
async def start_analysis(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except ValueError as error:
        raise WorkerError("unreadable", "the body isn't JSON") from error
    sha256 = body.get("snapshotSha256") if isinstance(body, dict) else None
    llm = body.get("llm", "off") if isinstance(body, dict) else None
    if not isinstance(sha256, str) or not SHA256.match(sha256) or llm not in ("on", "off"):
        raise WorkerError("unreadable", "expected {snapshotSha256, llm: on|off}")
    snapshot = await run_in_threadpool(snapshots.load, sha256)
    if snapshot is None:
        return JSONResponse(WorkerError("unreadable").to_json(), status_code=404)
    # With no model configured, "on" gives the rules-only result (R-11).
    settings = settings_from_env() if llm == "on" else None
    return JSONResponse({"jobId": jobs.start(snapshot, settings)}, status_code=202)


@app.get("/v1/jobs/{job_id}")
def job_status(job_id: str) -> JSONResponse:
    job = jobs.get(job_id)
    if job is None:
        return JSONResponse(WorkerError("unreadable").to_json(), status_code=404)
    return JSONResponse(job)
