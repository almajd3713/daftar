"""The worker in a client bundle (C-8): export and re-import only."""

from fastapi import FastAPI

from daftar_worker.client_routes import add_error_handler, router


app = FastAPI(title="Daftar worker", docs_url=None, redoc_url=None, openapi_url=None)
add_error_handler(app)
app.include_router(router)
