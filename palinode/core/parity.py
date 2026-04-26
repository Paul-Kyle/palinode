"""
Cross-surface parity registry — the canonical-names contract for ADR-010.

Every memory operation that should appear on more than one surface
(CLI, MCP, REST API, OpenClaw plugin) is enumerated here with one
canonical name per parameter and one canonical shape (type + required
flag).  ``tests/test_surface_parity.py`` walks this registry and asserts
each surface conforms.

When you add a parameter to one surface, add it here first, then
mirror to the others.  When the four surfaces drift, record the drift
in ``known_drift`` with the GitHub issue number — the test xfails the
drift entry until the issue closes.

Admin-only operations (reindex, migrations, doctor, etc.) are explicitly
exempt from parity by listing them in ``ADMIN_EXEMPT_OPERATIONS``.  The
contract is "all memory operations are equivalent across surfaces, by
design"; it is *not* "all operations appear everywhere".

See ``ADR-010-cross-surface-parity-contract.md`` and ``docs/PARITY.md``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ParamType = Literal["string", "boolean", "array", "integer", "number", "object"]
Surface = Literal["cli", "mcp", "api", "plugin"]


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CanonicalParam:
    """One parameter, named and shaped as it should appear on every surface."""

    name: str
    type: ParamType
    required: bool = False
    #: If the default is shared across surfaces, this is the attribute name in
    #: ``palinode.core.defaults``.  ``None`` means "no default" or "surface-
    #: specific default that we accept by design".
    default_key: str | None = None
    #: Closed set of allowed values, if any.  Surfaces that expose an enum
    #: must use this exact tuple (order-insensitive).
    enum: tuple[str, ...] | None = None
    notes: str = ""


@dataclass(frozen=True)
class Operation:
    """A memory operation with its canonical params and per-surface mapping."""

    name: str
    canonical_params: tuple[CanonicalParam, ...]
    cli_command: str | None = None
    mcp_tool: str | None = None
    api_endpoint: tuple[str, str] | None = None  # (METHOD, path)
    plugin_tool: str | None = None
    #: Surfaces in this set are *not* required to expose the operation.
    #: Useful when something is intentionally CLI-only (admin) or
    #: API-only (internal observability) — see ``ADMIN_EXEMPT_OPERATIONS``
    #: for the global admin carve-out.
    exempt_surfaces: frozenset[Surface] = field(default_factory=frozenset)
    #: Known drift, keyed by ``(surface, param_name)``.  Value is the GitHub
    #: issue number tracking the fix.  The parity test reports these as xfail
    #: with the issue ref — once the issue closes and the surface is fixed,
    #: remove the entry and the test enforces.
    known_drift: dict[tuple[Surface, str], int] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Admin carve-out
# ─────────────────────────────────────────────────────────────────────────────


#: Operations that are intentionally NOT subject to cross-surface parity.
#: They appear on whichever surfaces make operational sense (typically CLI +
#: API, sometimes only one).  Adding parity for these requires a new ADR.
ADMIN_EXEMPT_OPERATIONS: frozenset[str] = frozenset(
    {
        # Full-database operations (CLI + API only)
        "reindex",
        "rebuild-fts",
        "split-layers",
        "bootstrap-fact-ids",
        # One-off importers (CLI + API only)
        "migrate-openclaw",
        "migrate-mem0",
        # Local / operational (CLI only)
        "doctor",
        "start",
        "stop",
        "config",
        "banner",
        # Observability internals (API only)
        "health",
        "git-stats",
        "generate-summaries",
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# Canonical category + type sets
# ─────────────────────────────────────────────────────────────────────────────


#: The canonical ``category`` enum.  Matches the memory-directory names
#: (plural) — that is the value the ``chunks.category`` column stores
#: (``palinode/api/server.py:660-668`` and the watcher's directory-basename
#: derivation).  Surfaces that expose a ``category`` filter MUST use
#: this exact tuple — ADR-010, finding #161.
CATEGORIES: tuple[str, ...] = (
    "people",
    "projects",
    "decisions",
    "insights",
    "research",
)

#: The canonical memory ``type`` enum (used by save).  Lives here so
#: the API can validate ``SaveRequest.type`` server-side instead of
#: relying on per-surface enum lists.  ADR-010, finding #166.
MEMORY_TYPES: tuple[str, ...] = (
    "PersonMemory",
    "Decision",
    "ProjectSnapshot",
    "Insight",
    "ResearchRef",
    "ActionItem",
)

#: The canonical prompt-task enum.  Single source replacing the duplicate
#: ``"enum"`` keys at ``palinode/mcp.py:624-625``.  ADR-010, finding #162.
PROMPT_TASKS: tuple[str, ...] = (
    "compaction",
    "extraction",
    "update",
    "classification",
    "nightly-consolidation",
)


# ─────────────────────────────────────────────────────────────────────────────
# The registry
# ─────────────────────────────────────────────────────────────────────────────


REGISTRY: tuple[Operation, ...] = (
    # ── status ──────────────────────────────────────────────────────────────
    Operation(
        name="status",
        canonical_params=(),
        cli_command="status",
        mcp_tool="palinode_status",
        api_endpoint=("GET", "/status"),
    ),
    # ── list ────────────────────────────────────────────────────────────────
    Operation(
        name="list",
        canonical_params=(
            CanonicalParam(name="category", type="string", enum=CATEGORIES),
            CanonicalParam(name="core_only", type="boolean"),
        ),
        cli_command="list",
        mcp_tool="palinode_list",
        api_endpoint=("GET", "/list"),
        exempt_surfaces=frozenset({"plugin"}),
    ),
    # ── read ────────────────────────────────────────────────────────────────
    Operation(
        name="read",
        canonical_params=(
            CanonicalParam(name="file_path", type="string", required=True),
            CanonicalParam(name="meta", type="boolean"),
        ),
        cli_command="read",
        mcp_tool="palinode_read",
        api_endpoint=("GET", "/read"),
        exempt_surfaces=frozenset({"plugin"}),
        known_drift={},
    ),
    # ── search ──────────────────────────────────────────────────────────────
    Operation(
        name="search",
        canonical_params=(
            CanonicalParam(name="query", type="string", required=True),
            CanonicalParam(
                name="limit", type="integer", default_key="SEARCH_LIMIT_DEFAULT"
            ),
            CanonicalParam(name="category", type="string", enum=CATEGORIES),
            CanonicalParam(
                name="threshold",
                type="number",
                default_key="SEARCH_THRESHOLD_DEFAULT",
            ),
            CanonicalParam(name="since_days", type="integer"),
            CanonicalParam(name="types", type="array"),
            CanonicalParam(name="date_after", type="string"),
            CanonicalParam(name="date_before", type="string"),
            CanonicalParam(name="include_daily", type="boolean"),
        ),
        cli_command="search",
        mcp_tool="palinode_search",
        api_endpoint=("POST", "/search"),
        plugin_tool="palinode_search",
        known_drift={
            # #176: plugin TS schema for ``palinode_search`` only exposes
            # ``query``, ``category``, ``limit`` — the six post-#163 search
            # filters need to be declared in the plugin's TypeBox schema in
            # ``plugin/index.ts`` and wired through to the API call.  All
            # 11 plugin known_drift entries (search × 6 + save × 5) are
            # tracked together in #176; each closes when the plugin
            # declares the param and the entry is removed from this dict
            # (the TS parity test fails otherwise — that's the forcing
            # function).
            ("plugin", "threshold"): 176,
            ("plugin", "since_days"): 176,
            ("plugin", "types"): 176,
            ("plugin", "date_after"): 176,
            ("plugin", "date_before"): 176,
            ("plugin", "include_daily"): 176,
        },
    ),
    # ── save ────────────────────────────────────────────────────────────────
    # NOTE on ``ps``: deliberately *not* a canonical parameter.  CLI ``--ps``
    # and MCP ``ps`` are surface sugar that resolves to ``type=ProjectSnapshot``
    # locally before hitting the API.  Documented in ``docs/PARITY.md``;
    # surfaces are free to add the shortcut without parity overhead.  The
    # plugin currently lacks it (#166 expansion), but adding it is a plugin
    # courtesy, not a parity obligation.
    Operation(
        name="save",
        canonical_params=(
            CanonicalParam(name="content", type="string", required=True),
            CanonicalParam(name="type", type="string", enum=MEMORY_TYPES),
            CanonicalParam(name="entities", type="array"),
            CanonicalParam(name="project", type="string"),
            CanonicalParam(name="metadata", type="object"),
            CanonicalParam(name="confidence", type="number"),
            CanonicalParam(name="title", type="string"),
            CanonicalParam(name="slug", type="string"),
            CanonicalParam(name="core", type="boolean"),
            CanonicalParam(name="source", type="string"),
        ),
        cli_command="save",
        mcp_tool="palinode_save",
        api_endpoint=("POST", "/save"),
        plugin_tool="palinode_save",
        known_drift={
            # #176: plugin TS schema for ``palinode_save`` lacks
            # ``project`` (originally #159), ``metadata``, ``confidence``,
            # ``title``, ``source`` (the latter four originally #166).
            # All five — together with the six search-side gaps — are now
            # tracked under #176, the dedicated plugin-schema-closure
            # tracking issue.  ``type`` was in this list during ADR-010's
            # first wave, but the plugin's ``palinode_save`` TypeBox
            # schema actually declares ``type``; the TS parity test at
            # ``plugin/test/parity.test.ts`` surfaced the stale entry, so
            # it has been removed.  ``title`` and ``source`` are real
            # plugin gaps surfaced by the same test.
            ("plugin", "project"): 176,
            ("plugin", "metadata"): 176,
            ("plugin", "confidence"): 176,
            ("plugin", "title"): 176,
            ("plugin", "source"): 176,
        },
    ),
    # ── consolidate ─────────────────────────────────────────────────────────
    Operation(
        name="consolidate",
        canonical_params=(
            CanonicalParam(name="dry_run", type="boolean"),
            CanonicalParam(name="nightly", type="boolean"),
        ),
        cli_command="consolidate",
        mcp_tool="palinode_consolidate",
        api_endpoint=("POST", "/consolidate"),
        exempt_surfaces=frozenset({"plugin"}),
        known_drift={},
    ),
    # ── trigger (create) ────────────────────────────────────────────────────
    # Trigger is multi-action.  We model the most cross-surface-relevant one,
    # ``create``, and let the others (list, delete) be tested via simpler
    # presence-only checks (or as separate Operation entries when they have
    # parameters worth pinning).
    Operation(
        name="trigger.create",
        canonical_params=(
            CanonicalParam(name="description", type="string", required=True),
            CanonicalParam(name="memory_file", type="string", required=True),
            CanonicalParam(name="trigger_id", type="string"),
            CanonicalParam(
                name="threshold",
                type="number",
                default_key="TRIGGER_THRESHOLD_DEFAULT",
            ),
            CanonicalParam(
                name="cooldown_hours",
                type="integer",
                default_key="TRIGGER_COOLDOWN_HOURS_DEFAULT",
            ),
        ),
        cli_command="trigger add",
        mcp_tool="palinode_trigger",
        api_endpoint=("POST", "/triggers"),
        exempt_surfaces=frozenset({"plugin"}),
        known_drift={},
    ),
    # ── rollback ────────────────────────────────────────────────────────────
    Operation(
        name="rollback",
        canonical_params=(
            CanonicalParam(name="file_path", type="string", required=True),
            CanonicalParam(name="commit", type="string"),
            CanonicalParam(name="dry_run", type="boolean"),
        ),
        cli_command="rollback",
        mcp_tool="palinode_rollback",
        api_endpoint=("POST", "/rollback"),
        exempt_surfaces=frozenset({"plugin"}),
        known_drift={},
    ),
    # ── blame ───────────────────────────────────────────────────────────────
    Operation(
        name="blame",
        canonical_params=(
            CanonicalParam(name="file_path", type="string", required=True),
            CanonicalParam(name="search", type="string"),
        ),
        cli_command="blame",
        mcp_tool="palinode_blame",
        api_endpoint=("GET", "/blame/{file_path:path}"),
        exempt_surfaces=frozenset({"plugin"}),
        known_drift={},
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def by_name(op_name: str) -> Operation:
    """Look up an operation by name.  Raises ``KeyError`` if missing."""
    for op in REGISTRY:
        if op.name == op_name:
            return op
    raise KeyError(op_name)


def required_surfaces(op: Operation) -> frozenset[Surface]:
    """Return the surfaces this operation must appear on (i.e. not exempt)."""
    all_surfaces: frozenset[Surface] = frozenset({"cli", "mcp", "api", "plugin"})
    return all_surfaces - op.exempt_surfaces


__all__ = [
    "ADMIN_EXEMPT_OPERATIONS",
    "CATEGORIES",
    "CanonicalParam",
    "MEMORY_TYPES",
    "Operation",
    "PROMPT_TASKS",
    "ParamType",
    "REGISTRY",
    "Surface",
    "by_name",
    "required_surfaces",
]
