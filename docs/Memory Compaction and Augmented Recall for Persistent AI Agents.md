# Memory Compaction and Augmented Recall for Persistent AI Agents (2025–2026)

## Executive Summary

Recent work on long-horizon LLM agents converges on a few key principles for persistent memory: (1) separate fast in-context memory from slower long-term stores, (2) make memory *mutable* and *selectively forgetful* rather than append-only, (3) use background "sleep" processes to consolidate and compact, and (4) move from pure similarity search toward associative, graph- or activation-based recall.[^1][^2][^3]
Systems like Letta/MemGPT, LangMem, Mastra's Observational Memory, Zep/Graphiti, Cognee, and Zilliz's memsearch implement these principles with different trade-offs around transparency, latency, and retrieval style.  Academic work from 2024–2026 on memory benchmarks, selective forgetting, temporal decay, and sleep-inspired consolidation provides design patterns that can be applied directly to a file-based, git-versioned memory system such as Palinode.[^4][^5][^6][^7][^3][^8][^9][^10][^11][^12][^13][^1]

For Palinode, the most promising architecture is a **layered memory system**: (a) append-only episodic logs, (b) per-entity and per-project semantic files with structured facts and status, and (c) a background "sleep" job that rewrites semantic files via LLM tools implementing explicit operations (KEEP, UPDATE, MERGE, ARCHIVE, SUPERSEDE) under a provenance-preserving schema. This can be combined with **associative recall** driven by entity graphs and spreading activation, and **prospective triggers** that surface memories when relevant context appears, not only when the agent explicitly searches.[^14][^15][^16][^1]

***

## 1. Comparison of Compaction and Recall Approaches Across Systems

### 1.1 High-level comparison table

| System | Memory representation | Compaction / consolidation | Associative / augmented recall | Temporal handling | Notes |
|--------|-----------------------|----------------------------|--------------------------------|-------------------|-------|
| **Letta / MemGPT-style** | **Core memory blocks** kept in-context ("human", "persona", etc.), plus external archival stores and conversation history.[^4][^17][^18] | Letta enforces per-block length limits (default ~2k chars) and uses summarization-based **memory compaction** when context budgets are exceeded; sleep-time agents rewrite blocks asynchronously into "learned context".[^19][^20][^21][^22] MemGPT exposes tools like `core_memory_replace` and `archival_memory_insert` so the agent can rewrite or replace memories rather than append-only.[^18][^23] | Primarily retrieval-triggered: agents search archival memory or conversation history via tools and pull results into core blocks. Sleep-time agents can also consolidate across history into new blocks that function as always-visible associative context.[^4][^19][^24] | Uses block size limits plus optional compaction; temporal information largely implicit in text, though sleep-time agents preferentially work over recent history.[^19][^20] | Strong abstraction (blocks) and good ergonomics; compaction is summary-based and block-local, not global graph-based. Works well with background agents modulating memory at "sleep" times.[^19][^25] |
| **LangMem** | Long-term memories as structured JSON-like objects (e.g., triples or typed records) stored in a LangGraph `BaseStore`.[^5][^26][^27] | A **memory manager** agent (or single-call manager) receives existing memories and new messages, and emits operations to **create**, **update**, or **delete** memories. With deletes enabled, it returns `RemoveDoc` objects that callers can implement as hard delete, soft-delete, or downweighting.[^5][^26][^27] | Retrieval generally vector + metadata search over stored items; LangMem itself does not prescribe spreading-activation or KGs but can be combined with them. A separate manager agent can perform multi-step reflection over memories.[^5][^27] | Supports recency via timestamps and custom scoring, but temporal decay / contradiction handling policies are left to the developer.[^27] | Very close to what Palinode needs: explicit functional API for **keep/merge/delete** decisions driven by LLM tools, decoupled from storage representation.[^5][^27] |
| **Zilliz memsearch** | Markdown-first memory: plain-text `.md` files are the source of truth; Milvus index is just a derived semantic/BM25 index.[^28][^29][^12][^30] | Provides a `compact` command that **retrieves historical chunks and LLM-summarizes them into condensed markdown**, then archives or deletes originals. The ccplugin for Claude Code writes daily session summaries, and memsearch Compact can summarize older days into higher-level notes.[^12][^31][^32] | Recall is **search-triggered**: hybrid semantic + BM25 search on chunks, with optional progressive disclosure layers (summaries → timelines → raw transcripts) in the Claude Code plugin.[^12][^32] | Temporal ordering is implicit via filenames (daily logs) and timestamps in summaries; compaction is time-based (older logs get summarized).[^31][^32] | Architecturally almost identical to Palinode: markdown + git + hybrid search. Compact is pure summarization without structural rewriting of fact graphs.[^12][^31] |
| **Mastra Observational Memory (OM)** | Two blocks: (1) **Observation log** (dense list of dated observations: events, tool calls, preferences, etc.), (2) recent raw message history. Observations live at the *start* of context; messages at the end.[^6][^33][^7] | Background **Observer** agent compresses raw messages into observations once history exceeds a threshold (≈30k tokens by default, configurable). A **Reflector** periodically restructures and condenses the observations, merging related entries and dropping low-priority ones to keep context bounded while preserving high-priority facts.[^33][^7][^34][^35] | There is **no per-turn retrieval**; instead, the observation log is always in context. Associativity comes from how observations are written (they explicitly encode entities, tasks, and preferences) and how the Reflector groups them.[^7][^34] | Each observation is timestamped and priority-tagged; Reflector prefers to drop older, low-priority items, achieving 3–40× compression while maintaining accuracy on LongMemEval.[^33][^34] | OM delivers a *stable, cacheable context* instead of dynamic RAG. This is effectively continuous compaction of history into a dense event log.[^33][^34] |
| **Zep / Graphiti** | **Temporal knowledge graph** with separate episodic, semantic, and community subgraphs; nodes represent entities/episodes, edges represent temporally-scoped facts and relations.[^1][^36][^37] | Compaction is **structural rather than lossy**: new facts create new edges; conflicting edges are **invalidated via temporal extraction and edge invalidation**, not deleted, so history is preserved. Higher-level entity and community summaries compress local neighborhoods for retrieval.[^1][^38] | Associative recall is **graph-based**: retrieval functions search for relevant edges, entity nodes, and community nodes, and traverse their connections. This enables multi-hop reasoning (A→B→C), temporal queries, and "what else is related to this episode?" queries.[^1][^36][^38] | Bi-temporal model tracks event time and transaction time; edges have `t_valid` / `t_invalid` and created/expired timestamps. New contradictory facts invalidate overlapping old facts by adjusting `t_invalid`.[^1][^38] | Strong template for contradiction-driven compaction & provenance-preserving history; more complex than Palinode’s current flat file model, but many ideas can be approximated in SQL + markdown.[^1][^38] |
| **Cognee** | Unified **knowledge graph + vectors** over ingested files/APIs/DBs, built via Extract–Cognify–Load pipeline (ECL). Entities and relations form a graph in Kuzu; LanceDB holds aligned embeddings.[^39][^40][^41] | A background **Memify pipeline** cleans stale nodes, strengthens associations, reweights important facts, and can add new associations, all without full re-ingestion. This is a graph-oriented compaction and refinement layer rather than pure summarization.[^39][^40][^41] | Multi-hop retrieval uses the knowledge graph for reasoning (e.g., entity A → relationship → entity B → facts), with embeddings as a parallel channel; this improves multi-hop QA like HotPotQA.[^39][^40] | Recent features add **temporal cognification**: building event-centric graphs with explicit timestamps and relations like before/after/during, plus a dynamic notion of "now" per chunk.[^42] | Demonstrates a mature **memory-first architecture** where recall is inherently multi-hop and time-aware. Compaction is continuous reweighting and graph repair, not destructive deletion.[^39][^41][^42] |
| **Shodh Memory (for augmented recall)** | Typed memories with importance weights, stored locally; supports hybrid vector + graph retrieval and **proactive context**.[^14][^16] | Not an explicit compaction layer; relies on importance weighting and TTLs. The system emphasizes *not* auto-saving everything; it attaches sources, timestamps, and short TTLs to new memories.[^16] | Implements **prospective / context-triggered recall**: developers can register "intentions" with semantic descriptions; every new context is checked against these embeddings, and when similarity crosses a threshold, the intention is surfaced automatically (no explicit search).[^14][^16] Also supports spreading activation over a memory graph.[^14] | Memories can decay via TTL and importance-weighted aging; recalled items can be reinforced. Temporal reasoning is basic compared to Zep/Cognee.[^14][^16] | Provides a concrete implementation of **context-triggered recall** and spreading activation that can be re-created over Palinode’s SQLite + vec schema.[^14][^16] |

***

## 2. Memory Compaction Strategies

### 2.1 Letta / MemGPT: block-level compaction and sleep-time agents

Letta’s **memory blocks** are discrete, labeled segments of the context (e.g., `human`, `persona`, `knowledge`) persisted in a DB and always injected into the prompt. Each block has a configurable character limit (default ≈2,000 chars) because blocks are always in-context; exceeding the limit leads to an error that the agent must handle by rewriting or shrinking the block. A separate "context budget management" component ensures that older interaction messages are summarized instead of being naively truncated when windows fill.[^17][^20][^21][^4]

Letta extends the original MemGPT idea of self-editing memory by introducing **sleep-time agents** that share memory blocks with the primary agent but run asynchronously in the background. Sleep-time agents:[^18][^19][^24]

- Read conversation history and other data sources.
- Reflect to derive **learned context** (higher-level summaries, patterns, and cleaned-up memories).
- Rewrite core memory blocks of the primary agent to keep them concise and up to date (e.g., merging scattered notes about a project into a single canonical summary).[^19][^24][^25]

This pattern effectively implements **compaction-as-rewrite**: the sleep agent is responsible for periodic consolidation and pruning, while the primary agent may do small tactical edits.

### 2.2 LangMem: functional memory managers with create/update/delete

LangMem’s core abstraction is a **memory manager** that transforms a list of existing memories plus new messages into a new list of memories, emitting operations to create, update, or remove documents. Examples from the docs show the manager returning `ExtractedMemory` objects that either wrap a new structured content (e.g., `UserFoodPreference` records) or a `RemoveDoc` wrapper indicating that a previous memory should be deleted.[^5][^26][^27]

Developers can:

- Run the manager inline, updating an in-memory list.
- Or create a separate agent (`create_react_agent`) that uses tools `create_manage_memory_tool` and `create_search_memory_tool` to manage memories over multiple LLM calls in the background.[^5]

Crucially, LangMem decouples **decision logic** from storage: the manager decides *what should happen* (`update`, `remove`, `create`), while the calling code decides whether deletion means hard delete, archival, or downweighting. This matches Palinode’s needs: a weekly job can be a manager that outputs structured operations that a Git-aware executor applies to markdown files.[^27][^5]

### 2.3 memsearch: markdown-first summarization compaction

memsearch treats **markdown files as the only source of truth**; Milvus indices are fully reconstructable and can be dropped at any time. It provides a `compact` mode that:[^28][^29][^12][^31]

- Retrieves historical chunks (e.g., older daily logs or notes).
- Calls an LLM to **summarize** them into a condensed markdown representation.
- Writes the summary to a target file (often a new daily or project summary) and optionally deletes or archives the originals.[^12][^31][^30]

This is the canonical **append-with-summarize-and-archive** strategy: compaction is lossy but human-auditable. For Claude Code, a companion plugin writes daily session summaries in plain markdown, and memsearch Compact is suggested for summarizing older days into higher-level recaps.[^32]

### 2.4 Mastra Observational Memory: continuous compression into observations

Mastra’s Observational Memory (OM) removes retrieval from the hot path entirely: the main agent always sees a **two-block context** consisting of (1) a log of structured observations and (2) the recent raw message history. Observations are small textual entries capturing discrete events, preferences, tool results, and inferred state, each tagged with date and priority.[^6][^33][^7][^43]

Two background agents run:

- **Observer**: Watches the conversation; when raw message history exceeds a threshold (default ~30k tokens), it compresses recent messages into new observations appended to the observation block, then drops the raw messages.[^33][^7]
- **Reflector**: Periodically reads the entire observation log and restructures it, combining related observations, dropping low-priority or obsolete items, and producing a denser, shorter log while preserving critical facts.[^7][^34][^35]

This architecture delivered SOTA on LongMemEval, even outperforming an "oracle" that had only the exact conversations containing the answer, suggesting that **structured observational summaries are more useful than raw history**.[^34][^35][^33]

### 2.5 Zep / Graphiti: non-lossy temporal graphs and edge invalidation

Zep’s memory layer is built on **Graphiti**, a temporally aware knowledge graph engine that synthesizes unstructured conversation and structured business data into a single graph of entities, episodes, and communities. Zep stores both:[^36][^37][^1]

- **Episodic subgraph**: episodes (messages, events) and their entity edges.
- **Semantic subgraph**: fact-level edges and entity summaries.[^1]

Compaction is achieved via structure and metadata rather than summarization:

- New fact edges carry validity intervals (`t_valid`, `t_invalid`) along with transaction times (`t'_created`, `t'_expired`).[^1]
- When a new edge contradicts an existing one in overlapping time ranges, an LLM-based comparison process **invalidates** the old edge by setting its `t_invalid` to the new edge's `t_valid`, effectively marking it as superseded without deletion.[^1]
- Entity and community summaries provide compressed, higher-level representations but maintain back-references to underlying episodes for provenance and deep inspection.[^1]

This yields a **non-lossy compaction**: current truth is easy to query, but historical facts remain accessible with precise temporal semantics.[^38][^1]

### 2.6 Cognee: Memify and temporal cognification

Cognee builds a memory layer by unifying a knowledge graph with a vector store: an ECL (Extract–Cognify–Load) pipeline parses inputs into entities, relations, timestamps, and embeddings stored in a graph DB (Kuzu) and LanceDB. The **Memify** pipeline then:[^39][^40][^41]

- Cleans stale nodes and edges.
- Strengthens associations that recur or receive positive feedback.
- Reweights important facts to improve retrieval quality without full re-ingestion.[^41][^39]

Recent "temporal cognification" features introduce an **event-based graph with explicit timestamps and temporal relations (before/after/during)**, plus a sparse chain representation of timelines that can be extended incrementally. This allows compaction that respects time: old events can be downweighted or aggregated into coarser events while preserving ordering and intervals.[^42]

### 2.7 Academic perspectives: selective forgetting, decay, and consolidation

Several 2024–2026 works distill general principles:

- **MemoryAgentBench** defines four competencies for memory agents: accurate retrieval, test-time learning, long-range understanding, and **selective forgetting**; current systems perform poorly at selective forgetting, especially in multi-hop scenarios.[^8][^44]
- Surveys and systems like **FadeMem** and MaRS argue that agents must implement **importance-weighted temporal decay**, separate fast and slow memory layers, and treat forgetting as a first-class operation to avoid memory poisoning and bloat.[^45][^46][^9]
- Biologically inspired approaches like **SleepGate** introduce sleep-inspired consolidation at the KV-cache level, using conflict-aware tagging, learned forgetting gates, and consolidation modules that merge superseded entries into compact representations.[^47]
- Cognitive benchmarks and reviews (e.g., Memory for Autonomous LLM Agents, Continuum Memory Architectures, Memory-Augmented Transformers) emphasize dual-phase consolidation (fast episodic, slow semantic), hippocampal replay, and spreading activation as core design patterns.[^2][^3][^11]

These works collectively suggest: compaction should be **importance-aware**, **temporally informed**, and **provenance-preserving**, with explicit mechanisms for both summarization and contradiction resolution.

***

## 3. Augmented / Associative Recall

### 3.1 Spreading activation and associative graphs

Cognitive theories model semantic memory as a network where activating one concept ("Peter") increases activation of connected nodes ("canon decisions", "5-act structure"). Synapse applies this directly by modeling memory as a dynamic episodic–semantic graph and using **spreading activation with lateral inhibition and temporal decay** for retrieval.[^15][^48]

The retrieval pipeline in Synapse:

1. Identifies **anchor nodes** using both lexical (BM25) and semantic triggers for a query.
2. Propagates activation across edges for a few steps, with decay and competition limiting spread.
3. Produces a ranked subgraph of nodes and edges representing a focused context.[^15]

On long-horizon LoCoMo tasks, Synapse significantly improved temporal and multi-hop reasoning accuracy (up to +23 F1) while reducing tokens by ≈95% relative to full-context approaches, demonstrating that activation-based associative recall is both more accurate and more efficient than naive vector search.[^15]

### 3.2 Zep / Graphiti: temporal knowledge graphs for associative recall

Graphiti uses a **multi-tier temporal knowledge graph**: episodic, semantic, and community graphs. Retrieval first finds candidate nodes and edges (semantic facts, entities, communities) and then traverses their neighborhood to assemble context. Because edges track validity intervals and maintain bidirectional links to source episodes, the system supports:[^36][^1]

- Multi-hop associations: A→B→C queries (e.g., "projects Alice worked on that involved Kubernetes and were active last year").
- Temporal queries: "What was true about entity X in March 2024?" vs current truth.
- Backtracking from semantic summaries to raw episodic data for provenance.[^38][^1]

This is associative recall by **graph traversal** rather than top-K similarity; activation over neighbors yields the context, not a flat top-3 embedding result.

### 3.3 Cognee: multi-hop over KG + embeddings

Cognee’s architecture unifies a graph and a vector store so that applications can perform questions like "What regulations affected this product launch?" by following **entity→relation→entity** chains and supplementing with similarity search. Its reported improvements on multi-hop QA tasks like HotPotQA come from this **graph-aware retrieval**, and the Memify pipeline refines the graph by adding associations and reweighting key nodes based on use.[^40][^39][^41]

Temporal cognification adds another axis: event nodes with before/after relations let applications retrieve context like "What events led up to the last deployment failure?" by traversing along time-ordered paths.[^42]

### 3.4 Context-triggered recall and prospective memory

Shodh Memory explicitly frames a second type of memory: **prospective memory**—remembering to do something when a certain context occurs ("If you see groceries, remember milk"). Its `proactive_context` tool:[^16][^14]

- Lets developers store "intentions" with semantic descriptions.
- Embeds these intentions and stores them as standing queries.
- On each new input, automatically checks similarity to intentions and, when above a threshold, surfaces the relevant memory to the agent without an explicit search call.[^14][^16]

This is a direct implementation of **context-triggered recall**. The same system supports spreading activation over a memory graph, where queries activate not only direct matches but also connected memories via edges.[^14]

### 3.5 Episodic recall triggers

Cognitive-inspired agent work emphasizes that episodic memory (episodes, tasks, conversations) should also be recallable: "Last time we discussed X, we decided Y." Zep’s episodic subgraph, which links episodes to entities and semantic facts, allows queries like "episodes where entity A and entity B co-occurred" and "what else happened in the same episode as decision D".[^1]

Academic systems such as **Continuum Memory Architectures (CMA)** also highlight this: consolidation jobs run replay walks over recent sequences, strengthen temporal chains, and extract "gist" nodes that summarize sequences while retaining back-links to raw fragments that can be reactivated when needed.[^11]

### 3.6 Empirical retrieval scoring: recency, importance, relevance

Experimental work on generative agents shows that simple retrieval scoring combining **recency, importance and semantic relevance** already yields strong performance:[^10][^49]

\[
\text{Score}(m) = w_r \cdot \text{Recency}(m) + w_i \cdot \text{Importance}(m) + w_s \cdot \text{Relevance}(m, q)
\] [^4]

Here, Recency decays hourly (e.g., factor 0.995 per hour), Importance is rated by an LLM, and Relevance is cosine similarity between memory and query embeddings. More advanced models (ACAN, SynapticRAG, MyAgent) plug such scores into cross-attention modules or spiking-like decay models to dynamically balance recent vs long-term memories across languages and datasets.[^50][^49][^10]

***

## 4. Compaction Architecture Patterns for Palinode

This section distills patterns from the above systems into implementable designs for a **file-based, git-versioned memory store** using markdown + SQLite-vec + FTS5.

### 4.1 Layered memory: episodic, semantic, and status layers

A practical architecture for Palinode:

1. **Episodic layer (append-only)**
   - Daily/session logs under `logs/YYYY-MM-DD.md` capturing raw OpenClaw transcripts, tool traces, etc.
   - This matches memsearch/OpenClaw style and is ideal for git history and auditing.[^31][^32]

2. **Semantic layer (project + entity facts)**
   - Files like `projects/palinode.md`, `people/peter.md`, `concepts/lora.md` containing **canonical facts and long-lived insights**.
   - Each fact is a small block with metadata: ID, type (Decision, Preference, Insight, Fact), timestamps (`created_at`, `updated_at`), importance score, and provenance (source log file + commit hash).
   - This mirrors LangMem’s structured memories, Zep’s semantic subgraph, and Cognee’s knowledge graph but encoded in markdown frontmatter + sections.[^39][^5][^1]

3. **Status layer (fast-changing state)**
   - Files like `projects/palinode_status.md` or `students/peter_status.md` that track current milestones, open tasks, and live config.
   - Designed for frequent updates and aggressive compaction (e.g., only the last N states kept, plus an archived history file).

4. **Index & graph layer (SQLite)**
   - SQLite tables (or views over Palinode’s existing DB) representing memories as rows with columns: `id`, `entity`, `project`, `type`, `text`, `created_at`, `updated_at`, `importance`, `strength`, `provenance`, plus edges for `subject`, `predicate`, `object` relations.
   - FTS5 for BM25, sqlite-vec for embeddings, and adjacency tables for simple knowledge-graph traversal.

This provides the substrate for both **compaction** (by operating over semantic/status layers) and **associative recall** (by traversing entity and relation edges) while leaving episodic logs untouched for provenance.

### 4.2 Weekly "sleep" job as a memory manager

Implement a cron-style job (`palinode_sleep`) that acts like LangMem’s memory manager and Letta’s sleep-time agent:

1. **Ingest recent episodes**
   - Query logs for the last week per project or entity.
   - Group by project and entity to get relevant slices.

2. **Fetch current semantic/state memories**
   - Load relevant project and entity markdown into structured memory objects (one per fact/decision/preference/status entry).

3. **Call an LLM with a compaction prompt** that:
   - Lists current memories (structured JSON or numbered bullets with IDs).
   - Provides new episodic snippets (summaries of recent sessions, not raw logs).
   - Asks the model to emit a list of operations with an explicit schema:

```json
{
  "operations": [
    {
      "op": "KEEP",  
      "id": "fact_23"
    },
    {
      "op": "UPDATE", 
      "id": "fact_5",
      "new_text": "Peter prefers 5-act structure for feature-length story development, and avoids 3-act templates.",
      "rationale": "Refined preference expressed multiple times this week.",
      "provenance": ["logs/2026-03-21.md#peter", "logs/2026-03-24.md#story-structure"]
    },
    {
      "op": "MERGE", 
      "ids": ["fact_8", "fact_19"],
      "new_text": "For LoRA training, prioritize curation over volume: fewer, highly representative samples outperform large noisy datasets.",
      "provenance": ["logs/2026-03-18.md#lora", "logs/2026-03-19.md#experiments"],
      "importance": 0.9
    },
    {
      "op": "SUPERSEDE", 
      "id": "fact_12",
      "new_text": "Palinode’s consolidation now rewrites summaries instead of appending, eliminating stale milestones.",
      "provenance": ["logs/2026-03-27.md#palinode-arch"],
      "reason": "New design intentionally replaces old behaviour.",
      "superseded_at": "2026-03-27"
    },
    {
      "op": "ARCHIVE", 
      "id": "fact_3",
      "archive_reason": "Low importance and no references in last 90 days."
    }
  ]
}
```

4. **Apply operations via a deterministic executor**
   - Use a programmatic layer to:
     - Edit markdown files accordingly (UPDATE text in place, MERGE to new entries and mark old ones `superseded_by: <new_id>`, ARCHIVE to `archive/` files).
     - Append provenance and timestamps as YAML frontmatter or inline comments.
   - Commit the changes to git with a standardized message (e.g., `chore(memory): weekly compaction for project palinode`).

This keeps LLMs out of the git layer while leveraging them for the semantic judgment of what to keep vs. merge vs. archive.

### 4.3 Prompt templates for compaction and conflict resolution

A base system prompt for the compaction LLM, borrowing from LangMem and Zep patterns:[^5][^1]

```text
You are a memory manager for a long-term AI assistant. 

You receive:
- A list of EXISTING_MEMORIES (facts, decisions, preferences, statuses), each with:
  - id, type, text, created_at, updated_at, importance, strength, provenance
- A list of NEW_EPISODIC_SUMMARIES with timestamps and source log files.

Your job is to:
1. Preserve important, stable facts.
2. Update or supersede outdated facts when new information contradicts or refines them.
3. Merge redundant or overlapping entries into a single, clearer memory.
4. Archive low-importance, stale memories.
5. Never silently delete; always use ARCHIVE or SUPERSEDE.

Consider:
- Recency (newer evidence usually wins unless explicitly marked tentative).
- Frequency and importance of mention.
- Explicit contradictions ("I no longer", "That changed", "We switched to", etc.).

Output ONLY a JSON object with an `operations` array. Use the schema:
- KEEP: {"op": "KEEP", "id": ...}
- UPDATE: {"op": "UPDATE", "id": ..., "new_text": ..., "provenance": [...], "rationale": ...}
- MERGE: {"op": "MERGE", "ids": [...], "new_text": ..., "provenance": [...], "importance": float}
- SUPERSEDE: {"op": "SUPERSEDE", "id": ..., "new_text": ..., "provenance": [...], "reason": ..., "superseded_at": ...}
- ARCHIVE: {"op": "ARCHIVE", "id": ..., "archive_reason": ...}
```

For contradiction-driven compaction, adopt Zep-style temporal semantics:[^1]

- When a new fact clearly contradicts an old fact about the same subject and relation, produce a `SUPERSEDE` op and record `superseded_at`.
- The executor moves the old memory into an **archive section** with fields `valid_until` and `superseded_by` while leaving the text intact for provenance.

### 4.4 Temporal decay and importance scoring

Each memory should maintain a **strength** scalar used for retrieval scoring and decay:

- Initialize `strength` from LLM-rated importance (`importance`), boosted when the memory is recalled or referenced (retrieval reinforcement).[^51][^9][^10]
- Apply exponential or Weibull-based decay over time since last retrieval, as suggested by governance work on temporal decay and forgetting policies.[^52][^51]

Example scoring function (at retrieval time):

\[
\text{Strength}_t(m) = \text{importance}(m) \cdot e^{-\Delta t / \tau} \cdot (1 + \log(1 + f_m))
\] [^53]

Where \(\Delta t\) is time since last retrieval or update, \(\tau\) is a half-life-like constant that differs by memory type (e.g., Decisions vs. Status), and \(f_m\) is the frequency of retrieval.[^9][^51][^10]

Approximate defaults inspired by FadeMem and cognitive curves:[^9][^11]

- Critical configuration / safety facts: \(\tau \approx 90\) days.
- Core preferences & identity: \(\tau \approx 60\) days.
- Project status: \(\tau \approx 14\) days.
- Ephemeral context (one-off errors, transient messages): \(\tau \approx 7\) days.

Memories whose decayed strength falls below a threshold and have not been referenced within a window (e.g., 60–90 days) can be candidates for `ARCHIVE` or aggressive summarization.

### 4.5 Replace vs. append and layered files

The systems surveyed suggest a hybrid of **rewrite** and **append**:

- For **core facts and long-lived insights** (semantic layer), prefer **rewrite/merge** with explicit supersession rather than infinite append; this keeps files small and canonical, like Zep’s current facts or Memora’s primary abstractions.[^54][^1]
- For **status updates and history**, maintain shorter main files (recent snapshots) and move old states to an `*_history.md` archive, possibly summarized.[^33][^34]
- For **raw episodes**, keep append-only daily logs.

Physically, Palinode can use:

- `projects/palinode.md` (canonical facts, decisions, stable insights).
- `projects/palinode_status.md` (current status only; overwritten each week with compaction).
- `projects/palinode_history.md` (archived older statuses and superseded facts, perhaps auto-summarized quarterly).

This keeps working files small for injection, while retaining full history in archive files that are rarely loaded.

***

## 5. Practical Implementations & Code Patterns

### 5.1 LangMem-style memory manager in pseudo-code

A basic Palinode compaction manager (Python-like pseudo-code):

```python
from palinode import load_project_memories, load_recent_logs, apply_memory_ops
from llm_client import call_llm

def run_compaction(project_id: str, since_days: int = 7):
    existing = load_project_memories(project_id)  # list[Memory]
    recent = load_recent_logs(project_id, since_days)  # list[EpisodicSummary]

    prompt = build_compaction_prompt(existing, recent)
    ops_json = call_llm(model="claude-3.5-sonnet", system=COMPACTION_SYSTEM_PROMPT, user=prompt)
    ops = json.loads(ops_json)["operations"]

    apply_memory_ops(project_id, existing, ops)  # rewrites markdown + archives
```

This mirrors LangMem’s `manager.invoke({"messages": messages, "existing": existing})` call, but the storage backend is markdown + git.[^26][^5]

### 5.2 memsearch-style compact integration

Since Palinode already uses markdown and hybrid search, it can adopt memsearch’s pattern for timeline compaction:[^30][^12][^31]

```bash
# Example CLI pattern akin to memsearch
palinode compact \
  --source logs/2026-02-*.md \
  --target projects/palinode_history.md \
  --model claude-3-haiku \
  --strategy timeline
```

Where `--strategy timeline` instructs a small LLM to produce a dated list of events, decisions, and outcomes at a coarser granularity.

### 5.3 Observational Memory-lite for Palinode

To emulate Mastra’s OM without abandoning retrieval:

- Maintain `observations/` files per project, where a lightweight background job writes **short observations** whenever tool calls or decisions occur.
- Cap each observations file to a token budget; when the file exceeds that, run a **Reflector** LLM that merges related observations and compresses the file by 40–60%, preserving date and priority tags.[^35][^7][^33]

Pseudo-prompt for the Reflector:

```text
You are an observation reflector.
You receive a chronological list of observations.
Each observation has a timestamp, priority (high/med/low), and text.

Your job:
- Merge redundant or closely related observations.
- Drop low-priority items that are unlikely to be useful in future reasoning.
- Preserve all high-priority and critical decisions.
- Keep timestamps but you may coarsen them (e.g., group events within the same day).

Output a new list of observations, in the same format, but about 40–60% fewer entries.
```

Palinode can then **inject the observation file wholesale** for certain agents, mimicking OM’s stable context block.

### 5.4 Associative recall implementation patterns

For Palinode, associative recall can be implemented by augmenting search with **entity/edge tables** and simple spreading activation.

1. **Entity and relation extraction**
   - During consolidation or ingestion, call a small LLM to extract `(subject, predicate, object)` triples and named entities from each memory, and store them in SQLite tables (e.g., `edges(subject, predicate, object, memory_id, created_at)`).[^39][^1]

2. **Spreading activation query**

```sql
-- Seed nodes: entities whose names appear in the current prompt
SELECT DISTINCT entity FROM entities WHERE name IN (:tokens);

-- Step 1: direct neighbors
SELECT DISTINCT e2.entity, e2.memory_id
FROM edges e1
JOIN edges e2 ON e1.object = e2.subject
WHERE e1.subject IN (:seed_entities);

-- Then, in Python, iteratively propagate activation scores over hops with decay
```

3. **Hybrid ranking**
   - Combine activation scores with BM25 + embedding similarity when ranking candidate memories, similar to Synapse’s triple hybrid retrieval (semantic, activation, structural).[^15]

4. **Prospective triggers**
   - Store `intentions` in a table with text + embedding (e.g., "When user mentions LoRA, remind them about curation-over-volume insight").
   - On each new user message, embed it and compute cosine similarity against all intentions; if similarity exceeds a threshold, fetch and inject the corresponding memories and mark the intention as fired or cooldown-limited.[^16][^14]

This yields patterns like:

- "When Peter appears in context, auto-inject his canonical decisions and constraints."
- "When 'LoRA' appears, auto-inject the curation-over-volume insight and most recent experiment results."

### 5.5 Episodic recall: "last time we discussed X"

To support queries like "The last time we discussed X, what did we decide?":

- Maintain an `episodes` table where each row records `episode_id`, `topic_tags`, `start_time`, `end_time`, and `summary_text` pointing back to log file segments.
- When the user asks about X, search `episodes` by FTS and tags, fetch the most recent matching episode, and inject its summary, optionally followed by a link to the underlying log.

This is similar to Zep’s episodic subgraph and CMA’s replay-based consolidation.[^11][^1]

***

## 6. The "Sleeping Brain" Pattern for

---

## References

1. [Zep: A Temporal Knowledge Graph Architecture for Agent Memory](https://arxiv.org/html/2501.13956v1) - The Graphiti KG engine dynamically updates the knowledge graph with new information in a non-lossy m...

2. [Memory-Augmented Transformers: A Systematic Review from ... - arXiv](https://arxiv.org/html/2508.10824v1) - Neural replay during sleep drives consolidation by reactivating patterns of network activity that oc...

3. [Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and ...](https://arxiv.org/html/2603.07670v1) - The paper closes with open challenges: continual consolidation, causally grounded retrieval, trustwo...

4. [Memory Blocks: The Key to Agentic Context Management - Letta](https://www.letta.com/blog/memory-blocks) - Memory blocks offer an elegant abstraction for context window management. By structuring the context...

5. [How to Extract Semantic Memories - LangMem](https://langchain-ai.github.io/langmem/guides/extract_semantic_memories/) - Since we have enabled "deletes", the manager will return RemoveDoc objects to indicate that the memo...

6. [Observational Memory - Mastra Docs](https://mastra.ai/docs/memory/observational-memory) - Observational Memory (OM) is Mastra's memory system for long-context agentic memory. Two background ...

7. [Observational Memory: 95% on LongMemEval - Mastra Research](https://mastra.ai/research/observational-memory) - A Reflector agent restructures and condenses the observations: combining related items, reflecting o...

8. [Evaluating Memory in LLM Agents via Incremental Multi-Turn ... - arXiv](https://arxiv.org/html/2507.05257v2) - (4) Selective Forgetting (SF): The skill to revise, overwrite, or remove previously stored informati...

9. [FadeMem: Why Teaching AI Agents to Forget Makes Them ...](https://www.co-r-e.com/method/agent-memory-forgetting) - FadeMem introduces biologically-inspired memory management for LLM agents, implementing selective fo...

10. [Enhancing memory retrieval in generative agents through LLM ...](https://pmc.ncbi.nlm.nih.gov/articles/PMC12092450/) - Common memory retrieval methods include temporal decay ranking, evaluation of memory importance, vec...

11. [Continuum Memory Architectures for Long-Horizon LLM Agents - arXiv](https://arxiv.org/html/2601.09913v1) - Finally, the architecture must support consolidation and abstraction. Sleep-inspired replay and gist...

12. [memsearch - Zilliz](https://zilliztech.github.io/memsearch/) - Inspired by OpenClaw's memory system, memsearch brings the same markdown-first architecture to a sta...

13. [Sleep-time Compute: Beyond Inference Scaling at Test-time - arXiv](https://arxiv.org/html/2504.13171v1) - We introduce sleep-time compute, which allows models to “think” offline about contexts before querie...

14. [Shodh Memory - The Missing Brain for Stateless LLMs | 37 MCP Tools](https://shodh-rag.com/memory) - Time-based, duration-based, or context-triggered reminders that surface when relevant keywords appea...

15. [Synapse: Empowering LLM Agents with Episodic-Semantic Memory ...](https://arxiv.org/html/2601.02744v3) - Drawing from cognitive science, Synapse models memory as a dynamic graph where relevance emerges fro...

16. [Memory Poisoning in AI: Early-Stage Hallucinations - LinkedIn](https://www.linkedin.com/posts/priyam-tiwari-42b7a5193_ai-llm-developertools-activity-7431915521702531073-DRu1) - The context triggered it automatically. We built this into shodh-memory. You can set an intention wi...

17. [Memory blocks (core memory) - Letta Docs](https://docs.letta.com/guides/core-concepts/memory/memory-blocks/) - Memory blocks are structured sections of the agent's context window that persist across all interact...

18. [MemGPT: Towards LLMs as Operating Systems - Leonie Monigatti](https://www.leoniemonigatti.com/papers/memgpt.html) - A MemGPT agent is an AI agent that follows the design pattern introduced in the research paper with ...

19. [Sleep-time Compute - Letta](https://www.letta.com/blog/sleep-time-compute) - Sleep-time compute is a new way to scale AI capabilities: letting models "think" during downtime. In...

20. [Letta: Building Stateful AI Agents with In-Context Learning ... - ZenML](https://www.zenml.io/llmops-database/building-stateful-ai-agents-with-in-context-learning-and-memory-management) - For example, a memory block might allocate 20,000 characters to storing information about users, wit...

21. [Core memory - Letta Docs](https://docs.letta.com/guides/ade/core-memory/) - Default block length limit: 2,000 characters per block; Customizable: You can adjust limits in the A...

22. [Trigger memory compaction in Letta with Claude Code - LinkedIn](https://www.linkedin.com/posts/letta-ai_you-can-now-manually-trigger-memory-compaction-activity-7336860237909434369-RUgx) - You can now manually trigger memory compaction (summarization) in Letta, and also explicitly view th...

23. [[PDF] MemGPT: Towards LLMs as Operating Systems - arXiv](https://arxiv.org/pdf/2310.08560.pdf) - Awareness of context limits is a key aspect in making the self-editing mechanism work effectively, t...

24. [Sleep-time agents - Letta Docs](https://docs.letta.com/guides/agents/architectures/sleeptime/) - In Letta, you can create special sleep-time agents that share the memory of your primary agents, but...

25. [Agent Memory: How to Build Agents that Learn and Remember - Letta](https://www.letta.com/blog/agent-memory) - The sleep-time compute paradigm introduces several key improvements to the agent design from the ori...

26. [Understanding LangMem's Long-Term Memory: Overview and Usage](https://developer.mamezou-tech.com/en/blogs/2025/02/26/langmem-intro/) - LangMem is an SDK that enables AI agents to manage long-term memory. Long-term memory complements sh...

27. [Long-term Memory in LLM Applications](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/) - LangMem uses a memory enrichment process that strives to balance memory creation and consolidation, ...

28. [Zilliz Open-Sources Memsearch, Giving AI Agents Persistent ...](https://www.prnewswire.com/news-releases/zilliz-open-sources-memsearch-giving-ai-agents-persistent-human-readable-memory-302711968.html) - New open-source library lets developers give any AI agent long-term memory that humans can read, edi...

29. [Zilliz Open-Sources Memsearch, Giving AI Agents Persistent ...](https://technode.global/prnasia/zilliz-open-sources-memsearch-giving-ai-agents-persistent-human-readable-memory-2/) - New open-source library lets developers give any AI agent long-term memory that humans can read, edi...

30. [zilliztech/memsearch: A Markdown-first memory system, a ... - GitHub](https://github.com/zilliztech/memsearch) - A Markdown-first memory system, a standalone library for any AI agent. Inspired by OpenClaw. - zilli...

31. [We Extracted OpenClaw's Memory System and Open-Sourced It ...](https://milvus.io/blog/we-extracted-openclaws-memory-system-and-opensourced-it-memsearch.md) - Memsearch simply re-embeds and re-indexes the Markdown files, rebuilding the full retrieval layer in...

32. [Persistent Memory for Claude Code: memsearch ccplugin - Milvus](https://milvus.io/blog/adding-persistent-memory-to-claude-code-with-the-lightweight-memsearch-plugin.md) - To address this, we built a persistent memory plugin designed specifically for Claude Code. It sits ...

33. [Announcing Observational Memory - Mastra Blog](https://mastra.ai/blog/observational-memory) - At Mastra, we just shipped a new type of memory for agentic systems: observational memory. Observati...

34. [Mastra's Observational Memory Boosts AI Performance in Production](https://www.linkedin.com/posts/pholcomb8_observational-memory-activity-7429887815888302080-zJaU) - Mastra's open-source "observational memory" architecture eliminates retrieval entirely. Instead of s...

35. [Your AI Has an Attention Problem. Here's How We Fixed It (using ...](https://gavlahh.substack.com/p/your-ai-has-an-attention-problem) - Every successful agent memory system (Stanford's Generative Agents, MemGPT, Mastra's Observational M...

36. [Zep: Temporal Knowledge Graphs for AI Agent Memory - YouTube](https://www.youtube.com/watch?v=2V-zMRF7lL0) - Zep utilizes Graphiti, a temporally-aware knowledge graph engine, to synthesize both unstructured co...

37. [Zep - Build Agents That Recall What Matters](https://blog.getzep.com) - Graphiti builds dynamic, temporally aware knowledge graphs that represent complex, evolving relation...

38. [Agent memory: Letta vs Mem0 vs Zep vs Cognee - Community](https://forum.letta.com/t/agent-memory-letta-vs-mem0-vs-zep-vs-cognee/88) - This article explains how agent memory works and compares five popular solutions to the problem: Mem...

39. [How Cognee Builds AI Memory Layers with LanceDB](https://lancedb.com/blog/case-study-cognee/) - At the product level, combining Cognee's knowledge graph with LanceDB's vector search has improved r...

40. [From RAG to Graphs: How Cognee is Building Self-Improving AI ...](https://memgraph.com/blog/from-rag-to-graphs-cognee-ai-memory) - RAG systems fail 40% of the time. See how Cognee's memory-first design with knowledge graphs raises ...

41. [A Spotlight on Cognee: the memory engine for AI Agents - gdotv](https://gdotv.com/blog/cognee-graphs-that-learn/) - We'll create a sample knowledge graph, then see how we can perform a few sample queries and explore ...

42. [Temporal Cognification: Time-Aware AI Memory for LLMs - Cognee](https://www.cognee.ai/blog/cognee-news/unlock-your-llm-s-time-awareness-introducing-temporal-cognification) - Temporal cognification brings time-awareness to AI memory, enabling LLMs to understand when events h...

43. [How I Built a Personal AI Assistant with Mastra - Damian Galarza](https://www.damiangalarza.com/posts/2026-03-06-build-personal-ai-assistant/) - Observational memory uses background Observer and Reflector agents to maintain a dense observation l...

44. [[PDF] EVALUATING MEMORY IN LLM AGENTS VIA INCRE](https://cseweb.ucsd.edu/~jmcauley/reviews/iclr26c.pdf) - However, weaknesses include concerns about the Selective Forgetting task appearing somewhat artifici...

45. [A Cognitive Memory Architecture and Benchmark for Privacy‑Aware ...](https://arxiv.org/html/2512.12856v1) - Algorithmically, we design and analyze a family of forgetting policies, including reflection‑based c...

46. [Selective Forgetting in Machine Learning and Beyond: A Survey](https://dl.acm.org/doi/10.1145/3796542) - The survey synthesizes theoretical foundations from diverse fields to establish design principles fo...

47. [[PDF] Learning to Forget: Sleep-Inspired Memory Consolidation for ...](https://arxiv.org/pdf/2603.14517.pdf) - Biological brains face an analogous challenge and resolve it through sleep-dependent memory consolid...

48. [SYNAPSE: Empowering LLM Agents with Episodic-Semantic ...](https://alphaxiv.org/overview/2601.02744v1) - The core innovation lies in SYNAPSE's implementation of spreading activation, a principle from cogni...

49. [Enhancing memory retrieval in generative agents through LLM ...](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2025.1591618/full) - Common memory retrieval methods include temporal decay ranking, evaluation of memory importance, vec...

50. [[PDF] Enhancing Temporal Memory Retrieval in Large Language Models ...](https://aclanthology.org/2025.findings-acl.1048.pdf) - The memory management parameters include cosine similarity threshold costh = 0.262 and temporal deca...

51. [Persistent Memory in LLM Agents - Emergent Mind](https://www.emergentmind.com/topics/persistent-memory-for-llm-agents) - Persistent memory for LLM agents is a structured framework that enables long-term retention, dynamic...

52. [Governing Evolving Memory in LLM Agents: Risks, Mechanisms ...](https://arxiv.org/html/2603.11768v1) - SSGM decouples memory evolution from execution by enforcing consistency verification, temporal decay...

53. [Letta's next phase](https://www.letta.com/blog/our-next-phase) - Memory Blocks: The Key to Agentic Context Management. Memory blocks offer an elegant abstraction for...

54. [Memora: A Harmonic Memory Representation Balancing Abstraction ...](https://chatpaper.com/chatpaper/paper/233389) - ... manage memory consumption effectively. On which ... Memory Systems: Includes Zep, Mem0, LangMem ...

