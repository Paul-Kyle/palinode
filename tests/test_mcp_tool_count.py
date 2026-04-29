"""
Test: MCP tool count consistency

Ensures that docs/MCP-SETUP.md's available-tools table and palinode/mcp.py's
registered tools stay in sync.  This test is the enforcement mechanism for
Option C of issue #238 — prose tool counts are removed from docs; the table
itself is the source of truth, and this assertion catches any drift.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
MCP_SETUP_MD = REPO_ROOT / "docs" / "MCP-SETUP.md"
MCP_PY = REPO_ROOT / "palinode" / "mcp.py"


def _count_docs_table_rows() -> int:
    """Count rows in the available-tools table in MCP-SETUP.md.

    Lines that start with '| palinode_' (after stripping whitespace) are tool
    rows.  The header and separator lines do not match this pattern.
    """
    text = MCP_SETUP_MD.read_text(encoding="utf-8")
    rows = [
        line
        for line in text.splitlines()
        if re.match(r"\|\s*`palinode_", line)
    ]
    return len(rows)


def _count_registered_tools() -> int:
    """Count tools registered in palinode/mcp.py.

    Looks for ``name="palinode_`` inside the list_tools return value.
    Each such occurrence is one registered tool.
    """
    text = MCP_PY.read_text(encoding="utf-8")
    return len(re.findall(r'name="palinode_', text))


def test_mcp_tool_count_matches_docs() -> None:
    docs_count = _count_docs_table_rows()
    code_count = _count_registered_tools()
    assert docs_count == code_count, (
        f"docs/MCP-SETUP.md table has {docs_count} rows "
        f"but palinode/mcp.py registers {code_count} tools. "
        "Update the docs table (or mcp.py) so they match."
    )
