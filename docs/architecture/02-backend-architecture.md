# 02 — Backend Architecture

## Layout

```text
backend/app/
├── main.py               App factory + lifespan (engine, migrations, checkpointer, harness)
├── config.py             pydantic-settings; every knob is env-driven
├── api/                  HTTP boundary only — no business logic
│   ├── deps.py           Auth/session/ownership dependencies
│   ├── schemas.py        Request/response models (Pydantic v2)
│   ├── auth.py           register / login / logout / me
│   ├── agents.py         Agent CRUD
│   ├── conversations.py  Conversations + SSE chat endpoint
│   ├── runs.py           Execution inspector + cancel
│   └── meta.py           Tools catalog, provider status, health
├── agents/               The harness (see 03-agent-harness.md)
│   ├── providers.py      ModelProviderManager
│   ├── tools.py          ToolRegistry + built-ins
│   ├── runner.py         AgentRunner (deepagents + event adaptation)
│   ├── events.py         Platform event schema
│   ├── runs.py           RunTaskRegistry (cancel support)
│   └── fake_model.py     Deterministic provider for tests/demos
├── db/
│   ├── models.py         SQLAlchemy 2.0 models
│   └── session.py        Engine + session factory (SQLite FK pragma)
└── security/
    ├── passwords.py      scrypt hashing (stdlib)
    └── sessions.py       Token generation + SHA-256-at-rest
```

## Dependency rules

1. `api/*` may import services (`agents/*`, `db/*`) — never the reverse.
2. The harness (`agents/runner.py`) receives **plain data**
   (`AgentRuntimeConfig`, ids) and owns its own DB session. ORM objects never
   cross session boundaries — this was a real bug class early on (runs stuck
   in `running`).
3. Framework imports (`deepagents`, `langgraph`, `langchain_*`) live only in
   the harness; swapping the execution framework would not touch `api/` or
   `db/`.

## Request flow (non-streaming)

Routes validate input via Pydantic, resolve dependencies (`CurrentUser`,
ownership-scoped entity), call services or repositories directly for CRUD,
and return schema-serialized ORM objects. Mutating endpoints call
`db.refresh()` before returning so server-side defaults (`updated_at`) are
loaded eagerly — async SQLAlchemy lazy loads raise `MissingGreenlet`.

## Lifespan

`app/main.py` owns process-wide state on startup:

1. `data/` dirs ensured, Alembic `upgrade head` (in a worker thread — Alembic's
   async template calls `asyncio.run()`).
2. Async engine + session factory; stale `running` runs marked
   `failed(server_restarted)` (single-process honesty).
3. `AsyncSqliteSaver` checkpointer opened; harness singletons attached to
   `app.state`.

## Sessions and auth

- Cookie `aap_session` carries a 32-byte random token; the DB stores only its
  SHA-256 hash with an expiry. Logout deletes the row; expiry is checked on
  every request.
- Passwords: stdlib scrypt (`n=2^14, r=8, p=1`) with per-user salt,
  constant-time comparison.
- Ownership: every entity query filters by `owner_id`; foreign users get 404
  (not 403) to avoid existence leaks.

## Testing strategy

- Session-scoped app + lifespan on a **single shared event loop** —
  cross-loop access to aiosqlite/checkpointer objects caused real hangs until
  `asyncio_default_*_loop_scope = "session"` was set.
- Each test user gets a fresh `AsyncClient` (own cookie jar) so ownership
  tests are exact.
- The fake provider makes SSE tests deterministic: `2+2`-style inputs produce
  a scripted tool call → answer sequence through the real deepagents graph.

## Failure scenarios

| Failure | Behavior |
|---|---|
| DB locked (SQLite) | 30s busy timeout via connect args; short transactions |
| Migration fails on startup | Logged, app continues if tables exist |
| Provider key missing | Run fails `provider_not_configured` — surfaced in UI |
| Client disconnect mid-SSE | Response generator cancels the run task → status `cancelled` |
| Process restart mid-run | Startup cleanup marks run `failed(server_restarted)` |
