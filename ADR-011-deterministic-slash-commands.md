# ADR-011: Deterministic Slash Commands

**Status:** Accepted
**Date:** 2026-04-28
**Context:** Issue #138 — formalizes de-facto practice already observed in `.claude/commands/`
**Relates to:** ADR-001 (Tools Over Pipeline)

## Decision

User-facing slash commands MUST map to a **single, named tool** with a **fixed argument shape**. The LLM is allowed to synthesize the *content* of arguments but must not choose the *tool*, decide whether to invoke a tool at all, or vary the type/shape of arguments based on context.

| Allowed | Not allowed |
|---|---|
| Agent writes the `summary` text for `palinode_session_end` | Agent decides whether to call `palinode_session_end` or `palinode_save` |
| Agent picks which facts to list as `decisions` | Agent decides whether to save at all |
| Agent writes the body of a `ProjectSnapshot` | Agent picks between `ProjectSnapshot` and `Decision` type |
| Agent fills in `project` from the current CLAUDE.md | Agent skips saving because "nothing important happened" |

## Context

Palinode provides slash commands as shortcut entry points for common memory operations. As of 2026-04-28 the canonical commands are:

| Command | File | Tool | Fixed argument shape |
|---|---|---|---|
| `/wrap` | `.claude/commands/wrap.md` | `palinode_session_end` | `summary`, `decisions`, `blockers`, `project` |
| `/save` | `.claude/commands/save.md` | `palinode_save` | `type=ProjectSnapshot`, `content`, `project` |
| `/ps` | `.claude/commands/ps.md` | `palinode_save` (back-compat alias for `/save`) | same as `/save` |

Each command file ends with an explicit "**This command is deterministic.**" statement naming the single tool it calls and what it does *not* do.

The pattern emerged organically. This ADR formalizes it as a load-bearing constraint rather than a style preference.

## Rationale

### 1. Trust via repetition

When a user types `/wrap`, they expect the same tool to fire every time — unconditionally. Smart-dispatch (letting the LLM decide whether to use `palinode_session_end` or `palinode_save`, or whether to skip saving entirely because the session looked short) breaks user mental models. The value of `/wrap` is precisely that the user does not have to think; they just type it and know what happened.

Predictability is the contract. An agent that fires the right tool 95% of the time provides weaker guarantees than one that fires *a specific tool* 100% of the time — even if the 5% of smart-dispatch choices would technically be "better."

### 2. ADR-001 alignment

ADR-001 established the principle: **LLM proposes content, deterministic Python disposes.** That principle governs the LLM→executor boundary (the LLM proposes KEEP/MERGE/ARCHIVE ops; the executor applies them deterministically without re-evaluating the proposals).

The same principle applies at the user→tool boundary. The LLM synthesizes the *content* of the tool call (what to write in `summary`, which facts to surface in `decisions`). It does not re-evaluate *which tool to call* or *whether to call one at all*. That decision was made by the user when they typed `/wrap`.

### 3. Provenance

Git blame on memory only works when tool selection is deterministic and visible in the commit trail. When `/wrap` always calls `palinode_session_end`, every session end produces a predictable commit pattern. When `/save` always writes a `ProjectSnapshot`, snapshots are auditable by type. Allowing the LLM to vary tool choice breaks the "what fired and why" trail that makes palinode memory trustworthy across sessions.

### 4. Failure surface

When something goes wrong, "I typed `/wrap` and it called the wrong tool" is an obvious, debuggable failure. "The LLM decided to call `palinode_save` instead of `palinode_session_end` because of context" is a silent divergence that is nearly impossible to diagnose post-hoc. The failure surface of deterministic dispatch is narrow and visible; the failure surface of smart-dispatch is wide and latent.

## Alternatives considered

### Smart-dispatch: let the LLM pick the best tool for context

Rejected. The benefit (theoretically better tool selection for unusual cases) is smaller than the cost (broken user mental models, unpredictable git trail, hard-to-debug failures). If the user wants `palinode_save` instead of `palinode_session_end`, they type `/save`. The slash commands are the user's dispatch mechanism; the LLM's job is content synthesis, not routing.

### Parameterized commands: one command, many modes

Rejected for the existing three commands. `/wrap` and `/save` are already separate because they serve different purposes (end-of-session structured capture vs. mid-session snapshot). Merging them into a single `/memory` command with a mode flag would require the LLM to choose the mode — which is exactly the smart-dispatch problem in disguise.

### No slash commands at all: always use tools directly

Deferred. Tools-first is the right long-term direction (ADR-001). But slash commands provide a UX shorthand that reduces friction for common workflows and are especially useful in non-coding contexts (Cursor, Obsidian, conversational sessions). The commands remain valid as long as they are deterministic wrappers.

## Consequences

### Requirements for new slash commands

Any new slash command added to `.claude/commands/` MUST:

1. Name exactly one tool in its command file.
2. Specify the fixed argument shape (which fields, what types/values).
3. End with a "**This command is deterministic.**" statement that names the single tool and explicitly contrasts with the command that does *not* apply (e.g., "For X, use `/other-command` instead").
4. Not contain any conditional logic, branching, or context-dependent tool selection.

### Compliance audit (as of 2026-04-28)

All three existing commands comply:

- `/wrap` (`.claude/commands/wrap.md`): always `palinode_session_end`. Explicitly states "Do not call any other tool."
- `/save` (`.claude/commands/save.md`): always `palinode_save` with `type=ProjectSnapshot`. Explicitly states "always `palinode_save`, always `ProjectSnapshot`."
- `/ps` (`.claude/commands/ps.md`): back-compat alias, identical behaviour to `/save`. Deprecated label included.

No violations found. The "This command is deterministic." footer in each file is the inline enforcement signal — any future command file missing it fails the review.

### Scope

This ADR governs user-facing slash commands (`.claude/commands/`). It does not govern:

- Internal agent-to-agent calls (those are governed by ADR-001 and ADR-010).
- The MCP tool implementations themselves (they may have internal branching).
- CLI commands, which are multi-dispatch by design and governed by ADR-010's parity contract.

## References

- ADR-001 (Tools Over Pipeline) — the source principle: LLM proposes content, deterministic Python disposes.
- ADR-010 (Cross-Surface Parity Contract) — the complementary discipline for CLI/MCP/API parity.
- `.claude/commands/wrap.md` — canonical example of a deterministic wrap command.
- `.claude/commands/save.md` — canonical example of a deterministic snapshot command.
- `.claude/commands/ps.md` — back-compat alias demonstrating that even deprecated commands carry the determinism guarantee.
- Issue #138 — the tracking issue that prompted this formalization.
