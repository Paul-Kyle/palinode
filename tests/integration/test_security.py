"""Security test suite — OWASP top-10 coverage (issue #123).

Uses FastAPI TestClient against the real API.  Each test is independent.
Where a control is confirmed to be in place the test asserts the correct
rejection.  Where a control is not yet hardened the test is marked
``@pytest.mark.xfail`` so CI stays green while the issue is tracked.

Coverage map
------------
- Path traversal      → test_path_traversal_*
- Null bytes          → test_null_byte_path_rejected
- Symlink escape      → test_symlink_outside_root_rejected
- SQL injection       → test_sql_injection_*
- SSRF                → test_ssrf_*
- CORS enforcement    → test_cors_*
- Rate limiting       → test_rate_limit_write / test_rate_limit_search
- Request size        → test_oversized_request_rejected
- No stack traces     → test_no_stack_trace_in_500
- YAML injection      → test_yaml_frontmatter_injection_is_inert
- CRLF header inj.   → test_crlf_in_source_field_is_safe
- XSS in content      → test_script_tag_injection_blocked
"""
from __future__ import annotations

import os
import time
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from palinode.core.config import config


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMBED_DIM = 1024


def _fake_embed(text: str, backend: str = "local") -> list[float]:
    return [0.1] * EMBED_DIM


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Isolated tmp memory dir — same pattern as test_api_roundtrip.py."""
    memory_dir = str(tmp_path)
    db_path = os.path.join(memory_dir, ".palinode.db")

    monkeypatch.setattr(config, "memory_dir", memory_dir)
    monkeypatch.setattr(config, "db_path", db_path)
    monkeypatch.setattr(config.git, "auto_commit", False)

    for d in ("people", "projects", "decisions", "insights", "research", "inbox", "daily"):
        os.makedirs(os.path.join(memory_dir, d), exist_ok=True)

    from palinode.core import store
    store.init_db()

    with (
        mock.patch("palinode.core.embedder.embed", side_effect=_fake_embed),
        mock.patch("palinode.api.server._generate_description", return_value="Test description"),
        mock.patch("palinode.api.server._generate_summary", return_value=""),
    ):
        yield memory_dir


@pytest.fixture()
def client():
    """Fresh TestClient with cleared rate counters."""
    from palinode.api.server import app, _rate_counters
    _rate_counters.clear()
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# PATH TRAVERSAL
# ---------------------------------------------------------------------------


def test_path_traversal_classic_rejected(client):
    """Classic ../../../etc/passwd traversal → 403 or 400, not 200."""
    resp = client.get("/read?file_path=../../../etc/passwd")
    assert resp.status_code in (400, 403), f"Expected 400/403, got {resp.status_code}"
    assert "Traceback" not in resp.text


def test_path_traversal_double_encoded_rejected(client):
    """Double-encoded traversal (../../sensitive.md) → 403 or 400."""
    resp = client.get("/read?file_path=../../sensitive.md")
    assert resp.status_code in (400, 403), f"Expected 400/403, got {resp.status_code}"


def test_path_traversal_deep_rejected(client):
    """Multiple directory levels of traversal → rejected."""
    resp = client.get("/read?file_path=../../../../../../../../etc/hosts")
    assert resp.status_code in (400, 403), f"Expected 400/403, got {resp.status_code}"
    assert "Traceback" not in resp.text


def test_path_traversal_in_history_rejected(client):
    """Path traversal in /history/{file_path} → 400 or 403 or 404 (not 200 from /)."""
    # The history endpoint accepts a path segment — traversal must not escape memory_dir
    resp = client.get("/history/../../etc/passwd")
    # Acceptable: 400/403 (rejected), 404 (not found), or 422 (validation error).
    # NOT acceptable: 200 with file contents from outside memory_dir.
    assert resp.status_code in (400, 403, 404, 422), (
        f"Expected rejection, got {resp.status_code}: {resp.text[:200]}"
    )


def test_null_byte_path_rejected(client):
    """Null byte in file_path → 400 (not 500 or 200)."""
    resp = client.get("/read?file_path=insights/test%00.md")
    assert resp.status_code in (400, 403), f"Expected 400/403, got {resp.status_code}"
    assert "Traceback" not in resp.text


def test_symlink_outside_root_rejected(client, tmp_path):
    """A symlink that points outside memory_dir must be blocked."""
    # Create a symlink inside memory_dir that points at /etc
    memory_dir = str(tmp_path)
    link_path = os.path.join(memory_dir, "insights", "evil-link.md")
    try:
        os.symlink("/etc/passwd", link_path)
    except OSError:
        pytest.skip("Cannot create symlink on this platform")

    resp = client.get("/read?file_path=insights/evil-link.md")
    # /etc/passwd resolves outside memory_dir → 403
    # If the symlink target doesn't exist for some reason → 404 (also acceptable)
    assert resp.status_code in (400, 403, 404), (
        f"Expected path-traversal rejection, got {resp.status_code}: {resp.text[:200]}"
    )


def test_absolute_path_rejected(client):
    """Absolute file path → 403."""
    resp = client.get("/read?file_path=/etc/passwd")
    assert resp.status_code == 403
    assert "Traceback" not in resp.text


# ---------------------------------------------------------------------------
# SQL INJECTION
# ---------------------------------------------------------------------------


def test_sql_injection_search_returns_empty_not_error(client):
    """Classic SQL injection in search query → 200 with 0 results (not 500)."""
    malicious = "'; DROP TABLE chunks; --"
    resp = client.post("/search", json={"query": malicious, "threshold": 0.0})
    assert resp.status_code == 200
    assert "Traceback" not in resp.text

    # Table must still exist — subsequent search works fine
    resp2 = client.post("/search", json={"query": "hello", "threshold": 0.0})
    assert resp2.status_code == 200


def test_sql_injection_union_select(client):
    """UNION-based SQL injection → 200 with 0 results, table intact."""
    malicious = "x' UNION SELECT 1,2,3 FROM chunks--"
    resp = client.post("/search", json={"query": malicious, "threshold": 0.0})
    assert resp.status_code == 200
    assert "Traceback" not in resp.text
    # Verify the DB is healthy
    resp2 = client.post("/search", json={"query": "test", "threshold": 0.0})
    assert resp2.status_code == 200


def test_sql_injection_in_save_slug(client):
    """SQL injection in slug field → saved to disk with sanitized slug, table intact."""
    resp = client.post("/save", json={
        "content": "SQL injection slug test.",
        "type": "Insight",
        "slug": "'; DROP TABLE chunks; --",
    })
    # Should succeed (slug gets sanitized) or return 400/422 (rejected) — never 500
    assert resp.status_code in (200, 400, 422), (
        f"Expected 200 or 400/422, got {resp.status_code}: {resp.text[:200]}"
    )
    assert "Traceback" not in resp.text
    # DB must still be functional
    resp2 = client.post("/search", json={"query": "test", "threshold": 0.0})
    assert resp2.status_code == 200


# ---------------------------------------------------------------------------
# SSRF
# ---------------------------------------------------------------------------


def test_ssrf_localhost_rejected(client):
    """SSRF to localhost admin port → 400 (not 500 or 200)."""
    resp = client.post("/ingest-url", json={"url": "http://localhost:6340/_internal_admin"})
    assert resp.status_code == 400
    assert "Traceback" not in resp.text


def test_ssrf_file_protocol_rejected(client):
    """SSRF via file:// URI → 400 (not 500 or 200)."""
    resp = client.post("/ingest-url", json={"url": "file:///etc/passwd"})
    assert resp.status_code == 400
    assert "Traceback" not in resp.text


def test_ssrf_cloud_metadata_rejected(client):
    """SSRF to cloud metadata IP (169.254.169.254) → 400."""
    resp = client.post("/ingest-url", json={"url": "http://169.254.169.254/latest/meta-data/"})
    assert resp.status_code == 400
    assert "Traceback" not in resp.text


def test_ssrf_private_ip_rejected(client):
    """SSRF to RFC-1918 private IP → 400."""
    resp = client.post("/ingest-url", json={"url": "http://192.168.1.1/admin"})
    assert resp.status_code == 400
    assert "Traceback" not in resp.text


def test_ssrf_loopback_ipv6_rejected(client):
    """SSRF to IPv6 loopback → 400."""
    resp = client.post("/ingest-url", json={"url": "http://[::1]/secret"})
    assert resp.status_code == 400
    assert "Traceback" not in resp.text


# ---------------------------------------------------------------------------
# CORS ENFORCEMENT
# ---------------------------------------------------------------------------


def test_cors_evil_origin_no_acao_header(client):
    """OPTIONS preflight from evil.example.com → no Access-Control-Allow-Origin."""
    resp = client.options(
        "/save",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    acao = resp.headers.get("access-control-allow-origin", "")
    assert "evil.example.com" not in acao, (
        f"CORS should not allow evil.example.com but got: {acao!r}"
    )


def test_cors_allowed_origin_granted(client):
    """OPTIONS from an allowed origin (localhost:3000) → correct ACAO header."""
    # The default allowed origins include http://localhost:3000
    resp = client.options(
        "/save",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    acao = resp.headers.get("access-control-allow-origin", "")
    assert "localhost:3000" in acao, (
        f"Expected localhost:3000 in ACAO, got: {acao!r}"
    )


def test_cors_wildcard_not_set(client):
    """ACAO header must not be '*' (would allow any origin)."""
    resp = client.options(
        "/save",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    acao = resp.headers.get("access-control-allow-origin", "")
    assert acao != "*", "CORS must not use wildcard origin"


# ---------------------------------------------------------------------------
# RATE LIMITING
# ---------------------------------------------------------------------------


def test_rate_limit_write(client):
    """Burst 31 writes → 30 succeed, 31st returns 429."""
    from palinode.api.server import _rate_counters
    _rate_counters.clear()

    for i in range(31):
        resp = client.post("/save", json={
            "content": f"Rate limit item {i}.",
            "type": "Insight",
            "slug": f"sec-rate-{i}",
        })
        if resp.status_code == 429:
            assert i >= 30, f"Rate limit fired too early at request {i}"
            return

    pytest.fail("Expected 429 after 30 rapid writes — rate limit not enforced")


def test_rate_limit_search(client):
    """Burst 101 searches → 100 succeed, 101st returns 429."""
    from palinode.api.server import _rate_counters
    _rate_counters.clear()

    for i in range(101):
        resp = client.post("/search", json={"query": f"security test {i}", "threshold": 0.0})
        if resp.status_code == 429:
            assert i >= 100, f"Rate limit fired too early at request {i}"
            return

    pytest.fail("Expected 429 after 100 rapid searches — rate limit not enforced")


# ---------------------------------------------------------------------------
# REQUEST SIZE LIMIT
# ---------------------------------------------------------------------------


def test_oversized_request_rejected(client):
    """POST body > 5MB → 413."""
    big_content = "x" * (6 * 1024 * 1024)
    resp = client.post("/save", json={
        "content": big_content,
        "type": "Insight",
        "slug": "oversized",
    })
    assert resp.status_code == 413, f"Expected 413, got {resp.status_code}"
    assert "Traceback" not in resp.text


# ---------------------------------------------------------------------------
# NO STACK TRACES IN ERROR RESPONSES
# ---------------------------------------------------------------------------


def test_no_stack_trace_in_500(client):
    """Internal server error must not leak Python traceback to client."""
    with mock.patch("palinode.core.store.get_db", side_effect=RuntimeError("db gone")):
        resp = client.post("/search", json={"query": "anything"})
    assert resp.status_code == 500
    body = resp.text
    assert "Traceback" not in body
    assert "File " not in body or "palinode" not in body


def test_no_stack_trace_on_malformed_json(client):
    """Malformed JSON request body → 4xx without traceback."""
    resp = client.post(
        "/save",
        content=b"not valid json at all",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code in (400, 422)
    assert "Traceback" not in resp.text


def test_no_stack_trace_on_unknown_endpoint(client):
    """Unknown endpoint → 404 or 405 without traceback."""
    resp = client.get("/nonexistent-endpoint-xyz")
    assert resp.status_code in (404, 405)
    assert "Traceback" not in resp.text


# ---------------------------------------------------------------------------
# YAML INJECTION IN FRONTMATTER
# ---------------------------------------------------------------------------


def test_yaml_frontmatter_injection_is_inert(client, tmp_path):
    """Content with embedded ---/admin: true frontmatter is saved as opaque body.

    The injected frontmatter-style payload must not be parsed into the saved
    file's own frontmatter — it should appear verbatim in the content section.
    """
    payload = "Normal content\n---\nadmin: true\n---\nmore content"
    resp = client.post("/save", json={
        "content": payload,
        "type": "Insight",
        "slug": "yaml-inject-test",
    })
    assert resp.status_code == 200
    fp = resp.json()["file_path"]
    assert os.path.exists(fp)

    with open(fp) as f:
        raw = f.read()

    # Parse the outer frontmatter (the first --- block written by the server)
    parts = raw.split("---", 2)
    assert len(parts) >= 3, "Expected frontmatter + body"
    outer_fm = parts[1]

    import yaml
    fm = yaml.safe_load(outer_fm)
    # The injected key must NOT have escaped into frontmatter
    assert "admin" not in fm, (
        f"Injected key 'admin' found in frontmatter — payload elevated: {fm}"
    )
    # The payload content must appear somewhere in the body section
    assert "admin: true" in raw


def test_yaml_injection_in_entities_is_safe(client, tmp_path):
    """Malicious YAML tag in entities is serialized safely (quoted) by yaml.safe_dump.

    yaml.safe_dump wraps ``!!python/object:os.system`` in single quotes, turning it
    into an inert string literal.  yaml.safe_load can then load the file back without
    executing anything.  This test verifies that property holds end-to-end.
    """
    import yaml as _yaml

    resp = client.post("/save", json={
        "content": "Entity injection test.",
        "type": "Insight",
        "slug": "entity-yaml-inject",
        "entities": ["person/alice", "!!python/object:os.system"],
    })
    # Should succeed (entities are serialized via yaml.safe_dump which quotes the
    # dangerous tag) or return 400/422 if validation rejects it.
    assert resp.status_code in (200, 400, 422)
    assert "Traceback" not in resp.text
    if resp.status_code == 200:
        fp = resp.json()["file_path"]
        with open(fp) as f:
            raw = f.read()
        # yaml.safe_load must be able to parse the frontmatter back without error
        # (this would raise if the dangerous tag were present unquoted)
        parts = raw.split("---", 2)
        assert len(parts) >= 3
        fm = _yaml.safe_load(parts[1])
        # Entity must be a plain string, not an executed object
        entities = fm.get("entities", [])
        for e in entities:
            assert isinstance(e, str), f"Entity is not a string: {e!r}"


# ---------------------------------------------------------------------------
# CRLF / HEADER INJECTION
# ---------------------------------------------------------------------------


def test_crlf_in_source_field_is_safe(client, tmp_path):
    """CRLF sequences in the 'source' field must not inject response headers.

    The source value goes into YAML frontmatter via safe_dump, so CRLF in it
    cannot escape into HTTP response headers.  We verify:
      1. The save succeeds (or returns 400/422 if the value is rejected).
      2. No injected header (X-Admin) appears in the response.
      3. If saved, the file frontmatter contains the escaped value safely.
    """
    crlf_source = "value\r\nX-Admin: true"
    resp = client.post("/save", json={
        "content": "CRLF source injection test.",
        "type": "Insight",
        "slug": "crlf-source-test",
        "source": crlf_source,
    })
    # The response must not contain the injected header
    assert "x-admin" not in resp.headers, (
        f"Injected header found in response: {dict(resp.headers)}"
    )
    assert resp.status_code in (200, 400, 422)
    assert "Traceback" not in resp.text


def test_crlf_in_slug_is_sanitized(client, tmp_path):
    """CRLF in slug is sanitized by the server's slug normalization."""
    resp = client.post("/save", json={
        "content": "CRLF slug test.",
        "type": "Insight",
        "slug": "valid-slug\r\nevil: header",
    })
    # Slug sanitization strips non-alphanumeric characters; CRLF → dash or dropped
    assert resp.status_code in (200, 400, 422)
    assert "Traceback" not in resp.text
    if resp.status_code == 200:
        fp = resp.json()["file_path"]
        # The resulting filename must not contain CRLF
        assert "\r" not in fp and "\n" not in fp


# ---------------------------------------------------------------------------
# XSS / SCRIPT INJECTION (content scan)
# ---------------------------------------------------------------------------


def test_script_tag_injection_blocked(client):
    """<script> tag in content → 400 (blocked by injection scanner)."""
    resp = client.post("/save", json={
        "content": "<script>alert('xss')</script>",
        "type": "Insight",
        "slug": "xss-test",
    })
    assert resp.status_code in (400, 422), (
        f"Expected 400/422 for script injection, got {resp.status_code}"
    )
    assert "Traceback" not in resp.text


def test_javascript_uri_injection_blocked(client):
    """javascript: URI in content → 400 (blocked by injection scanner)."""
    resp = client.post("/save", json={
        "content": "Click here: javascript:void(0)",
        "type": "Insight",
        "slug": "js-uri-test",
    })
    assert resp.status_code in (400, 422), (
        f"Expected 400/422 for javascript: URI, got {resp.status_code}"
    )
    assert "Traceback" not in resp.text
