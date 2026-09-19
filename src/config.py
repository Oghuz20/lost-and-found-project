"""Typed application configuration for the Smart Lost & Found service.

Owner: Person A (Storage, Config & DevOps).

Every environment variable the project cares about — across all three
people's slices — is declared here, once, with a type and a default.
Downstream code should import `get_settings()` rather than reading
`os.environ` directly, so there's exactly one place that knows a `.env`
file exists and exactly one source of truth for "what did we configure".

Field names intentionally match the keys already used in `.env.example`
(``DATABASE_URL``, ``IMAGE_STORAGE_DIR``, ``MAX_IMAGE_SIZE_MB``,
``HTTP_PORT``, ...) so nothing needs renaming later.

Note: the `ai/` package reads `LLM_PROVIDER`, `EMBEDDING_PROVIDER`, and the
provider API keys straight out of `os.environ` itself (see
`ai/providers/factory.py`) — it does NOT go through this module. We still
declare those fields here so the rest of the app (e.g. a `config` CLI
command, or the cost-report bonus) has one typed place to read them from
for *display* purposes; changing them here has no effect on how `ai/`
behaves, only `.env`/the real environment does.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of truth for runtime configuration.

    Instantiate via `get_settings()` in application code. Tests should
    construct `Settings(_env_file=None, **overrides)` directly so they
    never depend on (or are polluted by) a real `.env` file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Storage (Person A) -------------------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:dev@localhost:5432/lostfound",
        description="Postgres DSN. The '+asyncpg' driver segment (SQLAlchemy "
        "style, matching .env.example) is stripped automatically before we "
        "hand the DSN to asyncpg — see `asyncpg_dsn`.",
    )
    image_storage_dir: Path = Field(
        default=Path("./storage/images"),
        description="Directory image blobs are written to. Created if missing.",
    )
    max_image_size_mb: float = Field(
        default=5.0, gt=0, description="Max accepted upload size, in MB."
    )
    allowed_image_types: tuple[str, ...] = Field(
        default=("image/jpeg", "image/png"),
        description="Accepted MIME types for item images, sniffed from file bytes.",
    )

    # --- HTTP API & concurrency (Person B) ----------------------------------
    http_port: int = Field(default=8000, gt=0, lt=65536)
    http_host: str = "0.0.0.0"
    max_concurrent_ai_calls: int = Field(
        default=4, gt=0, description="Semaphore bound for batch registration."
    )
    rate_limit_tpm: int = Field(
        default=60_000, gt=0, description="Tokens-per-minute budget for the rate limiter."
    )

    # --- AI providers (ai/ reads these directly from the environment;
    #     declared here only so the rest of the app can display/report them) --
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-6"
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"

    # --- Telemetry (Person C) -----------------------------------------------
    otel_console_export: bool = True
    otel_exporter_otlp_endpoint: str | None = None

    # --- Logging (shared) ----------------------------------------------------
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def _log_level_valid(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper().strip()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}, got {v!r}")
        return upper

    @property
    def max_image_size_bytes(self) -> int:
        return int(self.max_image_size_mb * 1024 * 1024)

    @property
    def asyncpg_dsn(self) -> str:
        """`database_url` normalized for `asyncpg.create_pool` / `asyncpg.connect`.

        `.env.example` uses the SQLAlchemy-style scheme
        ``postgresql+asyncpg://...`` so the same value would also work if a
        teammate wires up SQLAlchemy later; asyncpg itself only understands
        plain ``postgresql://`` (or ``postgres://``), so we strip the driver
        segment here rather than asking everyone to remember to do it.
        """
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
            "postgres+asyncpg://", "postgresql://"
        )


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings instance.

    Cached with `lru_cache` so we parse the environment once. Call
    `get_settings.cache_clear()` in tests if you need a fresh read after
    mutating `os.environ` mid-test (prefer constructing `Settings(...)`
    directly instead, which sidesteps the cache entirely).
    """
    return Settings()
