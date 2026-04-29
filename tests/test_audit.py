"""Tests for #116: MCP audit log (structured JSON tool call logging)."""
import json
import os
import time

import pytest

from palinode.core.audit import AuditLogger, _sanitize_arguments
from palinode.core.config import AuditConfig


@pytest.fixture
def audit_dir(tmp_path):
    """Provide a temp directory for audit logs."""
    return tmp_path


@pytest.fixture
def audit_logger(audit_dir):
    """Create an AuditLogger writing to a temp directory."""
    cfg = AuditConfig(enabled=True, log_path=".audit/mcp-calls.jsonl")
    return AuditLogger(str(audit_dir), cfg)


def _read_entries(logger: AuditLogger) -> list[dict]:
    """Read all JSONL entries from the audit log."""
    path = logger.log_path
    assert path is not None
    if not path.exists():
        return []
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


class TestSanitizeArguments:
    def test_short_values_unchanged(self):
        args = {"query": "hello", "limit": 5}
        result = _sanitize_arguments(args)
        assert result == args

    def test_long_content_truncated(self):
        long_text = "x" * 300
        result = _sanitize_arguments({"content": long_text})
        assert len(result["content"]) == 203  # 200 + "..."
        assert result["content"].endswith("...")

    def test_long_query_truncated(self):
        long_query = "search " * 50
        result = _sanitize_arguments({"query": long_query})
        assert len(result["query"]) <= 204  # 200 + "..."

    def test_non_truncate_fields_left_alone(self):
        long_value = "y" * 500
        result = _sanitize_arguments({"file_path": long_value, "category": "people"})
        assert result["file_path"] == long_value

    def test_non_string_values_left_alone(self):
        result = _sanitize_arguments({"content": 12345, "limit": 5})
        assert result["content"] == 12345


class TestAuditLogger:
    def test_creates_directory(self, audit_dir):
        cfg = AuditConfig(enabled=True, log_path=".audit/mcp-calls.jsonl")
        logger = AuditLogger(str(audit_dir), cfg)
        assert (audit_dir / ".audit").is_dir()

    def test_log_creates_file(self, audit_logger):
        audit_logger.log_call("palinode_search", {"query": "test"}, 42.5, "success")
        assert audit_logger.log_path.exists()

    def test_log_entry_structure(self, audit_logger):
        audit_logger.log_call(
            "palinode_save",
            {"content": "important decision", "type": "Decision"},
            123.4,
            "success",
        )
        entries = _read_entries(audit_logger)
        assert len(entries) == 1
        entry = entries[0]

        assert entry["tool_name"] == "palinode_save"
        assert entry["arguments"]["content"] == "important decision"
        assert entry["arguments"]["type"] == "Decision"
        assert entry["duration_ms"] == 123.4
        assert entry["status"] == "success"
        assert entry["error"] is None
        assert "timestamp" in entry
        assert "client_info" in entry

    def test_log_error_entry(self, audit_logger):
        audit_logger.log_call(
            "palinode_search",
            {"query": "fail"},
            5.0,
            "error",
            error="Connection refused",
        )
        entries = _read_entries(audit_logger)
        assert len(entries) == 1
        assert entries[0]["status"] == "error"
        assert entries[0]["error"] == "Connection refused"

    def test_multiple_entries_appended(self, audit_logger):
        for i in range(3):
            audit_logger.log_call(f"tool_{i}", {}, float(i), "success")
        entries = _read_entries(audit_logger)
        assert len(entries) == 3
        assert [e["tool_name"] for e in entries] == ["tool_0", "tool_1", "tool_2"]

    def test_content_truncated_in_log(self, audit_logger):
        long_content = "a" * 500
        audit_logger.log_call(
            "palinode_save",
            {"content": long_content, "type": "Insight"},
            10.0,
            "success",
        )
        entries = _read_entries(audit_logger)
        logged_content = entries[0]["arguments"]["content"]
        assert len(logged_content) == 203  # 200 + "..."
        assert logged_content.endswith("...")

    def test_disabled_logger_does_nothing(self, audit_dir):
        cfg = AuditConfig(enabled=False)
        logger = AuditLogger(str(audit_dir), cfg)
        logger.log_call("palinode_search", {"query": "test"}, 10.0, "success")
        assert logger.log_path is None
        # No file created
        assert not (audit_dir / ".audit").exists()

    def test_timestamp_is_iso_format(self, audit_logger):
        audit_logger.log_call("palinode_status", {}, 1.0, "success")
        entries = _read_entries(audit_logger)
        ts = entries[0]["timestamp"]
        # Should be parseable as ISO 8601
        from datetime import datetime
        dt = datetime.fromisoformat(ts)
        assert dt.year >= 2026

    def test_jsonl_format_one_line_per_entry(self, audit_logger):
        audit_logger.log_call("tool_a", {"x": 1}, 1.0, "success")
        audit_logger.log_call("tool_b", {"y": 2}, 2.0, "success")
        with open(audit_logger.log_path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        # Each line is valid JSON
        for line in lines:
            json.loads(line)

    def test_absolute_log_path(self, audit_dir):
        abs_path = str(audit_dir / "custom" / "audit.jsonl")
        cfg = AuditConfig(enabled=True, log_path=abs_path)
        logger = AuditLogger(str(audit_dir), cfg)
        logger.log_call("test", {}, 1.0, "success")
        assert os.path.exists(abs_path)

    def test_client_info_populated(self, audit_logger, monkeypatch):
        monkeypatch.setenv("MCP_CLIENT_NAME", "claude-code")
        monkeypatch.setenv("PALINODE_PROJECT", "project/palinode")
        audit_logger.log_call("palinode_search", {"query": "test"}, 5.0, "success")
        entries = _read_entries(audit_logger)
        ci = entries[0]["client_info"]
        assert ci["harness"] == "claude-code"
        assert ci["project"] == "project/palinode"


class TestAuditConfig:
    def test_defaults(self):
        cfg = AuditConfig()
        assert cfg.enabled is True
        assert cfg.log_path == ".audit/mcp-calls.jsonl"

    def test_config_from_yaml(self):
        """AuditConfig can be overridden."""
        cfg = AuditConfig(enabled=False, log_path="custom/audit.jsonl")
        assert cfg.enabled is False
        assert cfg.log_path == "custom/audit.jsonl"


class TestResolvedAuditLogPath:
    """The resolved config (after load_config) must have an absolute audit path.

    Verifies the fix for #254: a fresh install should not trigger the
    audit_log_writable doctor warning about relative paths.
    """

    def test_resolved_default_is_absolute(self, tmp_path, monkeypatch):
        """When audit.log_path is at the default, load_config resolves it to
        an absolute path under memory_dir."""
        import os
        from palinode.core.config import load_config

        memory_dir = str(tmp_path / "palinode")
        os.makedirs(memory_dir)
        monkeypatch.setenv("PALINODE_DIR", memory_dir)

        cfg = load_config()

        assert os.path.isabs(cfg.audit.log_path), (
            f"audit.log_path should be absolute after load_config; got: {cfg.audit.log_path!r}"
        )
        assert cfg.audit.log_path.startswith(memory_dir), (
            f"audit.log_path should be under memory_dir ({memory_dir}); "
            f"got: {cfg.audit.log_path!r}"
        )

    def test_explicit_absolute_path_preserved(self, tmp_path, monkeypatch):
        """An explicit absolute audit.log_path in user config is unchanged."""
        import os
        import yaml
        from palinode.core.config import load_config

        memory_dir = str(tmp_path / "palinode")
        os.makedirs(memory_dir)

        abs_audit = str(tmp_path / "custom-audit" / "calls.jsonl")
        cfg_file = os.path.join(memory_dir, "palinode.config.yaml")
        with open(cfg_file, "w") as f:
            yaml.dump({"audit": {"log_path": abs_audit}}, f)

        monkeypatch.setenv("PALINODE_DIR", memory_dir)

        cfg = load_config()

        assert cfg.audit.log_path == abs_audit, (
            f"Explicit absolute audit.log_path should be preserved; "
            f"got: {cfg.audit.log_path!r}"
        )

    def test_explicit_relative_path_preserved(self, tmp_path, monkeypatch):
        """An explicit relative audit.log_path set by the user is left alone
        (so the doctor still warns — user made a choice)."""
        import os
        import yaml
        from palinode.core.config import load_config

        memory_dir = str(tmp_path / "palinode")
        os.makedirs(memory_dir)

        relative_path = "my-custom/.audit/calls.jsonl"
        cfg_file = os.path.join(memory_dir, "palinode.config.yaml")
        with open(cfg_file, "w") as f:
            yaml.dump({"audit": {"log_path": relative_path}}, f)

        monkeypatch.setenv("PALINODE_DIR", memory_dir)

        cfg = load_config()

        # Non-default relative path should NOT be auto-resolved — doctor warns
        assert cfg.audit.log_path == relative_path, (
            f"User-set relative audit.log_path should be preserved; "
            f"got: {cfg.audit.log_path!r}"
        )
