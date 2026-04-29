"""
Retrieval Event Logger — Issue #256

Append-only JSONL log of every memory-file retrieval, distinguishing
explicit tool calls from passive auto-injection.  Pure observability;
no ranker behavior change.

Log path: <memory_dir>/.audit/retrievals.jsonl
(parallel to the existing mcp-calls.jsonl audit log)

Each entry is a RetrievalEvent serialized as a single JSON line.

Disable globally: set PALINODE_INSTRUMENTATION_DISABLED=1 in env,
or set instrumentation.capture_retrievals: false in palinode.config.yaml.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger("palinode.retrieval_log")

_LOG_FILENAME = "retrievals.jsonl"


# ── Event schema ──────────────────────────────────────────────────────────────


@dataclass
class RetrievalEvent:
    """One retrieval of a memory file or chunk."""

    timestamp: str          # ISO-8601 UTC
    file_path: str          # relative to memory_dir (or absolute — logged as-is)
    chunk_id: str | None    # chunk PK if chunk-level (search returns chunks)
    mode: Literal["explicit", "passive"]  # explicit = tool call; passive = auto-inject / scope-chain
    source: str             # e.g. "palinode_search", "palinode_read", "auto_inject"
    query: str | None       # search query if applicable
    rank: int | None        # 0-based rank in result list
    score: float | None     # RRF / cosine score
    session_id: str | None  # MCP/HTTP session identifier when available


# ── Logger class ──────────────────────────────────────────────────────────────


class RetrievalLogger:
    """Append-only JSONL logger for retrieval events.

    Writes are best-effort: any I/O error is logged at WARNING level and
    swallowed so retrieval performance is never affected.

    Disable flag precedence:
      1. PALINODE_INSTRUMENTATION_DISABLED=1 env var (runtime kill-switch)
      2. instrumentation.capture_retrievals config key (default True)
    """

    def __init__(self, memory_dir: str, *, enabled: bool = True) -> None:
        # Env-var kill-switch overrides config
        env_disabled = os.environ.get("PALINODE_INSTRUMENTATION_DISABLED", "").strip()
        if env_disabled in ("1", "true", "yes"):
            self._enabled = False
            self._path: Path | None = None
            return

        self._enabled = enabled
        if not self._enabled:
            self._path = None
            return

        self._path = Path(memory_dir) / ".audit" / _LOG_FILENAME
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Cannot create retrieval-log directory %s: %s", self._path.parent, exc)
            self._enabled = False
            self._path = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def log_path(self) -> Path | None:
        return self._path

    def record(self, event: RetrievalEvent) -> None:
        """Append *event* to the JSONL log.  Never raises."""
        if not self._enabled or self._path is None:
            return
        entry = asdict(event)
        try:
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, separators=(",", ":"), default=str) + "\n")
        except OSError as exc:
            logger.warning("Retrieval-log write failed: %s", exc)

    def record_search_results(
        self,
        results: list[dict],
        *,
        query: str | None,
        source: str,
        mode: Literal["explicit", "passive"],
        session_id: str | None = None,
    ) -> None:
        """Emit one RetrievalEvent per result in *results*.

        Called after ``store.search_hybrid`` / ``store.search`` returns so we
        capture the actual file paths surfaced to the caller.
        """
        if not self._enabled:
            return
        ts = datetime.now(timezone.utc).isoformat()
        for rank, r in enumerate(results):
            self.record(RetrievalEvent(
                timestamp=ts,
                file_path=r.get("file_path", ""),
                chunk_id=r.get("section_id"),
                mode=mode,
                source=source,
                query=query,
                rank=rank,
                score=r.get("score"),
                session_id=session_id,
            ))

    def record_file_read(
        self,
        file_path: str,
        *,
        source: str,
        mode: Literal["explicit", "passive"],
        session_id: str | None = None,
    ) -> None:
        """Emit a single RetrievalEvent for a whole-file read."""
        if not self._enabled:
            return
        self.record(RetrievalEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            file_path=file_path,
            chunk_id=None,
            mode=mode,
            source=source,
            query=None,
            rank=None,
            score=None,
            session_id=session_id,
        ))
