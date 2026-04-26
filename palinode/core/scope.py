"""ADR-009 Layer 1: scope chain resolution.

Build a ScopeChain from config + env + caller-supplied project/session, to be
consumed by scope-filtered search (Slice 3) and the context prime endpoint
(Slice 4). This module is pure resolution — no I/O, no DB, no filtering.
Isolating it here keeps subsequent slices easy to test.

See ADR-009 §3.1-3.2 for the hierarchy and auto-detection rules.
"""
from __future__ import annotations

from dataclasses import dataclass

from palinode.core.config import Config


@dataclass(frozen=True)
class ScopeChain:
    """Ordered scope chain from narrowest (session) to broadest (org).

    Each level is an entity ref string (e.g. ``project/palinode``).
    Unset levels are dropped when serialized via :meth:`as_list`.
    The order of :meth:`as_list` is the search-priority order: earlier
    entries are more specific and take precedence over later ones.
    """
    session: str | None = None
    agent: str | None = None
    harness: str | None = None
    project: str | None = None
    member: str | None = None
    org: str | None = None

    def as_list(self) -> list[str]:
        """Return the chain as entity refs, narrow → broad, omitting unset levels."""
        entries: list[tuple[str, str | None]] = [
            ("session", self.session),
            ("agent", self.agent),
            ("harness", self.harness),
            ("project", self.project),
            ("member", self.member),
            ("org", self.org),
        ]
        return [f"{kind}/{value}" for kind, value in entries if value]

    def is_empty(self) -> bool:
        """True when no levels are set (caller has zero scoping context)."""
        return not self.as_list()


def resolve_scope_chain(
    cfg: Config,
    project: str | None = None,
    session_id: str | None = None,
) -> ScopeChain:
    """Resolve the scope chain for the current session.

    ``project`` should be the caller-resolved project entity name (typically
    supplied by the ADR-008 ambient-context detection). Pass ``None`` in
    pre-ADR-008 setups or when the caller has no project signal.

    ``session_id`` is the caller-generated session identifier. Pass ``None``
    when session-level scoping is not in use.

    Other levels are read from :class:`ScopeConfig` (env vars override YAML).
    """
    s = cfg.scope
    return ScopeChain(
        session=session_id,
        agent=s.agent,
        harness=s.harness,
        project=project,
        member=s.member,
        org=s.org,
    )
