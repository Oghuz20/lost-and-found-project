# syntax=docker/dockerfile:1
# =====================================================================
# Multi-stage Dockerfile — Smart Lost & Found  (bonus: multi-stage, +1)
#
# Stage 1 "builder": has the compiler + headers needed to build wheels
#   (e.g. asyncpg) into a venv.
# Stage 2 "runtime": copies ONLY the venv + source code onto a slim base.
#   No compiler, no apt build cache, no pip cache ship in the final image.
#
# After building, record the resulting image size in README.md:
#   docker build -t lost-and-found .
#   docker images lost-and-found --format "{{.Size}}"
# =====================================================================

# ---- Stage 1: builder -------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build-time-only system deps: a compiler + Postgres client headers, both
# needed to build the asyncpg wheel on platforms without a prebuilt one.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt requirements-ai.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ai.txt

# ---- Stage 2: runtime ---------------------------------------------------
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="Smart Lost & Found" \
      org.opencontainers.image.version="1.0" \
      org.opencontainers.image.source="https://github.com/your-team/your-repo"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Runtime-only system dep: the Postgres *client library* (asyncpg needs
# libpq.so at runtime) — NOT libpq-dev's headers/compiler, which stay in
# the builder stage. This is most of what keeps this image small.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Bring over only the already-built venv — no compiler, no apt cache, no
# pip cache leak into the final image.
COPY --from=builder /opt/venv /opt/venv
COPY . .

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/storage/images \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Uncomment once Person B's src/api.py exposes a `/health` route.
# HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
#     CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Default: serve the HTTP API (Person B's src/api.py exposes `app`).
# Swap to the CLI entrypoint below if you'd rather demo via the CLI.
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
# CMD ["python", "-m", "src.cli", "list"]

# =====================================================================
# Build and run:
#   docker build -t lost-and-found .
#   docker run --env-file .env -p 8000:8000 lost-and-found
#   docker compose up                 # app + Postgres together
#
# Verify before submission (run from a clean clone):
#   docker build -t lost-and-found .
#   docker run --env-file .env lost-and-found pytest tests/test_ai_smoke.py -v
# =====================================================================
