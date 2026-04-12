# ADR-007: Access Metadata Schema + DecayConfig Enable

**Status:** Planned — not yet drafted
**Depends on:** ADR-004 shipped
**Related:** Consolidation improvements

## What this ADR will decide

Two coupled decisions:
1. **Schema for access metadata** — how to track `last_retrieved_at`, `retrieval_count`, and possibly `last_modified_at` per memory file.
2. **Enable `DecayConfig`** — turn on the existing (but disabled) decay configuration in `palinode/core/config.py` and use its tau values as a ranker term.

These are in the same ADR because the decay ranker term can't exist without access metadata to feed it.

## What this ADR will NOT decide

- Whether to delete files based on decay. Nothing gets deleted. Decay is a ranker weight only.
- Whether to compact / archive based on decay. Separate decision (probably ADR-005 territory).
- On-read reconsolidation (ADR-006) — although access metadata is a prerequisite for ADR-006, the decision of *whether* to build ADR-006 is independent of this one.

## Prerequisites before drafting

- [ ] ADR-004 shipped (write-time contradiction check) — this ADR touches the same save path
- [ ] Real data on how often files are actually retrieved in a typical week (so tau tuning has ground truth)
- [ ] Real data on retrieval distribution — long-tailed or uniform? Informs whether decay actually matters

## Questions to think through when writing

### Where does access metadata live?

**Three-way tension:**

1. **Frontmatter in the file itself.** Source of truth, git-diffable, survives everything. But: every retrieval causes a file write, which causes a git commit, which causes a watcher reindex, which is expensive and noisy.

2. **SQLite table in `.palinode.db`.** Fast to update, fast to query from the ranker. But: not part of the source-of-truth markdown, can drift from file state, lost if the db is rebuilt.

3. **Hybrid: SQLite is live, periodic flush to frontmatter.** Best of both, but adds a "flush" operation that has its own failure modes.

My current lean (not a decision): **SQLite only for live access metadata, no frontmatter persistence.** Rationale: access metadata is ephemeral by nature — it's a signal about what's hot *right now*. If the db is rebuilt, the ranker resets to "everything is equally cold," which is a fine reset state. Not losing information you can't reconstruct.

But: if ADR-006 ever wants to use retrieval history ("this file was retrieved 10 times last week, so it's important"), SQLite-only breaks that. Worth weighing.

### What fields does the schema need?

Minimum:
- `file_path` (PK)
- `last_retrieved_at` (timestamp)
- `retrieval_count` (integer, monotonic)

Possibly:
- `last_retrieved_by` (session id? user id? source surface like "claude-code"?)
- `retrieval_count_7d` / `retrieval_count_30d` (decay-window counts, maintained by a sweeper)
- `last_modified_at` (file mtime at last index)
- `contradiction_check_count` (how many times tier 2a has run on this file)

Don't add fields speculatively. Add only what the ranker or a future ADR concretely needs.

### What's a "retrieval"?

Same question as ADR-006 (see that ADR for the option list). The choice here matters for decay:
- If automatic context injection counts as a retrieval, every file in core memory gets bumped on every turn → "core" never decays → access metadata is useless as a ranker signal
- If only explicit tool calls count, decay has signal but core files look stale → the ranker might downrank core files, which is wrong

**Likely answer:** access metadata distinguishes *explicit* reads (tool calls) from *passive* injection. Only explicit reads update `retrieval_count`. Passive injection updates `last_injected_at` separately, or not at all.

This is a schema-design decision that has to be made in ADR-007.

### Is decay actually useful?

The existing `DecayConfig` has tau values:
- `tau_critical: 180` days
- `tau_decisions: 60`
- `tau_insights: 90`
- `tau_general: 30`
- `tau_status: 7`
- `tau_ephemeral: 1`

These are guesses from before any data existed. Before this ADR can ship a "use decay in the ranker" decision, we need:
- Evidence that unused memories are actually hurting the ranker (e.g., stale status files surfacing in search results ahead of current ones)
- Empirical tau values, tuned from real retrieval patterns

If neither of those is in hand, the ADR should narrow to **"add access metadata schema only, defer decay enabling."** Half an ADR.

### How does this interact with the ranker?

Current ranker (`palinode/core/store.py`) uses hybrid BM25 + vector similarity fused via RRF. Adding a decay term means:
- Either multiply the existing RRF score by a decay factor (e.g., `score * exp(-age / tau)`)
- Or add decay as a third signal in the fusion

The ADR needs to pick one and justify it. Multiplication is simpler but makes decay dominate when age is large; fusion is more principled but introduces a tuning parameter.

### How does this interact with the watcher?

The watcher daemon reindexes on file modify. If access metadata is in frontmatter, every retrieval triggers a file modify, which triggers a reindex, which could create a feedback loop.

If access metadata is SQLite-only (my current lean), the watcher doesn't need to know about it at all — it stays focused on content indexing.

### Failure modes

- SQLite table corrupts → ranker loses decay signal, search still works (falls back to BM25+vector only)
- Access metadata gets out of sync with actual file state → stale last_retrieved_at, but self-corrects on next retrieval
- Ranker heavily favors recently-retrieved files → recency bias → user complains about "why does it keep showing me the thing I just read?" Need a brake.

### What telemetry do we need to tune tau?

- Histogram of retrieval intervals per file (time between retrievals)
- Distribution of retrieval_count per file at end of a week
- Correlation between "last retrieved > X days ago" and "never retrieved again" (predictive value of decay)

Without telemetry, tuning tau is guessing. The ADR should ship telemetry alongside the feature.

## Draft scope when written

Single coupled decision: access metadata schema + enable decay as ranker term. The two are bundled because one can't ship without the other (decay needs metadata to read from).

Possible split: ship access metadata schema alone first (ADR-007a), then decide decay enabling separately (ADR-007b) after the metadata has been collecting data for a few weeks. This is probably the right move if real data isn't available at draft time.

Explicitly out of scope: on-read reconsolidation (ADR-006), decay-based deletion (never — not a thing we do), decay-based archival (ADR-005 territory).

## Revisit trigger

Draft this ADR when:
- ADR-004 has been in production long enough that we can instrument retrieval
- OR we hit a concrete ranker problem that access metadata would solve (stale results outranking fresh ones in user-visible search output)
- OR we decide we want ADR-006 and need access metadata as a prerequisite

No rush. This ADR is valuable but not urgent.
