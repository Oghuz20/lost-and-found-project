# Smart Lost & Found

A service that matches lost items against found items using a vision-language description plus embedding similarity. The `ai/` package (VLM + embedding + similarity) is provided; everything else — storage, HTTP API, CLI, concurrency, retries, validation, logging, telemetry, Docker — is built by the team.

## Architecture in one diagram
![Architecture Diagram](artefacts/lost_and_found_final_architecture.png)

## Setup & Installation

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

# 5. Run smoke tests
python demo_ai.py --offline
pytest tests/test_ai_smoke.py -v

# 6. Confirm the provided AI module works, BEFORE writing any SE code
python data/_make_samples.py      # only if data/lost, data/found are empty
python demo_ai.py --offline
pytest tests/test_ai_smoke.py -v

# 7. Bring up Postgres (skip if you already have one running)
docker run -d --name pg -e POSTGRES_PASSWORD=dev -p 5432:5432 postgres:16
# ...or use the one wired up in docker-compose.yml: `docker compose up db`

# 8. Try the CLI
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