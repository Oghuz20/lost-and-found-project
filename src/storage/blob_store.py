"""Filesystem-backed storage for item image blobs.

Owner: Person A.

Design notes
------------
- Files are written under `Settings.image_storage_dir` using a
  server-generated UUID filename (never the client-supplied filename), so
  a path-traversal attempt like ``../../etc/passwd.png`` can never escape
  the storage directory or overwrite another file. This is the exact
  attack documented in `docs/COMMON_PITFALLS.md` #11, and the fix is the
  same: derive the on-disk name from a UUID, never from user input.
- Type checking sniffs the first bytes of the file (a "magic number"
  check) rather than trusting a client-supplied ``Content-Type`` header
  or the filename's extension, either of which a malicious or careless
  client can lie about. This is deliberately pure Python (no
  `python-magic`/libmagic) so the Docker runtime image doesn't need an
  extra system library.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from src.config import Settings, get_settings

# A file this small cannot possibly be a real photo; anything at or below
# this size that still passes the magic-number sniff is almost certainly a
# truncated/corrupted upload rather than a legitimate tiny image.
_MIN_PLAUSIBLE_IMAGE_BYTES = 32

_MAGIC_SIGNATURES: dict[bytes, str] = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
}

_EXTENSION_BY_MIME: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


class BlobValidationError(ValueError):
    """Raised when an uploaded file fails type, size, or integrity checks.

    Callers at the API/CLI boundary should catch this and turn it into a
    clean 4xx / CLI error message, never a raw traceback.
    """


def sniff_image_mime(header: bytes) -> str | None:
    """Return the MIME type implied by a file's leading bytes, or None.

    Only PNG and JPEG are recognised, matching the two types the project
    is required to accept.
    """
    for magic, mime in _MAGIC_SIGNATURES.items():
        if header.startswith(magic):
            return mime
    return None


@dataclass(frozen=True)
class StoredBlob:
    """Result of a successful `BlobStore.save` call."""

    path: Path
    mime_type: str
    size_bytes: int


class BlobStore:
    """Save/read validated image blobs under a configured root directory."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._root = self._settings.image_storage_dir.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def save(self, data: bytes, *, original_filename: str = "") -> StoredBlob:
        """Validate and persist `data`, returning where it landed.

        `original_filename` is accepted only for logging/error messages —
        it is never used to build the on-disk path.
        """
        if not data:
            raise BlobValidationError("uploaded file is empty")

        max_bytes = self._settings.max_image_size_bytes
        if len(data) > max_bytes:
            raise BlobValidationError(
                f"file is {len(data)} bytes, exceeds the {max_bytes}-byte "
                f"({self._settings.max_image_size_mb} MB) limit"
            )

        mime = sniff_image_mime(data[:16])
        if mime is None or mime not in self._settings.allowed_image_types:
            raise BlobValidationError(
                "unsupported or corrupted image; only JPEG/PNG are accepted "
                f"(original_filename={original_filename!r})"
            )

        if len(data) < _MIN_PLAUSIBLE_IMAGE_BYTES:
            raise BlobValidationError(
                "file is too small to be a valid image (likely truncated/corrupted)"
            )

        suffix = _EXTENSION_BY_MIME[mime]
        safe_name = f"{uuid.uuid4().hex}{suffix}"
        dest = (self._root / safe_name).resolve()

        # Defence in depth: unreachable given we build `safe_name` ourselves
        # from a UUID, but this is exactly the guard docs/COMMON_PITFALLS.md
        # asks for, so we keep it explicit rather than "trust the code above".
        if self._root not in dest.parents and dest != self._root:
            raise BlobValidationError("resolved path escapes the storage directory")

        dest.write_bytes(data)
        return StoredBlob(path=dest, mime_type=mime, size_bytes=len(data))

    def read(self, path: Path | str) -> bytes:
        p = Path(path).resolve()
        if self._root not in p.parents and p != self._root:
            raise BlobValidationError("path escapes the storage directory")
        if not p.is_file():
            raise FileNotFoundError(p)
        return p.read_bytes()

    def delete(self, path: Path | str) -> None:
        p = Path(path).resolve()
        if self._root not in p.parents and p != self._root:
            raise BlobValidationError("path escapes the storage directory")
        p.unlink(missing_ok=True)
