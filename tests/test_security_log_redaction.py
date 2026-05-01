"""L4: log redaction filter must scrub credentials from messages and tracebacks."""
from __future__ import annotations

import io
import logging
import time


def _make_logger() -> tuple[logging.Logger, io.StringIO]:
    from palinode.api.server import SecretRedactingFilter

    log = logging.getLogger(f"palinode.test.redact.{time.time_ns()}")
    log.setLevel(logging.DEBUG)
    log.handlers.clear()
    log.propagate = False
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(SecretRedactingFilter())
    log.addHandler(handler)
    return log, buf


def test_redacts_openai_style_key() -> None:
    log, buf = _make_logger()
    log.warning("token leaked: sk-abcdefghijklmnopqrstuvwxyz0123456789")
    out = buf.getvalue()
    assert "sk-abcdefghij" not in out
    assert "***REDACTED***" in out


def test_redacts_anthropic_style_key() -> None:
    log, buf = _make_logger()
    log.warning("got sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAA")
    out = buf.getvalue()
    assert "sk-ant-api03-AAAA" not in out
    assert "sk-ant-***REDACTED***" in out


def test_redacts_slack_token() -> None:
    log, buf = _make_logger()
    log.warning("slack: xoxb-1234567890-ABCDEFGHIJKL")
    out = buf.getvalue()
    assert "xoxb-1234567890-ABCDEFGHIJKL" not in out
    assert "***REDACTED***" in out


def test_redacts_aws_access_key() -> None:
    log, buf = _make_logger()
    log.warning("aws key found: AKIAIOSFODNN7EXAMPLE")
    out = buf.getvalue()
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "AKIA***REDACTED***" in out


def test_redacts_basic_auth_url() -> None:
    log, buf = _make_logger()
    log.warning("connect to https://alice:hunter2@example.com/api")
    out = buf.getvalue()
    assert "hunter2" not in out
    assert "alice:***REDACTED***@" in out


def test_redacts_authorization_header() -> None:
    log, buf = _make_logger()
    log.warning(
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGH"
    )
    out = buf.getvalue()
    assert "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGH" not in out
    assert "***REDACTED***" in out


def test_redacts_api_key_assignment() -> None:
    log, buf = _make_logger()
    log.warning("config: api_key=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    out = buf.getvalue()
    assert "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" not in out
    assert "***REDACTED***" in out


def test_redacts_traceback_text() -> None:
    """logger.exception() must scrub traceback content too."""
    log, buf = _make_logger()
    try:
        raise RuntimeError(
            "kaboom: leaked sk-abcdefghijklmnopqrstuvwxyz0123456789"
        )
    except RuntimeError:
        log.exception("oops")
    out = buf.getvalue()
    assert "sk-abcdefghij" not in out
    assert "***REDACTED***" in out


def test_no_op_on_clean_message() -> None:
    log, buf = _make_logger()
    log.warning("nothing sensitive here, just a normal log line")
    assert buf.getvalue().strip() == "nothing sensitive here, just a normal log line"


def test_args_substitution_works() -> None:
    log, buf = _make_logger()
    log.warning("user=%s key=%s", "alice", "sk-abcdefghijklmnopqrstuvwxyz0123456789")
    out = buf.getvalue()
    assert "user=alice" in out
    assert "sk-abcdefghij" not in out
