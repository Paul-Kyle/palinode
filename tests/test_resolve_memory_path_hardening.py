"""Tests for the path-traversal hardening of `_resolve_memory_path` (#284).

Tied to the marketplace security review (Tier B finding #2). The legacy
implementation used ``os.path.realpath`` plus ``os.path.commonpath``. Both
have known cross-platform quirks (Windows reparse points, TOCTOU during
symlink replacement) and the legacy ``ValueError``-leaks the
filesystem path into the HTTPException detail message.

This test suite asserts:
- ``../`` traversal is rejected with a generic 403 detail
- absolute paths are rejected
- null-byte paths are rejected
- symlinks pointing outside ``memory_dir`` are rejected
- a normal nested path is accepted
- the rejection detail message is generic (no leaked filesystem info)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from fastapi import HTTPException


def _make_memory_dir(tmp_path: Path) -> Path:
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "decisions").mkdir()
    (mem / "decisions" / "ok.md").write_text("# ok\n")
    return mem


def _patch_memory_dir(monkeypatch: pytest.MonkeyPatch, mem: Path) -> None:
    # The helper reads memory_dir via _memory_base_dir(), which itself reads
    # config.memory_dir. We monkeypatch the config module-level attribute.
    from palinode.api import server
    from palinode.core.config import config

    monkeypatch.setattr(config, "memory_dir", str(mem), raising=False)
    # Some code paths resolve via os.path.realpath; ensure both branches see
    # the same root.
    server._memory_base_dir.cache_clear() if hasattr(server._memory_base_dir, "cache_clear") else None


# ---------------------------------------------------------------------------
# Traversal rejection
# ---------------------------------------------------------------------------


def test_dotdot_traversal_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mem = _make_memory_dir(tmp_path)
    _patch_memory_dir(monkeypatch, mem)
    from palinode.api.server import _resolve_memory_path

    # Two levels up from `decisions/` lands outside memory_dir.
    with pytest.raises(HTTPException) as exc_info:
        _resolve_memory_path("decisions/../../etc/passwd")
    assert exc_info.value.status_code == 403
    # Generic detail — no leaked filesystem layout
    assert exc_info.value.detail == "Invalid path"


def test_absolute_path_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mem = _make_memory_dir(tmp_path)
    _patch_memory_dir(monkeypatch, mem)
    from palinode.api.server import _resolve_memory_path

    with pytest.raises(HTTPException) as exc_info:
        _resolve_memory_path("/etc/passwd")
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Invalid path"


def test_null_byte_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mem = _make_memory_dir(tmp_path)
    _patch_memory_dir(monkeypatch, mem)
    from palinode.api.server import _resolve_memory_path

    with pytest.raises(HTTPException) as exc_info:
        _resolve_memory_path("decisions/foo\x00bar.md")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid path"


def test_symlink_outside_memory_dir_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A symlink whose target sits outside memory_dir must be rejected."""
    mem = _make_memory_dir(tmp_path)
    _patch_memory_dir(monkeypatch, mem)
    from palinode.api.server import _resolve_memory_path

    # Create a target file outside memory_dir
    outside = tmp_path / "outside-secrets.md"
    outside.write_text("secret\n")

    # Create a symlink inside memory_dir pointing to it
    link = mem / "decisions" / "link-out.md"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover (Windows w/o privilege)
        pytest.skip(f"Cannot create symlink in this env: {exc}")

    with pytest.raises(HTTPException) as exc_info:
        _resolve_memory_path("decisions/link-out.md")
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Invalid path"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_legitimate_nested_path_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mem = _make_memory_dir(tmp_path)
    _patch_memory_dir(monkeypatch, mem)
    from palinode.api.server import _resolve_memory_path

    base, resolved = _resolve_memory_path("decisions/ok.md")
    assert base == str(mem.resolve())
    assert resolved == str((mem / "decisions" / "ok.md").resolve())


def test_path_with_dot_normalized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mem = _make_memory_dir(tmp_path)
    _patch_memory_dir(monkeypatch, mem)
    from palinode.api.server import _resolve_memory_path

    # "decisions/./ok.md" is identical to "decisions/ok.md" after resolve()
    base, resolved = _resolve_memory_path("decisions/./ok.md")
    assert resolved == str((mem / "decisions" / "ok.md").resolve())


def test_nonexistent_path_does_not_leak_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A nonexistent path under memory_dir should resolve cleanly (callers
    decide whether to 404). It must NOT raise — strict=False is intentional."""
    mem = _make_memory_dir(tmp_path)
    _patch_memory_dir(monkeypatch, mem)
    from palinode.api.server import _resolve_memory_path

    base, resolved = _resolve_memory_path("decisions/does-not-exist.md")
    assert resolved.startswith(str(mem.resolve()))


# ---------------------------------------------------------------------------
# Error-message safety: the legacy implementation embedded the resolved path
# in the ``ValueError`` text on Windows-vs-POSIX commonpath mismatches. Make
# sure the new implementation only ever returns "Invalid path".
# ---------------------------------------------------------------------------


def test_no_filesystem_info_leak_in_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mem = _make_memory_dir(tmp_path)
    _patch_memory_dir(monkeypatch, mem)
    from palinode.api.server import _resolve_memory_path

    forbidden_inputs = [
        "../../../etc/shadow",
        "/var/log/auth.log",
        "decisions/foo\x00../../etc/passwd",
    ]
    for inp in forbidden_inputs:
        with pytest.raises(HTTPException) as exc_info:
            _resolve_memory_path(inp)
        # Must be a generic message — never echo the input or filesystem path
        assert exc_info.value.detail == "Invalid path"
        # Also: status code should be either 400 (bad input shape) or 403
        assert exc_info.value.status_code in (400, 403)
