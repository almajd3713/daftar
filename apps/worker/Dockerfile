# Build from the repo root: docker build -f apps/worker/Dockerfile .
FROM python:3.12-slim-bookworm AS base

# Headless LibreOffice converts .xls and .ods (R-1). The conversion path must never force a recalculation.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-calc-nogui \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.11.26
RUN useradd --create-home --uid 1000 daftar
WORKDIR /app
COPY . .

# Runs the worker tests against the same LibreOffice that ships. A missing soffice fails them.
FROM base AS test
RUN uv sync --frozen
RUN chown -R daftar /app
USER daftar
ENV DAFTAR_REQUIRE_LIBREOFFICE=1 UV_NO_SYNC=1
CMD ["uv", "run", "--frozen", "pytest", "apps/worker/tests", "-q"]

# The worker in a client bundle (D-9, C-8): export and re-import, with no analyser, Studio code or model.
FROM base AS client
RUN rm -rf apps/worker/tests eval \
    apps/worker/src/daftar_worker/analyser \
    apps/worker/src/daftar_worker/llm \
    apps/worker/src/daftar_worker/evaluation \
    apps/worker/src/daftar_worker/project \
    apps/worker/src/daftar_worker/studio \
    apps/worker/src/daftar_worker/census.py \
    apps/worker/src/daftar_worker/app.py \
    apps/worker/src/daftar_worker/cli.py \
    && uv sync --frozen --no-dev --no-editable --package daftar-worker \
    && rm -f .venv/bin/daftar
USER daftar
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["uvicorn", "daftar_worker.client_app:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS runtime
RUN rm -rf apps/worker/tests eval && uv sync --frozen --no-dev --no-editable --package daftar-worker
USER daftar
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["uvicorn", "daftar_worker.app:app", "--host", "0.0.0.0", "--port", "8000"]
