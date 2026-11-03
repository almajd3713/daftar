"""Worker HTTP app (C-4). The remaining endpoints arrive with their work packages."""

from pathlib import Path, PureWindowsPath
import shutil
import tempfile
from typing import Any

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile

from daftar_worker.errors import ErrorCode, WorkerError
from daftar_worker.reader import read_file
from daftar_worker.reader.limits import MAX_FILE_BYTES


app = FastAPI(title="Daftar worker", docs_url=None, redoc_url=None, openapi_url=None)

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


@app.exception_handler(WorkerError)
def worker_error(_: Request, error: WorkerError) -> JSONResponse:
    return JSONResponse(error.to_json(), status_code=STATUS[error.code])


@app.get("/healthz")
def healthz() -> dict[str, object]:
    return {"status": "ok", "libreoffice": shutil.which("soffice") is not None}


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
                return snapshot
    except WorkerError:
        raise
    except Exception as error:  # A malformed multipart body.
        raise WorkerError("unreadable", type(error).__name__) from error
