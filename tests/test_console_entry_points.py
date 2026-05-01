from __future__ import annotations

from importlib.metadata import entry_points


EXPECTED_CONSOLE_SCRIPTS = {
    "palinode": "palinode.cli:main",
    "palinode-api": "palinode.api.server:main",
    "palinode-watcher": "palinode.indexer.watcher:main",
    "palinode-mcp": "palinode.mcp:main",
    "palinode-mcp-http": "palinode.mcp:main_http",
    "palinode-mcp-sse": "palinode.mcp:main_sse",
}


def test_console_entry_points_resolve() -> None:
    scripts = {entry_point.name: entry_point for entry_point in entry_points(group="console_scripts")}
    missing = sorted(set(EXPECTED_CONSOLE_SCRIPTS) - set(scripts))
    assert missing == []

    for name, expected_value in EXPECTED_CONSOLE_SCRIPTS.items():
        entry_point = scripts[name]
        assert entry_point.value == expected_value
        entry_point.load()
