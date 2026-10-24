# 07 — Memory System

## Short-term memory — conversation state (Phase 1)

Uses the framework's checkpointing, not a custom message store:

- **Thread per conversation**: `thread_id = conv:{conversation_id}` in the
  LangGraph config; the `AsyncSqliteSaver` checkpointer (dedicated SQLite
  database, opened in the app lifespan) stores the full graph state after
  every step.
- **Continuation**: each new message resumes the same thread — the model sees
  prior turns (including tool calls/results) automatically. Covered by
  `test_chat_conversation_continues` and used across restarts.
- **Isolation**: threads are keyed by conversation UUID, owned and authorized
  per user.
- **Lifecycle**: deleting a conversation cascades the platform rows; the
  checkpoint blob becomes unreachable (no GC yet — known gap, see
  implementation-status).

## Long-term memory — implemented (Phase 2)

Nothing is captured automatically; every row has an explicit origin.

### Storage

`memories` table: `owner_id` (required), `agent_id` (NULL = visible to all
the owner's agents), `category` (`preference|project|fact`), `content`,
`source` (`manual|agent`), `conversation_id` (when an agent saved it during a
run), `created_at`. Ownership is enforced on every query (cross-user 404s
covered by tests).

### Access paths

| Path | What happens |
|---|---|
| REST `POST/GET/DELETE /api/memories` | explicit user management (Memory page) |
| `save_memory` tool | agent saves a fact during a run (source=agent, conversation linked); refuses unknown categories; prompt instructs not to store secrets |
| `recall_memory` tool | keyword-overlap retrieval over the agent-visible set (own + owner-global), deterministic and tested |
| `memory_enabled` agents | `AgentRunner._effective_config` appends a "Stored memories" preamble (≤50 rows) to the system prompt before building the graph |

### Runner integration

Memories load through the `MemoryStore` in the runner's own session before
`create_deep_agent`; the composed prompt is a frozen-dataclass replace on
`AgentRuntimeConfig`, keeping persistence and runtime separate.

### Design decisions

- **Keyword recall first** (token overlap + recency): deterministic, offline,
  honest about being non-semantic. The `MemoryStore` interface is the seam
  for embedding-based recall later.
- **Prompt injection vs tool-only**: both. Injection makes memories actually
  influence answers without an extra tool round-trip; the tools cover
  interactive save/recall. The preamble is capped and labeled so the model
  treats it as context, not commands (prompt injection is not "solved" —
  users curate their own memories here).
- **What is deliberately absent**: automatic extraction of memories from
  conversations, memory editing by the agent, semantic deduplication.
