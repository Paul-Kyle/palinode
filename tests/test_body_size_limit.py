"""Tests for the streaming body-size limit middleware (#284 / Tier B #3).

The legacy middleware only inspected the ``Content-Length`` header. The new
implementation tallies bytes from the ASGI ``receive`` callable so it cannot
be bypassed by chunked-transfer-encoding or by a client lying about the
declared length.

These tests exercise both:
- header fast-path (rejects on declared length over the limit)
- streaming path (rejects when the actual body grows past the limit even if
  the declared length was small or absent)
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from palinode.api import server


@pytest.fixture
def small_limit(monkeypatch: pytest.MonkeyPatch):
    """Re-build the middleware with a tiny limit for faster, deterministic tests."""
    # Mutate the constant; the middleware reads it on dispatch via self.max_bytes
    # which is captured at app-build time. Easiest: patch on each instance.
    found = False
    for mw in server.app.user_middleware:
        if mw.cls is server._BodySizeLimitMiddleware:
            monkeypatch.setitem(mw.kwargs, "max_bytes", 256)
            found = True
    assert found, "BodySizeLimitMiddleware was not registered on the app"
    # Force FastAPI to rebuild its middleware stack so the patched kwargs apply.
    server.app.middleware_stack = None
    yield 256
    server.app.middleware_stack = None


# ---------------------------------------------------------------------------
# Header fast-path
# ---------------------------------------------------------------------------


def test_oversized_content_length_rejected(small_limit):
    """A request that DECLARES it will be too large is rejected with 413."""
    client = TestClient(server.app, raise_server_exceptions=False)
    big_body = b"x" * 1024  # > 256
    resp = client.post(
        "/save",
        content=big_body,
        headers={"content-type": "application/json", "content-length": "1024"},
    )
    assert resp.status_code == 413
    assert resp.json()["detail"] == "Request body too large"


def test_undersized_request_passes_through(small_limit):
    """A small body must pass through to the route handler."""
    client = TestClient(server.app, raise_server_exceptions=False)
    # Hit a tiny endpoint that accepts JSON. We don't care about the result —
    # only that we don't get 413. /search rejects malformed bodies with 422,
    # which is fine here (it means the middleware passed us through).
    resp = client.post(
        "/search",
        content=json.dumps({"query": "x"}).encode(),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code != 413


# ---------------------------------------------------------------------------
# Streaming-path enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_body_exceeds_limit_returns_413():
    """Drive the middleware directly with a faked ASGI scope and a
    chunked receive that omits Content-Length entirely.

    This is the scenario the legacy header-only check missed: chunked
    transfer encoding doesn't set Content-Length, so the legacy middleware
    let the body through unconstrained. The new streaming check tallies
    bytes during receive() and raises 413 mid-stream.
    """
    sent_messages: list[dict] = []

    async def send(msg):
        sent_messages.append(msg)

    chunks = [
        {"type": "http.request", "body": b"a" * 100, "more_body": True},
        {"type": "http.request", "body": b"b" * 100, "more_body": True},
        {"type": "http.request", "body": b"c" * 100, "more_body": False},
    ]
    chunk_iter = iter(chunks)

    async def receive():
        try:
            return next(chunk_iter)
        except StopIteration:  # pragma: no cover (we always 413 first)
            return {"type": "http.disconnect"}

    # A no-op downstream that drains the body and returns 200 — should NEVER
    # be reached because 413 short-circuits.
    downstream_called = False

    async def fake_app(scope, recv, snd):
        nonlocal downstream_called
        downstream_called = True
        # Drain until the middleware injects 413
        while True:
            msg = await recv()
            if not msg.get("more_body", False):
                break
        await snd({"type": "http.response.start", "status": 200, "headers": []})
        await snd({"type": "http.response.body", "body": b"ok"})

    middleware = server._BodySizeLimitMiddleware(fake_app, max_bytes=150)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/save",
        "headers": [],  # NO content-length — this is the bypass case
    }
    await middleware(scope, receive, send)

    # The middleware should have emitted a 413 response start + body
    statuses = [m for m in sent_messages if m["type"] == "http.response.start"]
    assert statuses, f"No response.start emitted; got {sent_messages}"
    assert statuses[0]["status"] == 413


def test_max_bytes_constant_reused():
    """The middleware is wired with the module-level _MAX_REQUEST_BYTES constant,
    not a hard-coded value — operators can tune it via PALINODE_MAX_REQUEST_BYTES.
    """
    for mw in server.app.user_middleware:
        if mw.cls is server._BodySizeLimitMiddleware:
            assert mw.kwargs["max_bytes"] == server._MAX_REQUEST_BYTES
            return
    pytest.fail("BodySizeLimitMiddleware not registered on the app")
