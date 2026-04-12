# ADR-006: On-Read Reconsolidation (Tier 4)

**Status:** Speculative — not yet drafted, may never be
**Depends on:** ADR-004 shipped; ADR-007 (access metadata) shipped
**Related:** Consolidation improvements

## What this ADR would decide

Whether to trigger a targeted consolidation pass on a specific memory file when that file is retrieved and then followed within some window by a save that contradicts or extends the retrieved content.

Biological analog: reconsolidation (Nader, Schafe & LeDoux 2000) — a retrieved memory becomes labile and requires re-stabilization when prediction error or novel information is present.

## Why this ADR is marked speculative

When I first wrote about this tier in ADR-004-v1, I was seduced by the biological analogy and underestimated how vague the implementation specifics are. Cold-eye review: every piece of "when a retrieved memory is followed within N minutes by a contradicting save, trigger a re-stabilization pass" is its own decision I haven't made.

This ADR may never be written. It's here so we don't lose the idea, not because we're committed to building it.

## Prerequisites before drafting

- [ ] ADR-004 (tier 2a) shipped and validated
- [ ] ADR-007 (access metadata) shipped — we need to know which files have been recently retrieved before we can trigger anything on retrieval
- [ ] Real data on the typical "read-then-save" pattern — how often does it happen? what's the typical gap?
- [ ] Real data on how often write-time dedup from ADR-004 *already* catches the contradictions this tier would catch (if write-time dedup catches them all, this tier is redundant)

## Questions to think through when writing

### Is this distinguishable from tier 2a in practice?

The biggest threat to ADR-006 being useful: **maybe write-time dedup from ADR-004 already does the work.** When you save a fact, `_check_contradictions` looks at the top-k similar existing memories. If the memory you just retrieved is semantically close to the memory you're saving, it'll show up in the top-k regardless of whether you retrieved it. So the contradiction gets caught at write time anyway.

The scenario where tier 4 adds value: you retrieved a memory, and the memory you're about to save is semantically *different* from the retrieved one but contradicts it anyway. Is this even a real scenario? Example:
- You retrieve `decisions/api-rest-vs-graphql.md` (about REST)
- You save `insights/graphql-subscriptions-are-actually-fine.md` (not semantically identical, but contradicts the earlier decision)
- Vector similarity might not surface the REST decision in top-k for the new GraphQL insight
- But the chronological read-then-save pattern would

Before drafting ADR-006, check whether this scenario actually happens in real usage data, or whether it's a theoretical concern.

### What counts as a "read"?

Options:
- MCP tool calls (`palinode_read`, `palinode_search`)
- API `GET /files/{path}` calls
- CLI `palinode read` / `palinode search`
- Automatic context injection (core memory, top-k search results)
- File watcher detecting a manual `cat` or editor open

Each of these is a different signal strength. Automatic injection is much noisier than an explicit tool call — every turn injects core memory, and we probably don't want every subsequent save to trigger a reconsolidation on every core file.

### What counts as "contradicts or extends"?

This is an LLM judgment call. Options:
- Re-run `_check_contradictions` but with the retrieved file forced into the top-k regardless of similarity
- Add a separate LLM call that asks "does the new save contradict the retrieved file specifically?"
- Heuristic: if the new save mentions any entity or keyword from the retrieved file, treat it as potentially contradicting

Each option adds LLM calls. Measure the cost before committing.

### What's the window?

- Minutes (N=5, N=15, N=60)?
- Turns (next N agent turns after the read)?
- Session (same Claude Code session)?
- No window (any save while the read is in "recently retrieved" metadata triggers)?

### Does this compose with tier 2a?

If a read triggers a write-time contradiction check against the retrieved file, and the save also triggers its own write-time contradiction check (ADR-004), does the system do two LLM calls or one? If two, that's wasteful. If one, which one takes precedence?

### What happens for pure-read sessions?

If a user reads 20 files and never saves anything, nothing triggers. No cost. But then what's the value of tracking access metadata at all? Access metadata has value beyond this tier (ranker boost, decay), but ADR-006 specifically doesn't need it unless there's a save.

### Failure modes

- Retrieved file is deleted between read and save
- Retrieved file is already being consolidated by tier 2b
- User retrieves 50 files, saves 1 — check all 50 or just some subset?
- LLM hallucinates a contradiction that doesn't exist → bad UPDATE gets applied

The last one is the scariest. Without a human in the loop, a confidently wrong LLM can corrupt memory. ADR-006 needs a safety mechanism (low-confidence flag? dry-run only? surface to human for approval?) before shipping.

## Draft scope when written

This ADR is narrow: does retrieval + subsequent save trigger a targeted consolidation pass, yes or no, and if yes, how.

Out of scope: access metadata schema (ADR-007, which is a prerequisite), ranker weighting of access metadata (ADR-007), decay based on retrieval count (ADR-007).

## Revisit trigger

Draft this ADR only if **all** of the following are true:
- ADR-004 and ADR-007 are shipped
- Real-world data shows that the "read-then-contradicting-save" pattern happens often enough to matter
- Real-world data shows that write-time dedup (tier 2a) *isn't* already catching those contradictions
- We've designed a safety mechanism against LLM-hallucinated contradictions

If any of these is missing, leave this ADR as speculative and don't write it.

## Possible outcome

It is likely that this ADR gets closed as "not needed" after ADR-004 ships and we see that tier 2a already catches the contradictions that motivated this design. That's a fine outcome. Mark it "not needed" and move on.
