"""
Palinode cross-surface defaults — single source of truth.

Per ADR-010 (Cross-Surface Parity Contract), every parameter default that
appears on more than one surface lives here. Surfaces (CLI, MCP, REST API,
plugin) import from this module rather than baking literals like ``or 0.75``
into surface-specific code paths.

The ``test_surface_parity`` test asserts that the parity registry's
``default_key`` references all resolve here, and that no surface uses a
literal default that contradicts a value defined here.

If a default needs to be configurable, expose it via ``palinode.core.config``
and re-export here. The contract is "one place to look" — not "one place to
hard-code."
"""
from __future__ import annotations

from palinode.core.config import config


# ── Search ───────────────────────────────────────────────────────────────────

#: Default ``limit`` for ``search`` and ``list`` operations.
SEARCH_LIMIT_DEFAULT: int = 3

#: Default similarity ``threshold`` for ``search`` (server-side).  Driven by
#: ``config.search.api_threshold`` so deployments can tune via YAML.
SEARCH_THRESHOLD_DEFAULT: float = config.search.api_threshold

#: Default similarity threshold for ambient/MCP search (typically tighter than
#: explicit search to keep auto-context noise low).  Driven by config.
SEARCH_THRESHOLD_MCP: float = config.search.mcp_threshold


# ── Triggers ─────────────────────────────────────────────────────────────────

#: Default similarity threshold for prospective-recall triggers.
TRIGGER_THRESHOLD_DEFAULT: float = 0.75

#: Default cooldown (in hours) between consecutive firings of the same trigger.
TRIGGER_COOLDOWN_HOURS_DEFAULT: int = 24


# ── Diff / history ───────────────────────────────────────────────────────────

#: Default lookback window (in days) for ``diff``.
DIFF_DAYS_DEFAULT: int = 7

#: Default page size for ``history``.
HISTORY_LIMIT_DEFAULT: int = 20


# ── Save ─────────────────────────────────────────────────────────────────────

#: HTTP request header used to attribute writes to a source surface.
#:
#: Per ADR-010, surfaces SHOULD set this header on every API call rather than
#: putting ``source`` into the body.  The API uses the header value when
#: ``source`` is not in the body, which lets us keep a stable contract while
#: each surface maintains its own attribution.
SAVE_SOURCE_HEADER: str = "X-Palinode-Source"

#: Source attribution sentinel used when the header is absent and no body
#: ``source`` is supplied.  ``"api"`` matches the FastAPI server's prior
#: behavior, so this default does not change observable attribution.
SAVE_SOURCE_API_DEFAULT: str = "api"


# ── Session-end dedup (#126) ─────────────────────────────────────────────────

#: Lookback window (in minutes) over which ``session_end`` checks recently
#: indexed saves for semantic overlap.  60 minutes covers a typical Claude
#: Code session: long enough to catch /ps → /wrap reformulations of the same
#: decision, short enough that two genuinely separate sessions on the same
#: topic don't get conflated.
SESSION_END_DEDUP_WINDOW_MINUTES: int = 60

#: Cosine-similarity threshold above which a recent save is considered a
#: duplicate of the new session-end content.  0.85 is conservative — BGE-M3
#: routinely scores unrelated documents around 0.4-0.6 and near-paraphrases
#: 0.8-0.95.  Above 0.85 we have high confidence the prior save already
#: captures the same semantic information.
SESSION_END_DEDUP_THRESHOLD: float = 0.85


# ── Path validation ──────────────────────────────────────────────────────────

#: Allowed memory-file extensions accepted by ``read``/``list`` and the like.
ALLOWED_MEMORY_EXTENSIONS: tuple[str, ...] = (".md",)


__all__ = [
    "SEARCH_LIMIT_DEFAULT",
    "SEARCH_THRESHOLD_DEFAULT",
    "SEARCH_THRESHOLD_MCP",
    "TRIGGER_THRESHOLD_DEFAULT",
    "TRIGGER_COOLDOWN_HOURS_DEFAULT",
    "DIFF_DAYS_DEFAULT",
    "HISTORY_LIMIT_DEFAULT",
    "SAVE_SOURCE_HEADER",
    "SAVE_SOURCE_API_DEFAULT",
    "SESSION_END_DEDUP_WINDOW_MINUTES",
    "SESSION_END_DEDUP_THRESHOLD",
    "ALLOWED_MEMORY_EXTENSIONS",
]
