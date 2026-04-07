# ADR-002: Fault Isolation in the Indexing Layer

**Status:** Accepted
**Date:** 2026-04-06
**Deciders:** Paul Kyle

## Decision

Palinode's indexing layer treats every file event as an independent unit of work. A failure to index one file must never prevent indexing of subsequent files. Database write operations against SQLite virtual tables (`vec0`, `fts5`) use explicit delete-then-insert rather than relying on conflict-resolution clauses.

## Motivation

Palinode's value proposition depends on a simple invariant: **if a file exists in `PALINODE_DIR`, it is searchable.** The file watcher daemon is the component responsible for maintaining this invariant. It runs unattended, often as a systemd service, processing file events indefinitely.

Daemons that process streams of independent events have a well-known fragility: if one event raises an unhandled exception, the processing thread dies while the main process stays alive. The system appears healthy — the PID exists, the port responds, the service status is green — but no new work is being done. This is the worst class of failure because it is **silent and persistent**.

The indexing layer must therefore be designed around two principles:

1. **Event isolation** — each file event is processed in its own error boundary
2. **Defensive writes** — database operations use patterns that work reliably across all SQLite table types, including virtual tables with non-standard semantics

## Design

### Event isolation

Every watchdog event handler wraps its processing in a catch-all that logs and continues:

```
on_modified / on_created → try _process_file() except log + continue
on_deleted              → try delete_chunks() except log + continue
```

A failed file is skipped. It will be retried automatically on the next modification, or manually via `palinode ingest`. The invariant is temporarily broken for that one file but holds for everything else.

### Defensive virtual table writes

SQLite virtual tables implement their own storage engines via `xUpdate`. The SQLite documentation notes that virtual tables "may or may not" support conflict resolution in INSERT statements. In practice:

- **`vec0`** (sqlite-vec) does not reliably handle `INSERT OR REPLACE` — it can raise a UNIQUE constraint error on an existing primary key instead of replacing the row
- **`fts5`** has similar limitations with external-content tables

The safe pattern for any virtual table upsert:

```sql
DELETE FROM virtual_table WHERE id = ?;   -- no-op if absent
INSERT INTO virtual_table (id, ...) VALUES (?, ...);
```

This is two statements instead of one. The cost is negligible — embedding generation dominates the write path by orders of magnitude.

### Extensibility

These patterns apply to any new index type added to Palinode. If a future version adds a graph index, a keyword index, or a secondary vector store, the same rules hold:

- Wrap writes in the event handler's error boundary (already provided by the catch-all)
- Use delete-then-insert for any virtual table or extension-managed storage
- Use `INSERT OR REPLACE` only for regular SQLite tables where it is guaranteed

No per-index error handling is needed in calling code — the event boundary catches everything.

## Trade-offs

| | Benefit | Cost |
|---|---|---|
| **Event isolation** | One bad file never stalls the daemon | A persistently failing file logs on every modification until root-caused |
| **Delete-then-insert** | Works on all table types, past and future | One extra statement per write (negligible) |
| **Catch-all in handlers** | Maximum availability | Broad exception handling can mask programming errors in development |

The catch-all is acceptable because the watcher is a **production daemon**, not application logic. Availability takes priority over fail-fast. Errors are always logged with the file path and exception, so they remain debuggable.

## Consequences

- The indexing layer is resilient by default — new indexes inherit fault isolation without additional code
- Watcher logs contain structured error lines for any failed file, enabling monitoring and alerting
- The `chunks`, `chunks_fts`, and `chunks_vec` write paths are now consistent in their error-handling strategy
- No schema changes or migrations required

## References

- [SQLite Virtual Table Interface — xUpdate](https://www.sqlite.org/vtab.html#xupdate)
- [sqlite-vec](https://github.com/asg017/sqlite-vec) — the `vec0` virtual table extension
- [watchdog](https://github.com/gorakhargosh/watchdog) — filesystem event library
