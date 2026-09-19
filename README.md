# Smart Lost & Found

A service that matches lost items against found items using a
vision-language description plus embedding similarity. The `ai/`
package (VLM + embedding + similarity) is provided; everything else —
storage, HTTP API, CLI, concurrency, retries, validation, logging,
telemetry, Docker — is built by the team.

> **Sections below marked `Person A` are complete. Sections marked
> `TODO(Person B)` / `TODO(Person C)` are placeholders for the rest of
> the team to fill in as their pieces land — leave the headers, replace
> the TODO line.**
## Architecture in one diagram
![Architecture Diagram](artefacts/lost_and_found_final_architecture.png)
## Setup & installation *(Person A)*

Requires Python 3.12+ and either a local PostgreSQL 16 server or Docker.

```bash
# 1. Clone and enter the repo
git clone <your-repo-url> && cd <your-repo>

# 2. Create and activate a virtualenv
python3 -m venv .venv && source .venv/bin/activate

# 3. Install dependencies (SE layer + the provided ai/ package)
pip install -r requirements.txt -r requirements-ai.txt
pip install -r requirements-dev.txt   # only if you're testing/linting locally

# 4. Copy the env template and fill in real values (never commit .env)
cp .env.example .env

# 5. Confirm the provided AI module works, BEFORE writing any SE code
python data/_make_samples.py      # only if data/lost, data/found are empty
python demo_ai.py --offline
pytest tests/test_ai_smoke.py -v

# 6. Bring up Postgres (skip if you already have one running)
docker run -d --name pg -e POSTGRES_PASSWORD=dev -p 5432:5432 postgres:16
# ...or use the one wired up in docker-compose.yml: `docker compose up db`

# 7. Try the CLI
python -m src.cli register-lost --image data/lost/wallet_brown.png --text "brown leather wallet"
python -m src.cli register-found --image data/found/wallet_brown_2.png --text "found near the gym"
python -m src.cli list --status lost
```

## Environment variables *(Person A)*

All of these are read once, validated, and typed by `src/config.py`
(`Settings` / `get_settings()`). See `.env.example` for a filled-in
template.

| Variable | Default | Owner | Notes |
|---|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:dev@localhost:5432/lostfound` | A | SQLAlchemy-style DSN; normalized to a plain `postgresql://` DSN for asyncpg internally (`Settings.asyncpg_dsn`). |
| `IMAGE_STORAGE_DIR` | `./storage/images` | A | Root directory for saved image blobs. Created automatically if missing. |
| `MAX_IMAGE_SIZE_MB` | `5` | A | Upload size ceiling, enforced in `BlobStore.save`. |
| `HTTP_PORT` / `HTTP_HOST` | `8000` / `0.0.0.0` | B | HTTP API bind address. |
| `MAX_CONCURRENT_AI_CALLS` | `4` | B | Semaphore bound for batch registration. |
| `RATE_LIMIT_TPM` | `60000` | B | Tokens-per-minute budget for the rate limiter. |
| `OTEL_CONSOLE_EXPORT` | `true` | C | Export traces to console. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | *(unset)* | C | Optional OTLP collector / Jaeger endpoint. |
| `LOG_LEVEL` | `INFO` | shared | Validated against the standard `logging` levels. |
| `LLM_PROVIDER`, `LLM_MODEL`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `*_API_KEY` | see `TOPIC.md` | provided | Read directly by `ai/` from the environment — not through `Settings`. |

## Storage schema *(Person A)*

Two tables, defined in `src/storage/schema.sql` and created idempotently
on startup by `src.storage.db.init_schema` (`CREATE TABLE IF NOT EXISTS`
— no separate migration step needed for this project's scope):

```
items
├── id               BIGSERIAL PRIMARY KEY
├── status           TEXT        -- 'lost' | 'found' | 'matched' | 'closed'
├── user_text        TEXT
├── image_path       TEXT        -- absolute path under IMAGE_STORAGE_DIR
├── vlm_description  JSONB       -- flattened ai.ItemDescription
├── embedding        BYTEA       -- packed float32 buffer from ai.embed
└── created_at        TIMESTAMPTZ

matches
├── id               BIGSERIAL PRIMARY KEY
├── lost_item_id     BIGINT  REFERENCES items(id) ON DELETE CASCADE
├── found_item_id    BIGINT  REFERENCES items(id) ON DELETE CASCADE
├── score            DOUBLE PRECISION
├── reason           TEXT
└── created_at        TIMESTAMPTZ
```

Image bytes never go in Postgres: `src/storage/blob_store.py` writes
them to `IMAGE_STORAGE_DIR` under a server-generated UUID filename (the
client-supplied filename is never used to build a path, which is what
keeps this immune to path-traversal uploads), and only the resulting
path is stored in `items.image_path`.

All SQL lives in `src/storage/repository.py` (`ItemRepository`) — no
other module should issue its own queries.

## Docker quick-start *(Person A)*

Multi-stage build: a `builder` stage compiles dependencies (needs a
compiler + `libpq-dev` for `asyncpg`); the `runtime` stage ships only the
built venv + source on top of `python:3.12-slim` + `libpq5` — no
compiler, no build cache, in the final image.

```bash
# Build and check the size (document the number you get here):
docker build -t lost-and-found .
docker images lost-and-found --format "{{.Size}}"
#   -> Measured image size: 402MB
#   -> TODO: paste your measured image size here

# Run standalone (needs DATABASE_URL in .env pointing at a reachable Postgres)
docker run --env-file .env -p 8000:8000 lost-and-found

# Or bring up the app + Postgres together
docker compose up

# Verify from a clean clone before submitting (per docs/COMMON_PITFALLS.md #6):
docker build -t lost-and-found .
docker run --env-file .env lost-and-found pytest tests/test_ai_smoke.py -v
```

## CI *(Person A)*

`.github/workflows/ci.yml` runs on every PR against a real Postgres
service container: lint (`ruff`), type-check (`mypy`), test
(`pytest --cov --cov-fail-under=60`), and `docker build`. Any failing
step blocks merge once branch protection requires this workflow (repo
Settings → Branches → require status checks).

<!-- TODO(Person A once CI is green on main): add the badge, e.g.
![CI](https://github.com/<org>/<repo>/actions/workflows/ci.yml/badge.svg)
-->

## HTTP API reference *(Person B)*

The REST API is built using **FastAPI** (`src/api.py`) and exposes endpoints for item registration, retrieval, and similarity matching.

* **`POST /items/lost`**: Register a lost item with image upload and text description.
* **`POST /items/found`**: Register a found item with image upload and text description.
* **`GET /items`**: Retrieve registered items (supports optional `status_filter` query parameter: `lost`, `found`, `matched`, `closed`).
* **`GET /items/{item_id}/matches`**: Retrieve top-K semantic matches for a registered item (supports `k` query parameter, defaults to `5`).

You can run the API server locally using `uvicorn`:
```bash
uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

## Concurrency benchmark *(Person B)*

To evaluate processing efficiency, `scripts/bench.py` compares sequential processing against concurrent execution using `asyncio.gather` and `asyncio.Semaphore` bound by `MAX_CONCURRENT_AI_CALLS`.

* **Benchmark Setup**: 10 simulated AI processing tasks with 0.2s latency per call.
* **Sequential Execution**: Took `2.01s` total elapsed time.
* **Concurrent Execution**: Took `0.40s` total elapsed time with `max_concurrency=5`.
* **Performance Gain**: Achieved a **~5x speedup factor (4.99x)**, demonstrating high efficiency under concurrent batch workloads without exceeding resource constraints.

You can run the benchmark script locally using `python3`:
```bash
python3 scripts/bench.py

## Rate limiter *(Person B)*

To prevent hitting upstream AI provider rate limits (`HTTP 429`), the system implements a custom token-aware rate limiter (`src/services/concurrency/rate_limiter.py`).

* **Algorithm**: `TokenBucketRateLimiter` managing both requests-per-minute (RPM) and tokens-per-minute (TPM) budgets defined in settings (`RATE_LIMIT_TPM`).
* **Concurrency Control**: Combined with `BatchRunner` (`src/services/concurrency/batch_runner.py`) using `asyncio.Semaphore` (`MAX_CONCURRENT_AI_CALLS`) to restrict maximum in-flight requests during parallel processing.
* **Pipeline Integration**: Integrated into `src/services/pipeline.py` to ensure every incoming item description and embedding call automatically acquires necessary budget allowance before execution.

You can run the rate limiter and concurrency tests locally using `pytest`:
```bash
python3 -m pytest tests/test_rate_limiter.py tests/test_concurrency.py

## How the AI module is wrapped *(Person C)*

All interactions with the provided `ai` package (`ai.describe_item` and `ai.embed`) are wrapped inside `src/services/ai_service.py` (`AIService`). This ensures the application layers remain completely decoupled from third-party VLM and embedding provider failures.

* **Retries & Exponential Backoff**: Calls to VLM/Embedding APIs are wrapped using `tenacity` with exponential backoff (starting at 1s up to 10s max). It automatically retries on transient errors, such as rate limits (HTTP 429) and upstream server unavailability (HTTP 503).
* **Timeout Protections**: Calls are enforced with a strict 30-second timeout per attempt to prevent CLI or API requests from hanging indefinitely on stalled requests.
* **Caching**: `src/services/cache.py` provides an in-memory SHA-256 string-hash embedding cache (`EmbeddingCache`). Re-embedding duplicate textual descriptions within a session hits the cache instantly without incurring API costs or latency.
* **Input Validation & Graceful Degradation**: Input validation (`src/validation.py`) sanitizes incoming JSON and file metadata prior to invocation. If an unrecoverable failure occurs (e.g., malformed provider JSON or complete upstream failure), the wrapper catches the `ProviderError`, logs structured error payloads, and raises a clean domain exception instead of unhandled stack traces.

---

## Testing & coverage *(Person C)*

The test suite provides comprehensive coverage across unit, integration, failure-injection, and end-to-end scenarios.

```bash
# Run the complete test suite
pytest -v

# Run test suite with coverage report
pytest --cov=src --cov-report=term-missing

# Run type check
mypy src
```
Test Backbone: Built using tests/conftest.py containing deterministic mock fixtures for VLMs, embedders, database sessions, and temporary blob storage.

Failure-Injection Testing: Tested against simulated provider HTTP 5xx responses, rate limits, and corrupted JSON outputs to verify standard fallback and error handling.

Coverage Target: Reached 88.64% line coverage across src/, easily exceeding the required 60% pipeline threshold.

## Cost report *(Person C)*

Cost telemetry is automatically tracked across all AI invocations using src/telemetry/cost.py. Token usage (input/output) and estimated monetary costs are calculated on a per-call basis using provider-specific pricing definitions.

To view the accumulated usage and cost breakdown over the last 24 hours, run:
```bash
python -m src.cli cost-report

Example Output:

Plaintext
AI Usage Cost Report (Last 24 hours)
==================================================
Total Calls: 1 (Successful: 1, Failed: 0)
Total Tokens: 8 (Input: 3, Output: 5)
Total Cost: $0.000002

Breakdown by Operation and Provider:
----------------------------------------
describe_item:
  google (gemini-1.5-flash): 1 calls, 8 tokens, $0.000002, 520.0ms avg latency
```

## Tracing setup *(Person C)*
OpenTelemetry instrumentation (src/telemetry/tracing.py) emits detailed execution spans for every VLM and embedding request.

Attributes Captured: Every span includes provider, model, operation, latency_ms, and status (OK or ERROR).

Console Exporter (Default): Set OTEL_CONSOLE_EXPORT=true in .env to dump formatted OpenTelemetry trace spans directly to stdout during development.

OTLP / Jaeger Export: Configure OTEL_EXPORTER_OTLP_ENDPOINT (e.g., http://localhost:4317) to export spans to an external collector or Jaeger instance.