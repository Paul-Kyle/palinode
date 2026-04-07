# Palinode Launch Posts — Final Drafts

**Prepared:** 2026-04-05
**Status:** X thread posted. HN Monday. Reddit Tuesday.

---

## X Thread (POSTED 2026-04-05)

Reply to: https://x.com/karpathy/status/2039805659525644595

**Tweet 1 (with blame screenshot):**

I've been building exactly this.

Palinode: git-versioned markdown memory for AI agents. Hybrid BM25+vector search. 17 MCP tools. Deterministic compaction.

The part I added? git blame on every fact your agent knows.

github.com/Paul-Kyle/palinode

**Tweet 2:**

The architecture maps 1:1:

Your raw/ → palinode ingest
Compile → Consolidation executor (LLM proposes JSON ops, deterministic executor applies)
Query → Hybrid BM25 + vector, RRF fusion
Lint → palinode lint (orphans, stale files, contradictions)

Same philosophy. With provenance.

**Tweet 3:**

• git blame/diff/rollback as MCP tools
• Per-fact IDs — invisible in markdown, targetable by compaction
• Deterministic executor: LLM proposes, never touches files
• Works across Claude Code, Cursor, Zed, OpenClaw, etc
• If every service crashes, cat still works

**Tweet 4 (with status screenshot):**

227 files. 2,230 chunks indexed. 56 tests. 17 MCP tools. No cloud. No external DB. SQLite-vec + FTS5 + BGE-M3.

Runs on a single box. MIT license.

github.com/Paul-Kyle/palinode

---

## Show HN (Monday ~8am ET / 5am PT)

**Title:**
Show HN: Palinode – Persistent agent memory as plain markdown with git provenance

**Body:**
Palinode is persistent memory for AI agents. Your agent's memory is a folder of markdown files — typed (people, projects, decisions, insights), git-versioned, and searchable with hybrid BM25 + vector.

The architecture is simple: markdown files are truth, SQLite (vec + FTS5) is a derived index, and every interface (MCP, REST API, CLI, agent plugin) hits the same backend. Set up on a server, connect from any IDE on any machine.

What made me build this:

I was using Mem0, then found myself grepping the Qdrant vectors trying to figure out when my agent learned something wrong. I wanted `git blame` for agent memory. So I built it.

What's different:

- **Files are truth** — if every service crashes, `cat` still works. Rebuild the index anytime.
- **Git operations as agent tools** — diff, blame, rollback, push are callable MCP tools, not just CLI conveniences.
- **Deterministic compaction** — an LLM proposes structured ops (KEEP/UPDATE/MERGE/SUPERSEDE/ARCHIVE), a deterministic executor applies them and commits. The LLM never writes files directly.
- **One backend, every interface** — MCP server (Streamable HTTP or stdio), REST API, CLI, OpenClaw plugin. Same 18 tools everywhere. Connect Claude Code, Zed, Cursor, Claude Desktop, or your own scripts.
- **No infrastructure** — SQLite-vec + FTS5 + Ollama. No Postgres, no Redis, no cloud. One directory, one .db file, one API server.

Stack: Python 3.11+, BGE-M3 embeddings via Ollama, any chat model for consolidation. 56 tests. MIT.

I run it on a homelab box and connect from two laptops over Tailscale. The MCP server is a pure HTTP client — it holds no state, just proxies to the API.

https://github.com/Paul-Kyle/palinode

---

## r/LocalLLaMA (Tuesday)

**Title:**
Palinode: fully local agent memory — markdown files, SQLite-vec, git blame on every fact

**Body:**
I built a persistent memory system for AI agents that's fully local. No cloud, no API keys, no external databases.

Your agent's memory is a folder of typed markdown files. Palinode indexes them (BGE-M3 + FTS5), searches them (hybrid BM25 + vector with RRF fusion), and compacts them weekly with a local LLM.

Local stack:
- Embeddings: BGE-M3 via Ollama (runs on any GPU or CPU)
- Consolidation: any local chat model (I use OLMo 3.1 32B on a local GPU)
- Index: SQLite-vec + FTS5 — single .db file, no server
- Storage: plain markdown, git versioned

The compaction is the interesting part: the LLM proposes structured ops (KEEP/UPDATE/MERGE/SUPERSEDE/ARCHIVE), then a deterministic executor applies them. The LLM never touches your files directly. Every compaction is a git commit.

It works from any IDE — the MCP server runs over Streamable HTTP, so Claude Code, Zed, Cursor all connect via URL. I run it on a homelab box and connect from two laptops over Tailscale. Or use the CLI for scripts and cron.

Browse your agent's brain in Obsidian. If Ollama dies, cat and grep still work.

18 tools, 56 tests, MIT: https://github.com/Paul-Kyle/palinode

---

## r/MachineLearning (Tuesday)

**Title:**
[P] Palinode — persistent agent memory with deterministic compaction and git provenance

**Body:**
I built a persistent memory system for LLM agents where the storage layer is git-versioned markdown and the compaction layer uses a structured operation DSL.

The architecture: markdown files → SQLite-vec + FTS5 hybrid index → 4-phase injection (core, topic search, entity graph, prospective triggers). Weekly consolidation where an LLM proposes operations (KEEP/UPDATE/MERGE/SUPERSEDE/ARCHIVE) over per-fact IDs embedded in markdown, then a deterministic executor applies them. Every compaction is a reviewable git commit.

The design bet: files are the source of truth, everything else is a derived index. One backend, multiple interfaces (MCP server over Streamable HTTP, REST API, CLI, OpenClaw plugin). 18 tools work identically across Claude Code, Zed, Cursor, or shell scripts.

Behavioral spec in PROGRAM.md. 56 tests. MIT.

https://github.com/Paul-Kyle/palinode
