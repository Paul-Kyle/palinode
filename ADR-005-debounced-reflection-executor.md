# ADR-005: Debounced Reflection Executor (Tier 2b)

**Status:** Planned — not yet drafted
**Depends on:** ADR-004 shipped and validated in production for at least 2 weeks
**Related:** Consolidation improvements

## What this ADR will decide

Whether to build a background "reflection executor" that coalesces write-time contradiction checks into batched reflection passes, fired by a debounce threshold rather than a wall clock.

Pattern reference: LangMem's `ReflectionExecutor` — fire on N pending events OR K minutes idle, whichever first, reset the timer on new events.

## What this ADR will NOT decide

- Whether to remove the write-time synchronous path from ADR-004. That stays regardless.
- On-read reconsolidation (ADR-006)
- Access metadata schema (ADR-007)

## Prerequisites before drafting

- [ ] ADR-004 (tier 2a) is shipped and has been running in production for ≥ 2 weeks
- [ ] We have real data on write-time check latency under typical load
- [ ] We have real data on LLM call volume and cost under typical load
- [ ] We have real data on contradiction-check accuracy (false positives, missed contradictions)
- [ ] We know whether the async queue from ADR-004 is actually getting backed up, or whether per-save checks are fast enough to not need coalescing

## Questions to think through when writing

### Is this actually needed?

**The whole premise of ADR-005 is that write-time checks need to be coalesced.** If real-world data from ADR-004 shows per-save LLM calls are cheap enough and fast enough that no coalescing is needed, ADR-005 doesn't exist — we just let the tier 2a queue drain naturally and we're done.

Write the first section of ADR-005 as "when ADR-005 should NOT be written": include the concrete metrics (p50 check latency, queue depth, LLM call cost) that would make ADR-005 unnecessary. If those metrics are met by ADR-004 alone, close this ADR with status: "not needed."

### What's the trigger function?

Options to consider:
- **Count-based:** fire after N pending checks accumulate
- **Time-based:** fire K minutes after the most recent save
- **Entity-based:** fire when the same entity file has been touched N times
- **Weight-based:** each save contributes "pending weight" based on type/importance, fire at threshold
- **Hybrid:** count OR time, whichever first (LangMem's choice)

Don't pick one until we have real data from ADR-004 about which signal is actually predictive of "this is a good time to consolidate."

### What does "scoped to touched entities" mean?

v1 draft said "reflection pass scoped to touched entities." Concretely:
- If 5 facts about `project/palinode` arrive in 15 minutes, the reflection pass only looks at `projects/palinode.md` and `projects/palinode-status.md`?
- Or does it also pull in related entities via graph walk?
- How do we compute the scope without scanning the whole store?
- Does the scope include facts that share vector similarity even if they don't share an entity ref?

### Where does the pending-state live?

Options:
- **In-process queue** (in the API server, like ADR-004's write-time queue)
- **SQLite table** (survives restarts, queryable for dashboards)
- **File-based markers** (matches ADR-004's CLI/plugin path, disk-durable)

The answer probably depends on whether ADR-004's asyncio queue has been causing problems. If it has, ADR-005 might need a more durable store.

### What happens to the nightly cron?

This is the decision that belongs in ADR-005, not ADR-004. Options:
- **Remove nightly cron entirely when tier 2b ships** — cleanest, but loses a fallback for very idle systems
- **Keep nightly cron as "catch-up" for entities that didn't cross the debounce threshold** — hybrid, might be redundant
- **Re-scope nightly to "sanity check only"** — fire once a day, emit a warning if any entity has unconsolidated facts older than 24h, don't actually do the LLM work

My current lean (not a decision): remove entirely. If an entity doesn't hit the debounce threshold in a day, it probably doesn't need consolidation. But wait for real data.

### What happens to the weekly cron?

This is also an ADR-005 decision, not ADR-004. Options:
- **Keep weekly as "global view" safety net** for MERGE and ARCHIVE operations that need the full corpus
- **Remove weekly entirely** — if tier 2b fires on all touched entities, weekly is redundant
- **Re-scope weekly to "storage maintenance only"** — archive old daily notes, compact SQLite, run the linter, but don't do any LLM-driven consolidation

The weakness of v1's "keep weekly as safety net" was that I couldn't justify it on concrete grounds. Before ADR-005 ships, I need a concrete answer to "what specific operation does weekly do that tier 2b can't?"

### Failure modes to cover

- Queue daemon dies — how do pending reflections resume?
- LLM down for an extended period — what's the backlog policy?
- Debounce trigger fires during an already-running reflection pass — does it queue or drop?
- Entity gets N contradicting facts in 30 seconds — does debounce wait or fire immediately?
- Two separate reflection passes touch the same file — lock? serialize? last-write-wins?

### What observability do we need?

- Queue depth metric
- Reflection pass latency metric
- Op-counts per pass (how much work is each firing actually doing?)
- LLM call count + token count per day
- Contradiction-catch rate (how often does a reflection pass actually find something to UPDATE/SUPERSEDE?)

If the catch rate is low (most passes return NOOP), the whole tier is overengineered and we should stop.

## Draft scope when written

Single decision: whether and how to coalesce write-time contradiction checks into debounced reflection passes. Includes the concrete decisions about nightly and weekly cron fate because those are downstream of this one.

Explicitly out of scope: on-read reconsolidation (ADR-006), access metadata schema (ADR-007).

## Revisit trigger

Draft this ADR when any of the following is true:
- ADR-004 has been in production ≥ 2 weeks AND write-time check latency p95 > 3s
- OR ADR-004's queue has backed up past 500 pending jobs at any point
- OR LLM call cost from ADR-004 exceeds acceptable budget
- OR contradiction-catch rate from ADR-004 is high enough that coalescing would meaningfully reduce LLM calls

Otherwise: leave as planned, don't force it.
