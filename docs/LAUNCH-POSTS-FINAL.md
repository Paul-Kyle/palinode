# Palinode Launch Posts — Final Drafts

**Prepared:** 2026-04-05
**Status:** X thread posted. HN Monday. Reddit Tuesday.

---

## X Thread (POSTED 2026-04-05)

Reply to: https://x.com/karpathy/status/2039805659525644595

**Tweet 1 (with blame screenshot):**

I've been building exactly this.

Palinode: git-versioned markdown memory for AI agents. Hybrid BM25+vector search. 18 MCP tools. Deterministic compaction.

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

227 files. 2,230 chunks indexed. 92 tests. 18 MCP tools. No cloud. No external DB. SQLite-vec + FTS5 + BGE-M3.

Runs on a single box. MIT license.

github.com/Paul-Kyle/palinode

---

## Show HN (Wednesday ~9am PT)

**Title:**
Show HN: Palinode – Git-versioned markdown memory for AI agents

**Body (post as first comment):**
I was using Mem0 for agent memory and found myself SSHing into a box to grep Qdrant vectors trying to figure out when my agent learned something wrong. I wanted `git blame` for agent memory. So I built it.

Palinode stores your agent's memory as typed markdown files (people, projects, decisions, insights) with YAML frontmatter. A file watcher indexes them into SQLite-vec + FTS5 for hybrid search. Weekly, an LLM proposes structured compaction ops (KEEP/UPDATE/MERGE/SUPERSEDE/ARCHIVE) and a deterministic executor applies them — the LLM never writes files directly. Every compaction is a git commit.

The part I think is actually new: diff, blame, rollback, and push are MCP tools your agent can call. Not just git-compatible files — the agent can trace any fact back to the session that recorded it, or revert a bad compaction, without you touching a terminal.

Architecture is dumb on purpose. Markdown files are truth. SQLite is a derived index. If everything crashes, `cat` still works. One API server, one .db file, one directory.

It runs on a homelab box. I connect from two laptops over Tailscale. The MCP server is a pure HTTP client with no state — works with Claude Code, Cursor, Zed, anything that speaks MCP. Same 18 tools are also available as a REST API and CLI.

Karpathy's knowledge-base gist (https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) articulated a lot of what I was already building toward — particularly the raw/compiled split, which maps directly to Palinode's ingest/consolidate cycle. This is one working implementation of those ideas.

What it doesn't do: no auto-injection into arbitrary LLM calls (you need an MCP client or to call the API). No multi-user. No cloud hosted version. It's a personal tool for one human and their agents.

Python 3.11+, BGE-M3 via Ollama, any chat model for consolidation. 92 tests. MIT.

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

18 tools, 92 tests, MIT: https://github.com/Paul-Kyle/palinode

---

## r/MachineLearning (Tuesday)

**Title:**
[P] Palinode — persistent agent memory with deterministic compaction and git provenance

**Body:**
I built a persistent memory system for LLM agents where the storage layer is git-versioned markdown and the compaction layer uses a structured operation DSL.

The architecture: markdown files → SQLite-vec + FTS5 hybrid index → 4-phase injection (core, topic search, entity graph, prospective triggers). Weekly consolidation where an LLM proposes operations (KEEP/UPDATE/MERGE/SUPERSEDE/ARCHIVE) over per-fact IDs embedded in markdown, then a deterministic executor applies them. Every compaction is a reviewable git commit.

The design bet: files are the source of truth, everything else is a derived index. One backend, multiple interfaces (MCP server over Streamable HTTP, REST API, CLI, OpenClaw plugin). 18 tools work identically across Claude Code, Zed, Cursor, or shell scripts.

Behavioral spec in PROGRAM.md. 92 tests. MIT.

https://github.com/Paul-Kyle/palinode
