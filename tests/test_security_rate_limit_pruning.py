"""L2: rate-limit dict must be pruned + bounded so memory cannot leak."""
from __future__ import annotations

import time

import pytest


@pytest.fixture(autouse=True)
def _isolate_rate_counters():
    from palinode.api import server

    saved = server._rate_counters.copy()
    server._rate_counters.clear()
    yield server
    server._rate_counters.clear()
    server._rate_counters.update(saved)


def test_expired_entries_pruned_on_check(_isolate_rate_counters) -> None:
    s = _isolate_rate_counters
    stale_ts = time.time() - (s._RATE_LIMIT_WINDOW * 3)
    s._rate_counters["1.2.3.4:search"] = {"window_start": stale_ts, "count": 5}
    s._rate_counters["5.6.7.8:search"] = {"window_start": stale_ts, "count": 5}
    ok = s._check_rate_limit("9.9.9.9", "search", limit=10)
    assert ok
    assert "1.2.3.4:search" not in s._rate_counters
    assert "5.6.7.8:search" not in s._rate_counters
    assert "9.9.9.9:search" in s._rate_counters


def test_max_keys_eviction(_isolate_rate_counters) -> None:
    s = _isolate_rate_counters
    max_keys = s._RATE_LIMIT_MAX_KEYS
    now = time.time()
    for i in range(max_keys):
        s._rate_counters[f"10.0.{i // 256}.{i % 256}:search"] = {
            "window_start": now - i,  # older entries get earlier timestamps
            "count": 1,
        }
    assert len(s._rate_counters) == max_keys
    s._check_rate_limit("172.16.0.1", "search", limit=10)
    assert len(s._rate_counters) <= max_keys


def test_normal_traffic_unaffected(_isolate_rate_counters) -> None:
    s = _isolate_rate_counters
    for _ in range(5):
        assert s._check_rate_limit("10.10.10.10", "search", limit=10)
    entry = s._rate_counters["10.10.10.10:search"]
    assert entry["count"] == 5


def test_limit_exceeded_returns_false(_isolate_rate_counters) -> None:
    s = _isolate_rate_counters
    for _ in range(3):
        assert s._check_rate_limit("11.11.11.11", "search", limit=3)
    assert not s._check_rate_limit("11.11.11.11", "search", limit=3)


def test_pruning_does_not_kick_active_window(_isolate_rate_counters) -> None:
    """Within-window same IP: count should keep climbing, not get pruned."""
    s = _isolate_rate_counters
    for _ in range(10):
        s._check_rate_limit("12.12.12.12", "search", limit=100)
    assert s._rate_counters["12.12.12.12:search"]["count"] == 10
