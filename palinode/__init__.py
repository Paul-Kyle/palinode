"""
Palinode — Persistent memory for AI agents.

Files as truth. Vectors as search. Prompts as source code.

Components:
    core/       — Config, embeddings, storage, markdown parsing
    api/        — FastAPI HTTP server
    indexer/    — File watcher daemon (auto-indexes on save)
    ingest/     — Ingestion pipeline (PDF, audio, URL, text)
    mcp.py      — MCP server for Claude Code integration
    cli.py      — Command-line interface
"""
from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("palinode")
except PackageNotFoundError:  # pragma: no cover — only when running from a non-installed checkout
    __version__ = "0.0.0+unknown"
