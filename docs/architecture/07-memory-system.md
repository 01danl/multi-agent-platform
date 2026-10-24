# 07 — Memory System

## Short-term memory — implemented (Phase 1)

Conversation state persistence uses the framework's checkpointing, not a
custom message store:

- **Thread per conversation**: `thread_id = conv:{conversation_id}` passed in
  the LangGraph config; the `AsyncSqliteSaver` checkpointer (dedicated SQLite
  database, opened in the app lifespan) stores the full graph state after
  every step.
- **Continuation**: each new message resumes the same thread — the model sees
  the prior turns (including tool calls/results) automatically. Verified by
  tests (`test_chat_conversation_continues`) and by chatting across backend
  restarts.
- **Isolation**: threads are keyed by conversation UUID, which is owned and
  authorized per user — one user's threads are unreachable from another
  user's conversations.
- **Lifecycle**: deleting a conversation cascades the platform rows; the
  checkpoint blob for its thread becomes unreachable garbage. A checkpoint
  GC for deleted conversations is **not implemented** (small file growth,
  noted in implementation-status).

## Long-term memory — not implemented (Phase 2)

Planned shape (design notes, code does not exist yet):

- Separate `memories` store with ownership, source metadata (which
  conversation/run produced it), categories (preference / project fact /
  saved note), and explicit create/delete API + UI.
- Injection into runs via system-prompt assembly or a `recall` tool scoped by
  `ToolContext.user_id`.
- **No automatic capture** of every message (privacy + noise); extraction
  will be an explicit, inspectable step when added.
- Evaluation of LangGraph `store` (cross-thread KV) vs a platform table is
  part of the Phase 2 spike; the harness boundary (`AgentRuntimeConfig`) is
  where the choice will land.
