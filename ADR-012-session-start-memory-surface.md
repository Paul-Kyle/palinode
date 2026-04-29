# ADR-012: Session-Start Memory Surface Across Harnesses

**Status:** Proposed
**Date:** 2026-04-28
**Relates to:** ADR-008 (ambient context search), ADR-009 (scoped memory + context prime), ADR-011 (deterministic slash commands)
**Tracks:** #87, #107, #81 (superseded), this ADR's umbrella tracking issue

---

## 1. Problem

Palinode currently has **no active session-start mechanism in any harness**. Memory injection at session start is, in practice, a soft instruction — `CLAUDE.md` or a `SKILL.md` file telling the LLM to call `palinode_search` itself. Whether that happens depends on the agent reading the instruction and choosing to follow it.

The bigger problem is asymmetry. Different harnesses give palinode wildly different surface area to land on:

| Surface | MCP tools | CLAUDE.md / instruction file | Skill | SessionStart hook | SessionEnd hook | Slash commands |
|---|---|---|---|---|---|---|
| **Claude Code** | ✅ | ✅ (read by agent each session) | ✅ optional in `~/.claude/skills/` | ❌ not shipped | ✅ `palinode-session-end.sh` | ✅ `/save` `/wrap` `/ps` |
| **Claude Desktop** | ✅ | ❌ doesn't read CLAUDE.md | ❌ no skills system | ❌ | ❌ | ❌ |
| **Cursor** | ✅ via `.cursor/mcp.json` | ❌ | ✅ via `.cursor/skills/` | ❌ | ❌ | ❌ |
| **VS Code / JetBrains + Claude** | ✅ inherits from `~/.claude/` | ✅ | ✅ inherits | ❌ | ✅ inherits | ✅ inherits |
| **Codex CLI** | ✅ via `~/.codex/config.toml` | ❌ | ❌ no skills system | ❌ | ❌ | ❌ |
| **Gemini CLI / others** | ✅ if user wires it | ❌ | ❌ | ❌ | ❌ | ❌ |

The asymmetry matters because palinode's value depends on the agent *actually pulling memory* before answering. Claude Code is well-served (CLAUDE.md persistently instructs the agent + skills + slash commands). Claude Desktop, Codex CLI, and Gemini CLI have **only the MCP server** and no place to attach instructions — meaning palinode is invisible to a user who doesn't manually type "search palinode for X."

This ADR formalizes the surface map, names the levers we have, and sets the priority order for closing the asymmetry.

---

## 2. The Four Levers

Across all harnesses, palinode has at most four mechanisms to influence session-start behavior:

### 2.1 Instruction layer
A markdown file the harness loads into the agent's context every session. Highest leverage; lowest implementation cost.

- Claude Code reads `CLAUDE.md`.
- Cursor reads `.cursor/rules/*.md` (similar role).
- Claude Desktop, Codex CLI, Gemini CLI: **no equivalent.**

### 2.2 Skill layer
A SKILL.md file the harness exposes as a callable capability. Activated by trigger words or pattern match.

- Claude Code: `~/.claude/skills/palinode-session/SKILL.md` (per-user) or `.claude/skills/` (per-project).
- Claude Desktop: same path, same loading.
- Cursor: `.cursor/skills/`.
- Codex CLI, Gemini CLI: **no skills system.**

### 2.3 Lifecycle hook
A shell script the harness invokes on `SessionStart` / `SessionEnd` / `PreToolUse` / `UserPromptSubmit` events.

- Claude Code: full hook system, settings.json driven.
- Claude Desktop: limited (SessionEnd via app integration in some configs; no documented SessionStart hook).
- Cursor, Codex CLI, Gemini CLI: **no hook system.**

### 2.4 Server-side auto-inject (the leveler)
The MCP server itself can choose to push context **without being asked** — either by responding to the implicit `initialize` handshake with a context payload, or by exposing a "first call you should make" tool that the agent discovers and runs.

- Universally available (every MCP client gets it).
- Most invasive — has to be controlled per-scope so it doesn't leak across projects.
- The only mechanism that works for MCP-only harnesses (Claude Desktop, Codex, Gemini CLI).

---

## 3. Decision

Palinode adopts a **layered strategy** that uses each lever where it's available and falls back to the next when it isn't.

### 3.1 Layer 1: Instruction file (scaffold via `palinode init`)

`palinode init` already scaffolds `CLAUDE.md` integration text instructing the agent to call `palinode_search` at session start. This is the cheapest, highest-leverage lever for harnesses that read instruction files.

**Action:** Extend `palinode init` to also write:
- `.cursor/rules/palinode.md` block (Cursor)
- Plain `README.md`-friendly mention for harnesses without a canonical instruction file (best-effort discoverability)

### 3.2 Layer 2: Skill file (scaffold via `palinode init`)

`palinode init` already produces `.claude/commands/{save,wrap,ps}.md`. Extend to produce skill scaffolding for every harness that supports skills:

- `~/.claude/skills/palinode-session/SKILL.md` (Claude Code, Claude Desktop, VS Code, JetBrains)
- `.cursor/skills/palinode-session/SKILL.md` (Cursor, project-scoped)
The SKILL.md content can be the same — only the install path differs.

### 3.3 Layer 3: SessionStart hook (Claude Code only, per PHASE-G)

Implement `palinode-session-start.sh` per `specs/PHASE-G-AMBIENT-CONTEXT.md`:

```bash
# On SessionStart:
curl -s -X POST http://$PALINODE_API_HOST:$PALINODE_API_PORT/context/prime \
  -H "Content-Type: application/json" \
  -d "{\"cwd\": \"$CLAUDE_PROJECT_DIR\", \"session_id\": \"$SESSION_ID\"}"
```

This warms up server-side session context (project entity from CWD, recently-accessed files) so subsequent searches receive the ambient-context boost from ADR-008 without any agent-side action. Tracks against issue **#107** (`/context/prime` endpoint) and **#87** (ambient context boost).

### 3.4 Layer 4: Server-side auto-inject (MCP-only harnesses)

For Claude Desktop, Codex CLI, Gemini CLI, and any harness that gives palinode only an MCP connection: respond to the MCP `initialize` request (or expose a discoverable `palinode_session_init` tool) that returns a project-context summary derived from the same CWD-resolution path the SessionStart hook would have used.

The MCP `initialize` request carries the client's `cwd` (or can be configured to). Palinode can return:

- The list of `core: true` memories for the resolved project scope
- A "recent project decisions" digest (top 5 recently-modified Decision-type memories)
- Open ActionItems tagged to the project

**Critical constraint:** server-side auto-inject must be **scope-aware**. It must NOT bleed across projects. The same MCP server serves multiple harnesses simultaneously; each must see only its own project context.

**Critical constraint #2:** server-side auto-inject must be **opt-in or reversible**. A user who doesn't want every Claude Desktop conversation pre-populated with project memory needs an off switch. Default config: `auto_inject.enabled: true` for MCP-only harnesses, `false` for harnesses that have skill or hook layers (avoid duplication).

---

## 4. Priority Order

The work is sequenced by user impact × implementation cost:

| Priority | Layer | Work | Tracks |
|---|---|---|---|
| **P1** | Layer 3 | `palinode-session-start.sh` for Claude Code | #107 (foundation), new issue (hook script) |
| **P1** | Layer 4 | Server-side auto-inject for MCP-only clients | new issue |
| **P2** | Layer 1 | `palinode init` scaffolds `.cursor/rules/` | new issue |
| **P2** | Layer 2 | `palinode init` scaffolds skill files into all paths | new issue |
| **P3** | Layer 4 | Auto-inject scope chain (per ADR-009) | #107, #108, #109 |

P1 items are blocking adoption for users on harnesses other than Claude Code. P2 closes the long tail. P3 makes auto-inject smart rather than just present.

---

## 5. Consequences

### Positive

- **Memory becomes useful in Claude Desktop / Codex / Gemini.** Today, palinode is invisible in those harnesses unless the user manually types "search palinode" — practical adoption is near-zero. Layer 4 changes that.
- **Single source of truth in the server.** Layer 4's `/context/prime` endpoint is the same one ADR-008's ambient-context boost depends on; building it once unlocks both features.
- **Instruction surface mirrors the OpenClaw "tools-over-pipeline" principle (ADR-001).** The agent is still in charge of *what* to do with memory; palinode just makes sure memory is *available*.

### Negative

- **More moving parts to keep in sync.** Five harnesses × four layers means more places for drift. Mitigated by ADR-010 cross-surface parity contract being already in place.
- **Server-side auto-inject is a security/privacy surface.** A poorly-scoped auto-inject leaks one project's memory into another. Implementation must be careful and the default-on behavior for MCP-only clients needs a clear off-switch.
- **MCP `initialize` response shape is not infinitely extensible.** If we shove too much context into it, latency on cold start grows. Cap at a few KB worth of structured digest, not full memory bodies.

### Neutral

- Existing `palinode init` users on Claude Code see no behavior change until they re-run init or upgrade. Opt-in by re-running.

---

## 6. What This ADR Does NOT Decide

- The exact wire format for `/context/prime` response — left to issue #107.
- The exact MCP `initialize` extension protocol — left to a follow-up issue.
- Whether auto-inject should fire on every conversation turn or only on first turn — empirical question, defer until we have retrieval instrumentation data (ADR-007 / #256).
- Cross-harness UI presentation of the injected context (does the user see "palinode loaded N memories"? where?) — implementation detail per harness.

---

## 7. References

- ADR-008: Ambient Context Search (server-side context boost)
- ADR-009: Scoped Memory & Context Prime (scope hierarchy + `/context/prime` endpoint design)
- ADR-011: Deterministic Slash Commands (related principle: harness boundary)
- `specs/PHASE-G-AMBIENT-CONTEXT.md` (implementation plan)
- `docs/MCP-SETUP.md` (current per-harness install instructions)
- Issue #87 (ambient context search implementation)
- Issue #107 (ADR-009 Layer 1: scope chain + context prime)
- Issue #174 (Claude auto-memory vs palinode coordination)
