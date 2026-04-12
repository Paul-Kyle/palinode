# ADR-004: Write-Time Contradiction Check on `palinode_save`

**Status:** Accepted (2026-04-10)
**Date:** 2026-04-10
**Supersedes:** None (first ADR to touch the save hot path)
**Related:** Consolidation improvements

## Context

Palinode has a function `_check_contradictions` in `palinode/consolidation/runner.py` that compares a candidate memory item against the top-k most similar existing memories and asks an LLM to emit one of ADD / UPDATE / DELETE / NOOP. It exists today and is unit-tested. It is **not** currently wired into the `palinode_save` code path — it is only called from the scheduled consolidation runner.

This ADR decides whether and how to wire `_check_contradictions` into `palinode_save`.

### What motivates this

A literature review of AI memory systems in production (mem0, Zep, LangMem, A-Mem, Letta/MemGPT) found that every post-2024 system performs some form of contradiction check or dedup at write time rather than only in scheduled batches. mem0 in particular runs ADD/UPDATE/DELETE/NOOP synchronously on every `add()` call against the top-s similar existing memories — structurally identical to what `_check_contradictions` already does. The full review is in `artifacts/consolidation-redesign-2026-04-10.md`.

Palinode already has the primitive. It is not being called from the save path. That is the gap this ADR closes.

### What this ADR is NOT about

This ADR does **not** decide:

- Whether to replace the scheduled batch consolidation (nightly / weekly crons). Those stay.
- Whether to build a debounced reflection executor. Future ADR.
- Whether to build on-read reconsolidation. Future ADR, if ever.
- Access metadata schema (last-retrieved-at, retrieval count). Future ADR.
- Enabling `DecayConfig`. Future ADR.
- Weekly cron fate. Out of scope.

The temptation to bundle all of these into one decision is what killed ADR-004-v1. This ADR is scoped to one change on one code path.

## Decision

Wire `_check_contradictions` into the `palinode_save` path. Run it **asynchronously** by default — the save returns as soon as the file is written and git-committed, and a background task runs the contradiction check and applies any resulting deterministic executor operations.

### Why async default, not sync

1. **Save-never-fails is a load-bearing invariant.** Palinode's pitch is "markdown files as source of truth; survives everything." If the LLM is down, a synchronous contradiction check would turn every save into a failure. Async keeps saves landing even when the LLM is unreachable — the dedup pass is delayed, not lost.

2. **The session-end hook cannot block on an LLM.** The Claude Code session-end hook at `~/.claude/hooks/palinode-session-end.sh` has a 10-second timeout budget and is supposed to be non-blocking on exit. Adding 1-2s of synchronous LLM latency to every `palinode_save` on that path risks dropped sessions when the hook fires at the tail end of a long conversation.

3. **Matches mem0's architecture.** mem0 is the closest analog in the SOTA survey and also uses a background pipeline for reconciliation — not a fully synchronous hot-path LLM call.

### Sync opt-in

The CLI and API expose an opt-in sync mode for scripted workflows that want to wait for the contradiction-check result before continuing:

```bash
palinode save "fact text" --type Decision --sync
```

```http
POST /save?sync=true
```

When `--sync` is set, the request blocks on the contradiction check and returns the resulting operations in the response. Default behavior (no flag) is fire-and-forget with a queue handoff.

### Implementation

#### File layout

**New file:** `palinode/consolidation/write_time.py` — all tier 2a logic lives here. Isolated from `runner.py` so it can be feature-flagged and rolled back by touching one module.

**Modified files:**
- `palinode/api/server.py` — `save_api` gains a `sync` query param; API lifespan starts and stops the background worker
- `palinode/cli/save.py` + `palinode/cli/_api.py` — CLI gains `--sync` flag; API client forwards it as a query param
- `palinode/mcp.py` — `palinode_save` handler passes through (async only; no sync option at the MCP layer)
- `palinode/core/config.py` — new `WriteTimeConfig` dataclass on `ConsolidationConfig`
- `palinode.config.yaml.example` — new `consolidation.write_time` section

**No changes to:** `palinode/consolidation/executor.py` (unchanged — this is the ADR-001 invariant), `palinode/consolidation/runner.py::_check_contradictions` (reused as-is), `palinode/core/store.py`, `palinode/core/embedder.py`.

#### Module API: `palinode/consolidation/write_time.py`

```python
# Public entry point — called from save paths
def schedule_contradiction_check(
    file_path: str,       # absolute path to the just-saved memory file
    item: dict,           # {"content": ..., "category": ..., "type": ..., ...}
    *,
    sync: bool = False,   # True = run inline and return ops; False = enqueue
) -> dict | None:
    """If sync, runs the check and returns {"operations": [...], "applied": int}.
    If async (default), enqueues a job and returns None immediately."""

# Internal: does the actual work
def _run_check_and_apply(file_path: str, item: dict) -> dict:
    """Calls _check_contradictions, applies resulting ops via the executor,
    git-commits with 'palinode: write-time dedup'. Returns stats."""

# In-process queue (used when the API server is the save entry point)
class _PendingCheckQueue:
    """Async queue with bounded size. Workers pop one at a time."""

# Disk-backed marker files (used by CLI and plugin paths without a worker)
def _write_marker(file_path: str, item: dict) -> str:
    """Writes .palinode/pending/{timestamp}-{uuid}.json. Returns marker path."""

def sweep_pending_markers() -> int:
    """Called on API startup. Scans .palinode/pending/ and re-enqueues each
    marker file as a job. Returns number of markers recovered."""

# Async worker started in API lifespan
async def _worker_loop(queue: _PendingCheckQueue) -> None:
    """Pops jobs, runs _run_check_and_apply, logs results, swallows errors."""
```

#### Queue mechanics

- **In-process asyncio queue** (`asyncio.Queue`), bounded at `write_time.queue_max_size` (default 1000). When the queue is full, new jobs fall through to disk-backed marker files instead of blocking the caller. Never blocks a save.
- **Disk-backed markers** at `{PALINODE_DIR}/.palinode/pending/{utc_iso}-{uuid}.json`. Each marker is a single JSON object: `{"file_path": ..., "item": ..., "enqueued_at": ...}`. Atomic write (write to `.tmp` then rename).
- **Sweeper** runs once on API startup, sorted by enqueued timestamp (oldest first). Each successfully processed marker is deleted. Failed markers are renamed to `.failed.json` for operator review (not retried indefinitely — fail loud, don't retry silently forever).
- **Worker** runs one job at a time (no parallelism). The rationale: `_check_contradictions` holds embedder + LLM + sqlite handles; keeping it serial avoids contention with the main save path and the nightly consolidation runner.

#### Wiring into save paths

**1. API `POST /save` (`palinode/api/server.py`):**
```python
@app.post("/save")
def save_api(req: SaveRequest, sync: bool = False) -> dict[str, Any]:
    # ... existing save logic, unchanged through line 468 ...
    result = {"file_path": file_path, "id": frontmatter_dict["id"]}

    # NEW: tier 2a hook
    if config.consolidation.write_time.enabled:
        item = {
            "content": req.content,
            "category": category,
            "type": req.type,
            "entities": req.entities or [],
        }
        check_result = write_time.schedule_contradiction_check(
            file_path, item, sync=sync
        )
        if sync and check_result:
            result["write_time_check"] = check_result
    return result
```

**2. CLI `palinode save --sync` (`palinode/cli/save.py` + `_api.py`):**
- `save.py` gains `@click.option("--sync/--no-sync", default=False, ...)` and passes it through
- `_api.py::save()` gains `sync: bool = False` param and forwards as `?sync=true` query

**3. MCP `palinode_save` (`palinode/mcp.py`):**
- No schema change to the tool — it remains fire-and-forget. The MCP handler at line 544-564 stays identical. Async-only at the MCP layer because a blocking MCP call while the LLM is slow would wedge the Claude Code client, which is exactly the problem async is solving.

**4. Plugin path:** plugin saves go through the REST API, so wiring is automatic via change #1.

#### Config surface

**`palinode/core/config.py`:**
```python
@dataclass
class WriteTimeConfig:
    """Tier 2a: write-time contradiction check on palinode_save."""
    enabled: bool = False  # Rollout: False by default, flip after validation
    queue_max_size: int = 1000
    check_timeout_seconds: int = 30
    pending_dir: str = ".palinode/pending"
    sweep_on_startup: bool = True
```

**`palinode.config.yaml.example`:**
```yaml
consolidation:
  # ... existing fields ...
  write_time:
    enabled: false          # tier 2a — off by default during rollout
    queue_max_size: 1000
    check_timeout_seconds: 30
    pending_dir: ".palinode/pending"
    sweep_on_startup: true
```

The feature flag (`enabled: false` by default) is the rollback lever. Flipping one value returns the system to pre-ADR behavior. No code rollback needed.

#### Worker lifecycle (API server)

Start/stop in `api/server.py` lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing startup ...
    if config.consolidation.write_time.enabled:
        from palinode.consolidation import write_time
        recovered = write_time.sweep_pending_markers()
        if recovered:
            logger.info(f"write-time: recovered {recovered} pending markers")
        app.state.write_time_task = asyncio.create_task(
            write_time._worker_loop(write_time._queue)
        )
    yield
    # ... existing shutdown ...
    if hasattr(app.state, "write_time_task"):
        app.state.write_time_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await app.state.write_time_task
```

If `enabled` is false, no worker starts and `schedule_contradiction_check` is never called. Zero overhead.

#### Git commit semantics

When the worker applies ops from a contradiction check, it creates **a separate commit** with message `palinode: write-time dedup: {category}/{slug}` after the original save commit. This keeps the history clean: you can blame a memory line back to either the user save or the dedup pass that refined it.

If the check returns NOOP (no contradiction found), no commit is created. Most checks will likely be NOOP; silent success is correct.

#### Observability

- **Structured logs** on every check: `write-time: file=... result=NOOP/UPDATE/SUPERSEDE latency_ms=... model=...`
- **Queue depth** exposed via existing `/status` endpoint as new field `write_time_queue_depth`
- **Pending marker count** in `/status` as `write_time_pending_markers`
- **Failure counter** in `/status` as `write_time_failures_24h` (rolling count)
- **New log prefix:** all tier 2a log lines start with `write-time:` for easy grep/filter

#### Test plan

**Unit tests** (no real LLM, all mocked) — `tests/test_write_time.py`:
- `test_queue_enqueue_and_pop` — basic queue mechanics
- `test_queue_full_falls_to_marker` — when queue is full, item lands on disk
- `test_marker_write_atomic` — marker files never appear half-written
- `test_sweep_recovers_markers` — sweeper finds and re-enqueues all markers
- `test_sweep_deletes_processed_markers` — successful markers are cleaned up
- `test_sweep_renames_failed_markers_to_failed_json` — failed markers preserved for review
- `test_schedule_sync_returns_ops_inline` — sync path calls the function and returns
- `test_schedule_async_returns_none` — async path returns immediately
- `test_feature_flag_disabled_no_worker` — with `enabled=false`, scheduler is a no-op

**Integration tests** (real store, mocked LLM) — `tests/test_write_time_integration.py`:
- `test_sync_path_end_to_end` — save with `sync=true`, verify ops in response
- `test_async_path_eventual_consistency` — save async, sleep briefly, verify file was deduped
- `test_llm_failure_save_still_succeeds` — mock LLM raises, verify save returns 200
- `test_api_startup_sweeps_markers` — pre-create markers, start API, verify they're drained
- `test_concurrent_saves_serialized_on_worker` — 10 saves in a loop, worker processes serially

**Manual acceptance test** (live LLM on dev instance):
- Save a fact that contradicts an existing memory file with `--sync`
- Verify the response contains the UPDATE op
- Save the same fact async, wait 30s, verify the git log has both the save commit and a dedup commit
- Disable the LLM endpoint, save a fact, verify save succeeds and a marker file appears in `.palinode/pending/`
- Re-enable LLM, restart API, verify the sweeper processes the pending marker

#### Rollout plan

1. **Ship with `enabled: false`.** Merges the code without changing behavior. Allows testing in CI.
2. **Enable on dev instance only** by setting `consolidation.write_time.enabled: true` in its yaml. Run for 48h with live load. Monitor queue depth, LLM failure rate, dedup-catch rate.
3. **If metrics look fine, update the example config default** to `enabled: true`. Document the change in CHANGELOG as the feature becoming default in the next version.
4. **If metrics look bad** (queue backing up, LLM errors, incorrect ops applied): flip the yaml back to `false`, investigate, iterate.

#### Rollback procedure

Three levels of escalation:

1. **Runtime disable:** edit `palinode.config.yaml`, set `consolidation.write_time.enabled: false`, restart API. Reverts behavior without code changes. Pending markers on disk are left in place (harmless; they'll be picked up when re-enabled).
2. **Code flag at build time:** if the config check itself is broken, add `WRITE_TIME_FORCE_DISABLE = True` as a module constant in `write_time.py`. Hard no-op regardless of config.
3. **Git revert** of the tier 2a commit series. Everything in this ADR lives in new code paths behind a feature flag, so revert is a clean `git revert` of the feature-flag-off commits.

#### Failure handling (expanded from §"Failure modes")

Errors from `_check_contradictions`, the executor, git, or the LLM are caught inside `_worker_loop` and logged at `ERROR` level with the offending marker path. The worker never dies on a single job failure — it logs, moves on, picks up the next job. If the worker task itself crashes (unhandled exception, OOM), the API lifespan catches the cancellation and the next API restart triggers a sweep that recovers any in-memory jobs that were lost (via disk-backed markers if the queue-full fallback had kicked in).

**Save-path errors never propagate.** The save call path has a `try/except` around `schedule_contradiction_check` that logs and continues. If the scheduler itself raises (disk full writing a marker, queue module bug), the save still returns success.

### What this changes for the executor

Nothing. The deterministic executor (`palinode/consolidation/executor.py`) is the same code, applied to the same ops, in the same way. This ADR only changes **who calls it and when** — not how ops are applied. The [ADR-001](ADR-001-tools-over-pipeline.md) invariant (LLM proposes, Python applies) is preserved.

## Failure modes and their responses

| Scenario | Response |
|---|---|
| LLM endpoint down | Check is skipped with a warning log. Save still lands. Queued job is retried on next sweep. |
| LLM returns malformed JSON | `json_repair` already wraps parsing. If repair fails, check is skipped with error log. Save still lands. |
| Check finds a contradiction and wants to UPDATE | Background worker applies UPDATE via executor. New git commit with `palinode: write-time dedup`. Caller never sees the op. |
| Check times out (> 30s) | Job is killed, marker file stays in pending queue, retried by sweeper. Save still lands. |
| Background queue backed up (> 100 pending) | New jobs still enqueue, but a warning log fires. If > 1000 pending, API starts returning a soft warning in save responses ("dedup queue depth: N") without blocking. |
| Save loop: 50 files saved in 1 second | 50 jobs enqueued, worker processes them sequentially. Saves complete in ~1s (synchronous write + git). Dedup catches up over the next ~60-100s. |
| Process dies between save and dedup | Marker files on disk mean jobs persist across restarts. Sweeper picks up the queue on next API startup. |
| The `_check_contradictions` function itself has a bug | Bug affects only dedup quality, not save correctness. Can be rolled back by feature-flagging the call site. |

## Consequences

### Positive
- Contradictions surface minutes after they're written instead of 24 hours later at the nightly pass
- Uses a primitive that already exists and is tested
- Save latency unchanged (async)
- Failure modes are all soft — saves keep landing even when the LLM is down
- Reversible: if the contradiction check produces bad results, feature-flag the call site off and the system returns to pre-ADR behavior

### Negative
- New eventual-consistency window between save and consolidated state (seconds to tens of seconds normally; longer when LLM is down)
- More moving parts: an asyncio queue in the API, marker files for CLI/plugin paths, a sweeper on startup
- `_check_contradictions` has only been exercised by the nightly runner until now; wiring it into the save path will find latent bugs
- Scripted workflows that want "save, then immediately search and expect the new consolidated state" need to pass `--sync` or poll

### Neutral
- Existing nightly and weekly crons keep running exactly as they do today. Nothing is removed by this ADR.
- The background worker adds a dependency on the API server being up. CLI and plugin paths handle this via disk-backed marker files, so they work offline.

## Implementation order

1. Add `schedule_contradiction_check` and the asyncio queue/worker infrastructure. Unit-test the queue and sweeper in isolation (no real LLM).
2. Wire the `--sync` path first, because it's testable end-to-end with a small integration test. This validates that `_check_contradictions` actually works when called from a save code path before introducing async complexity.
3. Flip the default to async. Monitor queue depth and error rates for a week of real use.
4. If queue depth or error rate is unacceptable, feature-flag the call site off and investigate.

Each step is a separate commit and can be rolled back independently.

## Alternatives considered

- **Sync on hot path (ADR-004-v1's original proposal).** Rejected for the reasons in "Why async default" above. The session-end hook alone kills this option.
- **Don't wire it at all; keep using the scheduled batch.** Rejected because the contradiction function already exists, is tested, and the nightly pass is 24h later than the contradiction actually exists in the file. Latency is the main motivation.
- **Wire it into the save path but only when a flag is set in `palinode.config.yaml`.** Rejected as a half-measure. A feature you have to opt into is a feature nobody uses. If we're going to wire it, it should be the default with an opt-out, not the reverse. An opt-out is easy to add later if real-world use surfaces a reason.

## Open questions (explicit, deferred, or delegated to implementation)

**Deferred to implementation, with initial guesses:**
- Queue implementation: in-process asyncio queue for the API, disk-backed marker files for CLI/plugin. May need to converge on one mechanism if operational experience shows the split is confusing.
- Timeout on the background check: 30s initial. Tunable via config.
- Retry count: 3 initial. Tunable via config.

**Explicitly out of scope for this ADR:**
- Debounced reflection executor (tier 2b)
- On-read reconsolidation (tier 4)
- Access metadata schema
- Enabling `DecayConfig`
- Weekly cron fate

## Future work mentioned but not decided

A follow-up ADR may propose a debounced reflection executor that coalesces multiple write-time checks into a single LLM call, if write-time check latency or LLM call volume becomes a problem in practice. The research also identified on-read reconsolidation as a theoretically interesting tier (biological analog: Nader et al. 2000) but the implementation specifics are too vague to commit to a design.

## References

- Full literature review and benchmark data: `artifacts/consolidation-redesign-2026-04-10.md`
- Existing function: `palinode/consolidation/runner.py::_check_contradictions`
- Deterministic executor invariant: [ADR-001](ADR-001-tools-over-pipeline.md)
- Related to consolidation improvements
