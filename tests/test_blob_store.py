"""Tests for src/storage/blob_store.py (Person A)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import Settings
from src.storage.blob_store import BlobStore, BlobValidationError, sniff_image_mime

# Minimal but fully valid 1x1 PNG (89 bytes).
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000"
    "00907753de0000000c4944415408d76360000000000004000146a13a"
    "020000000049454e44ae426082"
)
# Not a real JPEG past the header, but enough to exercise the magic-number
# sniff and pass the min-size check.
JPEG_LIKE_BYTES = b"\xff\xd8\xff" + b"\x00" * 40


def _store(tmp_path: Path, **overrides: object) -> BlobStore:
    settings = Settings(_env_file=None, image_storage_dir=tmp_path / "blobs", **overrides)
    return BlobStore(settings)


def test_sniff_png_and_jpeg() -> None:
    assert sniff_image_mime(PNG_BYTES[:16]) == "image/png"
    assert sniff_image_mime(JPEG_LIKE_BYTES[:16]) == "image/jpeg"


def test_sniff_unknown_returns_none() -> None:
    assert sniff_image_mime(b"this is definitely not an image") is None


def test_save_valid_png_roundtrip(tmp_path: Path) -> None:
    store = _store(tmp_path, max_image_size_mb=1)
    blob = store.save(PNG_BYTES, original_filename="my-photo.png")
    assert blob.mime_type == "image/png"
    assert blob.size_bytes == len(PNG_BYTES)
    assert blob.path.exists()
    assert store.read(blob.path) == PNG_BYTES


def test_save_valid_jpeg_roundtrip(tmp_path: Path) -> None:
    store = _store(tmp_path, max_image_size_mb=1)
    blob = store.save(JPEG_LIKE_BYTES, original_filename="my-photo.jpg")
    assert blob.mime_type == "image/jpeg"
    assert blob.path.suffix == ".jpg"


def test_rejects_empty_file(tmp_path: Path) -> None:
    store = _store(tmp_path, max_image_size_mb=1)
    with pytest.raises(BlobValidationError, match="empty"):
        store.save(b"")


def test_rejects_oversize_file(tmp_path: Path) -> None:
    store = _store(tmp_path, max_image_size_mb=0.01)  # ~10 KB limit
    huge = PNG_BYTES + b"\x00" * 20_000
    with pytest.raises(BlobValidationError, match="exceeds"):
        store.save(huge)


def test_rejects_non_image_type(tmp_path: Path) -> None:
    store = _store(tmp_path, max_image_size_mb=1)
    with pytest.raises(BlobValidationError, match="unsupported or corrupted"):
        store.save(b"plain text content, long enough to clear the size floor")


def test_rejects_truncated_png(tmp_path: Path) -> None:
    store = _store(tmp_path, max_image_size_mb=1)
    with pytest.raises(BlobValidationError, match="too small"):
        store.save(PNG_BYTES[:10])  # magic bytes only, rest of the file missing


def test_saved_filename_is_server_generated_not_user_controlled(tmp_path: Path) -> None:
    store = _store(tmp_path, max_image_size_mb=1)
    blob = store.save(PNG_BYTES, original_filename="../../etc/passwd.png")
    assert blob.path.parent == store.root
    assert ".." not in blob.path.name
    assert blob.path.name != "passwd.png"


def test_read_rejects_path_outside_root(tmp_path: Path) -> None:
    store = _store(tmp_path, max_image_size_mb=1)
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG_BYTES)
    with pytest.raises(BlobValidationError, match="escapes"):
        store.read(outside)


def test_delete_removes_saved_blob(tmp_path: Path) -> None:
    store = _store(tmp_path, max_image_size_mb=1)
    blob = store.save(PNG_BYTES)
    assert blob.path.exists()
    store.delete(blob.path)
    assert not blob.path.exists()


def test_delete_is_idempotent_on_missing_file(tmp_path: Path) -> None:
    store = _store(tmp_path, max_image_size_mb=1)
    missing = store.root / "does-not-exist.png"
    store.delete(missing)  # should not raise
