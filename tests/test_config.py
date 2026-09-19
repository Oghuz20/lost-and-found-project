"""Tests for src/config.py (Person A)."""

from __future__ import annotations

import pytest

from src.config import Settings, get_settings


def test_defaults_are_sane() -> None:
    s = Settings(_env_file=None)
    assert s.max_image_size_mb == 5.0
    assert s.database_url.startswith("postgresql+asyncpg://")
    assert s.log_level == "INFO"
    assert s.http_port == 8000


def test_env_var_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_IMAGE_SIZE_MB", "2.5")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    s = Settings(_env_file=None)
    assert s.max_image_size_mb == 2.5
    assert s.log_level == "DEBUG"  # normalized to upper-case


def test_max_image_size_bytes_property() -> None:
    s = Settings(_env_file=None, max_image_size_mb=1)
    assert s.max_image_size_bytes == 1024 * 1024


def test_asyncpg_dsn_strips_sqlalchemy_driver_segment() -> None:
    s = Settings(_env_file=None, database_url="postgresql+asyncpg://u:p@host:5432/db")
    assert s.asyncpg_dsn == "postgresql://u:p@host:5432/db"


def test_asyncpg_dsn_passthrough_when_already_plain() -> None:
    s = Settings(_env_file=None, database_url="postgresql://u:p@host:5432/db")
    assert s.asyncpg_dsn == "postgresql://u:p@host:5432/db"


def test_get_settings_is_cached() -> None:
    a = get_settings()
    b = get_settings()
    assert a is b


def test_rejects_non_positive_upload_limit() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, max_image_size_mb=0)


def test_rejects_unknown_log_level() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, log_level="VERBOSE")
