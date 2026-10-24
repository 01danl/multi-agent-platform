# 10 — Database Design

## Two databases, two jobs

| Store | File (dev) | Contents | Owner |
|---|---|---|---|
| Platform DB | `data/platform.sqlite` | users, sessions, agents, conversations, messages, runs, run_events | SQLAlchemy models + Alembic migrations |
| Checkpointer DB | `data/checkpoints.sqlite` | LangGraph thread state per conversation (opaque blobs) | framework |

The split is deliberate: the platform's transcript is inspectable,
queryable, and versioned by migrations; the checkpointer is framework-owned
execution state we never read directly. No source of truth is duplicated —
messages are the platform's canonical transcript, checkpoints are how the
*graph* continues.

## Tables

```text
users(id UUID PK, email UNIQUE, name, password_hash, created_at)
sessions(token_hash PK, user_id FK→users CASCADE, created_at, expires_at)
agents(id UUID PK, owner_id FK→users CASCADE, name, description,
       system_prompt, model_provider, model_name, temperature,
       max_output_tokens?, enabled_tools JSON, memory_enabled,
       knowledge_base_ids JSON, created_at, updated_at)
conversations(id UUID PK, owner_id FK, agent_id FK→agents CASCADE,
              title, created_at, updated_at)
messages(id INT PK autoincr, conversation_id FK CASCADE, run_id UUID?,
         role user|assistant|tool, content, tool_calls JSON?,
         tool_call_id?, name?, created_at)
agent_runs(id UUID PK, conversation_id FK, agent_id FK, user_id FK,
           status running|completed|failed|cancelled, error_code?,
           error_message?, input_text, usage JSON?, started_at, finished_at?)
run_events(id INT PK autoincr, run_id FK CASCADE, event_type,
           payload JSON, created_at)
```

Key decisions:

- **Autoincrement integer PKs for `messages`/`run_events`** — free,
  gap-tolerant ordering within a conversation/run; inserts from the streaming
  runner are sequential, so ordering is exact.
- **UUID PKs for entities** referenced across tables and in URLs.
- **`enabled_tools` as JSON list of names** — the ToolRegistry is the only
  component that resolves names to implementations.
- **`usage` JSON** on runs (`input_tokens/output_tokens/total_tokens/
  model_calls`) — aggregated from `usage_metadata` per final AIMessage;
  never fabricated when the provider reports nothing.
- **Session tokens hashed at rest** — a DB leak cannot be replayed.

## Migrations

Alembic (`backend/alembic`), async template, URL taken from app settings so
migrations and runtime always target the same database. Autogenerate against
the models; applied on startup by default (dev) or via `make migrate`.

## SQLite specifics

- `PRAGMA foreign_keys=ON` set per connection in `db/session.py` (SQLite
  defaults to OFF — cascades would silently not fire).
- Relative SQLite URLs are resolved against `backend/` and parent dirs are
  created, so cwd does not matter.
- Single-writer: fine for a small self-hosted instance; PostgreSQL adapter is
  Phase 5 (the code already goes through SQLAlchemy async throughout).

## Lifecycle & isolation

- Deleting an agent cascades to conversations → messages/runs/run_events
  (FK ON DELETE CASCADE + the pragma above).
- Every query for agents/conversations/runs filters by `owner_id`; ownership
  mismatches return 404.
