"""Worker HTTP app. The C-4 endpoints arrive with their work packages."""

import shutil

from fastapi import FastAPI


app = FastAPI(title="Daftar worker", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/healthz")
def healthz() -> dict[str, object]:
    return {"status": "ok", "libreoffice": shutil.which("soffice") is not None}
