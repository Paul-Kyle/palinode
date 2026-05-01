"""I3: PALINODE_CORS_ORIGINS validation must reject wildcards and bad URLs."""
from __future__ import annotations

import pytest


def test_wildcard_rejected() -> None:
    from palinode.api.server import _parse_cors_origins

    with pytest.raises(ValueError, match="wildcard"):
        _parse_cors_origins("*")


def test_wildcard_in_list_rejected() -> None:
    from palinode.api.server import _parse_cors_origins

    with pytest.raises(ValueError, match="wildcard"):
        _parse_cors_origins("http://localhost:3000,*")


def test_wildcard_with_whitespace_rejected() -> None:
    from palinode.api.server import _parse_cors_origins

    with pytest.raises(ValueError, match="wildcard"):
        _parse_cors_origins("  *  ")


def test_malformed_origin_rejected() -> None:
    from palinode.api.server import _parse_cors_origins

    with pytest.raises(ValueError):
        _parse_cors_origins("not-a-url")


def test_missing_scheme_rejected() -> None:
    from palinode.api.server import _parse_cors_origins

    with pytest.raises(ValueError):
        _parse_cors_origins("example.com")


def test_unsupported_scheme_rejected() -> None:
    from palinode.api.server import _parse_cors_origins

    with pytest.raises(ValueError):
        _parse_cors_origins("ftp://example.com")


def test_missing_netloc_rejected() -> None:
    from palinode.api.server import _parse_cors_origins

    with pytest.raises(ValueError):
        _parse_cors_origins("http://")


def test_whitespace_stripped() -> None:
    from palinode.api.server import _parse_cors_origins

    result = _parse_cors_origins("  http://localhost:3000 , http://127.0.0.1:3000 ")
    assert result == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_empty_entries_skipped() -> None:
    from palinode.api.server import _parse_cors_origins

    result = _parse_cors_origins(
        "http://localhost:3000,,http://127.0.0.1:3000"
    )
    assert result == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_https_accepted() -> None:
    from palinode.api.server import _parse_cors_origins

    result = _parse_cors_origins("https://app.example.com")
    assert result == ["https://app.example.com"]


def test_only_empty_input_rejected() -> None:
    from palinode.api.server import _parse_cors_origins

    with pytest.raises(ValueError):
        _parse_cors_origins("")


def test_origin_with_port_accepted() -> None:
    from palinode.api.server import _parse_cors_origins

    result = _parse_cors_origins("http://localhost:8080")
    assert result == ["http://localhost:8080"]
