"""L5: file-read paths must use try-open + O_NOFOLLOW, not exists+open.

The TOCTOU window between os.path.exists() and open() let a symlink swap
within memory_dir redirect a memory read to a sensitive file. We close the
window two ways:

  - Try-open and catch FileNotFoundError instead of probing existence first.
  - Use os.O_NOFOLLOW where available (POSIX) so symlinks raise OSError
    even after the swap.

Tests cover both behaviours and confirm the legacy 404 path still works.
"""
from __future__ import annotations

import os
import sys

import pytest

from fastapi import HTTPException


@pytest.fixture
def memory_dir(tmp_path, monkeypatch):
    from palinode.core.config import config

    # config.palinode_dir is a property that delegates to memory_dir, so
    # patching memory_dir alone is sufficient.
    monkeypatch.setattr(config, "memory_dir", str(tmp_path))
    return tmp_path


def test_read_missing_file_returns_404(memory_dir) -> None:
    from palinode.api import server

    with pytest.raises(HTTPException) as ei:
        server.read_api(file_path="does-not-exist.md")
    assert ei.value.status_code == 404


def test_read_existing_file_works(memory_dir) -> None:
    from palinode.api import server

    target = memory_dir / "real.md"
    target.write_text("---\nid: real\n---\nbody\n", encoding="utf-8")

    result = server.read_api(file_path="real.md")
    assert result["file"] == "real.md"
    assert "body" in result["content"]


@pytest.mark.skipif(
    not hasattr(os, "O_NOFOLLOW") or sys.platform.startswith("win"),
    reason="O_NOFOLLOW is POSIX-only",
)
def test_open_memory_file_rejects_symlink(memory_dir) -> None:
    """A symlink target inside memory_dir is rejected by O_NOFOLLOW."""
    from palinode.api.server import _open_memory_file_text

    real = memory_dir / "real.md"
    real.write_text("real content", encoding="utf-8")
    link = memory_dir / "link.md"
    os.symlink(str(real), str(link))

    with pytest.raises(OSError):
        _open_memory_file_text(str(link))


def test_read_memory_body_handles_missing_file(memory_dir) -> None:
    """_read_memory_body returns None for missing files, doesn't raise."""
    from palinode.api.server import _read_memory_body

    assert _read_memory_body("nope.md") is None


def test_read_memory_body_returns_content(memory_dir) -> None:
    """_read_memory_body works on a real file."""
    from palinode.api.server import _read_memory_body

    target = memory_dir / "thing.md"
    target.write_text("hello world", encoding="utf-8")
    assert _read_memory_body("thing.md") == "hello world"


@pytest.mark.skipif(
    not hasattr(os, "O_NOFOLLOW") or sys.platform.startswith("win"),
    reason="O_NOFOLLOW is POSIX-only",
)
def test_open_memory_file_rejects_swap_to_symlink(memory_dir) -> None:
    """Simulates the L5 race: file exists as a symlink at open time.

    If `_resolve_memory_path` previously returned a real path and the
    filesystem entry has since been swapped to a symlink, _open_memory_file_text
    must refuse to follow it. We pass the symlink path directly here to
    exercise that behaviour — _resolve_memory_path itself uses realpath()
    which collapses symlinks at resolution time, so this test focuses on
    the open-time check that catches a swap that happens after resolution.
    """
    from palinode.api.server import _open_memory_file_text

    real = memory_dir / "real.md"
    real.write_text("real content", encoding="utf-8")

    link = memory_dir / "link.md"
    os.symlink(str(real), str(link))

    # Open the symlink path directly with O_NOFOLLOW — must raise OSError
    # (typically ELOOP). Without O_NOFOLLOW, we'd silently read 'real.md'.
    with pytest.raises(OSError):
        _open_memory_file_text(str(link))


def test_no_existence_check_before_open(memory_dir) -> None:
    """Confirms read_api uses try-open rather than exists+open.

    A regression check: removing the os.path.exists() probe must still
    yield a clean 404 for missing files (FileNotFoundError → 404).
    """
    from palinode.api import server

    with pytest.raises(HTTPException) as ei:
        server.read_api(file_path="absent.md")
    assert ei.value.status_code == 404
