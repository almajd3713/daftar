"""The routes a client's app needs: health, export and re-import. No analyser and no model (D-9)."""

import json
from pathlib import Path, PureWindowsPath
import shutil
import tempfile
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from starlette.datastructures import UploadFile

from daftar_spec import format_errors, validate_spec
from daftar_worker.errors import ErrorCode, WorkerError
from daftar_worker.reader.limits import MAX_FILE_BYTES
from daftar_worker.roundtrip.diff import diff_workbook
from daftar_worker.roundtrip.export import build_workbook


STATUS: dict[ErrorCode, int] = {
    "unreadable": 422,
    "protected": 422,
    "too_large": 413,
    "unsupported_format": 415,
    "invalid_spec": 422,
}
# Room for the multipart boundaries and headers around the file itself.
MAX_BODY_BYTES = MAX_FILE_BYTES + 64 * 1024
CHUNK_BYTES = 1024 * 1024

router = APIRouter()


def add_error_handler(app: FastAPI) -> None:
    @app.exception_handler(WorkerError)
    def worker_error(_: Request, error: WorkerError) -> JSONResponse:
        return JSONResponse(error.to_json(), status_code=STATUS[error.code])


@router.get("/healthz")
def healthz() -> dict[str, object]:
    return {"status": "ok", "libreoffice": shutil.which("soffice") is not None}


def _parse_spec(data: Any) -> dict[str, Any]:
    errors = validate_spec(data)
    if errors:
        raise WorkerError("invalid_spec", format_errors(errors)[:200])
    spec: dict[str, Any] = data
    return spec


@router.post("/v1/export")
async def export(request: Request) -> Response:
    try:
        body = await request.json()
    except ValueError as error:
        raise WorkerError("invalid_spec", "the body isn't JSON") from error
    if not isinstance(body, dict):
        raise WorkerError("invalid_spec", "expected {spec, rows}")
    spec = _parse_spec(body.get("spec"))
    data = await run_in_threadpool(
        build_workbook,
        spec,
        body.get("rows") or {},
        body.get("locale"),
        body.get("formulas", True),
        body.get("timezone", "UTC"),
    )
    return Response(
        data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@router.post("/v1/reimport/diff")
async def reimport_diff(request: Request) -> dict[str, Any]:
    declared = request.headers.get("content-length", "")
    # The file, plus what the app holds to compare it with.
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES * 8:
        raise WorkerError("too_large", "request is larger than the limit")
    try:
        async with request.form(max_files=1, max_fields=4, max_part_size=256 * 1024 * 1024) as form:
            upload = form.get("file")
            if not isinstance(upload, UploadFile) or not upload.filename:
                raise WorkerError("unreadable", "no file in the request")
            spec = _parse_spec(json.loads(str(form.get("spec"))))
            current = json.loads(str(form.get("keys") or "{}"))
            timezone = str(form.get("timezone") or "UTC")
            name = PureWindowsPath(upload.filename).name
            with tempfile.TemporaryDirectory(prefix="daftar-upload-") as directory:
                target = Path(directory) / f"upload{Path(name).suffix.lower()}"
                written = 0
                with target.open("wb") as stream:
                    while chunk := await upload.read(CHUNK_BYTES):
                        written += len(chunk)
                        if written > MAX_FILE_BYTES:
                            raise WorkerError("too_large", "upload is larger than the limit")
                        stream.write(chunk)
                result: dict[str, Any] = await run_in_threadpool(
                    diff_workbook, target, spec, current, name, timezone
                )
                return result
    except WorkerError:
        raise
    except Exception as error:
        raise WorkerError("unreadable", type(error).__name__) from error
