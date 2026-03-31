"""Stable non-cryptographic hashing helpers used for IDs and dedup keys."""
from __future__ import annotations

import hashlib


def stable_md5_hexdigest(value: str | bytes) -> str:
    """Return a stable MD5 digest for non-security identifiers."""
    payload = value.encode() if isinstance(value, str) else value
    return hashlib.md5(payload, usedforsecurity=False).hexdigest()
