# ADR-008: Ambient Context Search

**Status:** Proposed
**Date:** 2026-04-12
**Related:** Paul-Kyle/palinode#28

## Problem

With 80+ project files across 5+ domains (e.g. palinode, other-project, coursework, infrastructure), search results from unrelated projects drown out relevant ones. A search for "tier 2a ADR-004" from the palinode CWD returns other projects' ADRs ranked above the palinode-specific memory — even though the palinode memory exists, has the exact slug, and is tagged `project/palinode`.

This problem scales linearly with memory count. At 500+ files it will be unusable without context awareness.

## Decision

Add **multi-signal ambient context** as a scoring channel in the existing RRF hybrid search pipeline. Context is assembled automatically from the caller's environment and maintained as server-side session state.

### Core mechanism

After RRF fusion computes scores for semantic + BM25 channels, apply a multiplicative boost to results whose file_paths match the resolved context. The boost is soft (not a filter) — cross-project results still appear if genuinely the best semantic match.

### Context signals (phased)

**Phase 1 (v1):** Project entity from CWD mapping + recently accessed files this session.

**Phase 2:** Conversation entity extraction, git branch signal, session warm-start from previous session context snapshots.

**Phase 3:** Source surface weighting, learned weights from access patterns.

### Server-side session state

Context lives in the API server, not the conversation. This means:
- Context **survives client-side compaction** (MCP connection persists)
- Context **rebuilds on /clear** (SessionStart hook re-primes)
- Context **grows during session** (each search enriches recently_accessed)
- Context **carries across sessions** (lightweight warm-start snapshots)

### Context resolution

```
CWD → basename → config.context.project_map lookup
  ↓ (fallback if auto_detect=true)
basename → check entities table for project/{basename}
  ↓ (fallback)
No context → no boost → current behavior
```

### Embedding the context signal

The context signal can also be embedded as a query-time augmentation: prepend "In the context of project palinode:" to the query text before embedding, giving the semantic channel itself project awareness. This is cheap (one modified string before the existing embed call) and complementary to the entity-based boost.

## Alternatives considered

1. **Hard filter by entity** — Too aggressive. Cross-project memories (e.g., infrastructure affecting palinode) would be excluded.
2. **Separate indexes per project** — Breaks cross-project search entirely. Wrong architecture for a system that serves one human across multiple projects.
3. **Rely on the agent to pass filters** — Current state. Fails because agents don't reliably pass context, and the agent itself (this conversation) failed to search correctly.
4. **Client-side context only** — Dies on compaction/clear. Server-side state is the right home.

## Consequences

- Search results become project-aware without any change to caller behavior
- Existing search behavior preserved when no context is available (boost = 1.0)
- New config section: `context.*` in palinode.config.yaml
- New API endpoints: `/context/prime`, `/context/save`
- New hook: `palinode-session-start.sh` (SessionStart)
- New module: `palinode/core/context.py`
- New MCP tool (optional): `palinode_context` for explicit context override

## Prior art

No existing AI memory system (Mem0, Zep, Letta, LangMem, Cognee, Bedrock AgentCore) automatically fuses ambient context signals for retrieval boosting. All require explicit metadata filters or agent self-management.

Closest academic work: STITCH (arXiv:2601.10702) — contextual intent indexing, 35.6% improvement over baselines. SuperLocalMemory V3.3 — 4-channel RRF fusion but no workspace awareness. Full research survey saved to palinode memory: `insights/context-aware-retrieval-research-2026-04-12.md`.
