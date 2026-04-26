# Validation strategy for cross-session features

When a feature crosses a Palinode session boundary — `/wrap`, the SessionEnd hook, `palinode_session_end`, the `/ps` slash command, future cross-harness capture — four distinct things can fail independently. A green check at one layer doesn't imply the others. Don't declare a cross-session feature "works" until you have evidence at all four.

## The four layers

| # | Layer | The assertion | How to check |
|---|---|---|---|
| **L1** | **Tool fired** | The save actually ran. Hook didn't crash, CLI didn't error, API didn't 500. | `git -C $PALINODE_DIR log --oneline -5` (expect a `session-end:` or `save:` commit). `journalctl --user -u palinode-api` for API access logs. Hook script exit code. |
| **L2** | **Data on disk** | The write path succeeded. Daily note has today's entry, project status file has a new line, frontmatter is well-formed YAML, content is what was intended. | `palinode list --category daily`. `cat $PALINODE_DIR/daily/$(date -I).md`. `palinode list --category projects`. `head -25 $PALINODE_DIR/projects/<slug>-status.md`. |
| **L3** | **Retrievable** | The indexer caught up. Semantic search surfaces the new record with a meaningful score, `palinode diff --days 1` shows it, `palinode list` includes it. | `palinode search "<known keyword from the entry>"`. `palinode diff --days 1`. Watch the server log for "indexed N chunks". |
| **L4** | **Behavioral** | A fresh agent session actually uses the record. The agent searches on session start (per its CLAUDE.md instructions), finds the record, and references it in a response. | Run the agent with a blank context. Ask "what was I working on?" or a question that should hit the record. Inspect the agent's tool calls to confirm `palinode_search` fired and the result was used in the answer. |

## Why four and not three

L1–L3 are necessary but not sufficient. You can have a perfectly indexed, perfectly searchable record that no agent ever surfaces because:

- The CLAUDE.md session-start instructions are too vague ("call `palinode_search` when relevant" leaves the trigger to the model's judgment)
- The agent prioritizes its general knowledge over a `palinode_search` call
- The search query the agent forms doesn't match the record's content (compositional terms, synonyms, capitalization)
- The context-prime path is off (ADR-009 misconfigured, no project entity boost)

L4 is the only test that catches these. It's also the hardest to automate — it requires an LLM in the loop. See [#42](https://github.com/phasespace-labs/palinode/issues/42) for the automated-L4 path.

## What each layer protects against

- **L1 alone is not enough.** The CLI can return success while writing to a broken path. The hook can exit 0 while the embedded `curl` call timed out (the script is fail-silent by design — see `examples/hooks/palinode-session-end.sh`).
- **L1+L2 alone is not enough.** The file can land on disk but the watcher / embedder can drop it. Common when the embedder is slow and the next search runs before indexing completes. Or when `last_indexed` is stale because the watcher process died and was never restarted.
- **L1+L2+L3 alone is not enough.** The record can be retrievable by search but invisible to a fresh agent session that isn't instructed to search, or whose context-prime path doesn't fire. The most expensive bug to catch — silent, intermittent, hard to grep for.
- **L1+L2+L3+L4 is the minimum bar** for declaring a cross-session feature works.

## When to apply

Every PR that touches:

- `palinode_session_end`, `palinode_save`, or any session hook (`examples/hooks/`, `palinode/cli/init.py` `HOOK_SCRIPT`)
- Slash command prompts (`.claude/commands/*.md`, the `PS_COMMAND_BODY` / `WRAP_COMMAND_BODY` constants in `init.py`)
- CLAUDE.md template content (`CLAUDE_MD_BLOCK`)
- The consolidation executor — because it can delete or retract records that should have remained retrievable

…should include evidence at all four layers in the PR description, even if some layers are recorded as "verified manually" rather than via an automated test. The PR's test plan should name the exact commands that produced the evidence.

## Concrete checklist

Copy into a PR description and tick as you go:

```markdown
### Validation evidence

- [ ] L1 — Tool fired
  - Output: `<paste>`
- [ ] L2 — Data on disk (path + first 10 lines of file content)
  - Path: `<paste>`
  - Content head: `<paste>`
- [ ] L3 — Retrievable
  - `palinode search "<query>"` returned the new record at rank N with score X
- [ ] L4 — Behavioral
  - Fresh agent session, prompt: "<paste>"
  - Agent's tool calls included `palinode_search` with query "<paste>"
  - Agent's response referenced the record content
```

Skipping a layer is a yellow flag. Skipping L4 because "it's hard to automate" is the most common mistake — manual L4 verification still counts; absence of L4 doesn't.

## Existing automation

| Layer | Status | Where |
|---|---|---|
| L1 | Covered | `tests/test_session_end.py`, `tests/test_cli_init.py`, and the L1 case in `tests/integration/test_session_end_e2e_l1_l3.py` |
| L2 | Covered | Same suites — frontmatter shape, file existence, daily-note + project-status content |
| L3 | Covered | `tests/integration/test_session_end_e2e_l1_l3.py` — fresh `TestClient` issues `POST /search` against the on-disk SQLite DB written by the CLI's dual-write |
| L4 | **Gap** — see [`docs/L4-BEHAVIORAL-TESTING-DESIGN.md`](./L4-BEHAVIORAL-TESTING-DESIGN.md) and [#42](https://github.com/phasespace-labs/palinode/issues/42) | Automated LLM-in-the-loop test design is sketched but not yet implemented |

Until L4 lands, L4 is manual on every cross-session-feature PR. Document the manual evidence in the PR; don't assume future you will remember what you ran.

## Related

- [#41](https://github.com/phasespace-labs/palinode/issues/41) — automated integration test for L1–L3 of `/wrap` → `/clear` → recall
- [#42](https://github.com/phasespace-labs/palinode/issues/42) — automated L4 (LLM-in-the-loop)
- [#40](https://github.com/phasespace-labs/palinode/issues/40) — why the prompts this strategy validates have to be deterministic (every layer assumes the slash command does the same thing every time)
