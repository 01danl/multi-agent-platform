# Implementation Status

Single source of truth for what works, what does not, and what is next.
Last updated: 2026-10-24 (end of Phase 1).

## Phase 1 — Working AI chat platform: ✅ COMPLETE

### Completed features

**Backend (FastAPI, Python 3.12, uv)**
- Project scaffolding, pinned dependency set (deepagents 0.7.x, langgraph 1.2.x,
  langchain-openai, SQLAlchemy 2 async, Alembic, pydantic-settings).
- Auth: register/login/logout/me; scrypt password hashing; sessions stored
  hashed with expiry; HttpOnly cookies.
- Agent CRUD with ownership isolation; provider validation.
- Provider manager: OpenAI, OpenRouter, custom OpenAI-compatible endpoint,
  env-only credentials, optional deterministic `fake` provider
  (`FAKE_PROVIDER_ENABLED=true`).
- Harness: `AgentRunner` over `create_deep_agent` — per-run graph build,
  `ModelCallLimitMiddleware`, recursion + wall-clock limits, `AsyncSqliteSaver`
  checkpointer (thread per conversation).
- Tool registry: `calculator` (AST-whitelisted, DoS-guarded), `current_datetime`
  (IANA tz, UTC fallback).
- Streaming: SSE endpoint adapting LangGraph `messages`/`updates` modes into
  the platform event schema; cancellation via `RunTaskRegistry` (endpoint or
  disconnect); one active run per conversation (409).
- Persistence: platform DB (users/sessions/agents/conversations/messages/
  runs/run_events) + separate checkpointer DB; Alembic migration; migrations
  on startup; SQLite FK pragma; startup sweep of orphaned `running` runs.
- Execution inspector API: run list/detail with event timeline, cancel.

**Frontend (React + TypeScript + Vite + Tailwind v4)**
- Auth page (login/register), protected routes, auth context.
- App layout: sidebar with Workspace/Developer/Settings groups, future
  features marked "soon" (not dead buttons), dark/light theme toggle.
- Chat: conversation sidebar (create/rename/delete), agent picker, real SSE
  token streaming, inline tool-call blocks (running/done/failed), stop
  generation, markdown + syntax highlighting + copy, usage in header,
  auto-scroll with unpin.
- Agent studio: list, create/edit (name, description, system prompt, provider,
  model with suggestions, temperature, max output tokens, tool toggles),
  delete, "chat now".
- Execution logs: run list with status/usage/duration; run detail with stats
  and expandable event timeline.
- Tools catalog and Providers status pages.

**Infrastructure**
- Docker: multi-stage backend (uv) and frontend (nginx with SSE-friendly
  proxy) images; `docker compose up --build` verified end-to-end (register →
  agent → SSE chat with tool call through nginx).
- Makefile (dev/test/lint/typecheck/build/migrate/docker), `.env.example`,
  MIT license.

### Tests executed (last run)

- `uv run pytest -q` → **34 passed** (auth flows, agent CRUD + cross-user
  isolation, tool safety incl. DoS regressions, provider manager, SSE
  end-to-end with tool calls, transcript/run persistence, conversation
  continuation, cancellation contract, unconfigured-provider failure).
- `uv run ruff check app tests` → clean; `uv run mypy app` → clean.
- `npm run build` (tsc -b + vite) → clean.
- Manual browser E2E (in-app browser): register → create agent → chat with
  streaming + tool call → runs inspector → theme toggle. Screenshot-verified
  layout.
- Docker compose E2E over nginx (ports 8080/8100) including SSE.

### Known problems / limitations

- Single-process: cancellation only reaches runs started by the same process;
  one active run per conversation.
- Checkpoints for deleted conversations are not garbage-collected (small
  file growth).
- Real-provider integration (OpenAI/OpenRouter) shares the tested
  `ChatOpenAI` code path but has not been run against a paid API in this
  environment; the fake provider covers execution machinery.
- No SSE heartbeat (documented); long silent provider gaps are bounded by
  RUN_TIMEOUT_SECONDS.
- `frontend/dist` JS bundle ~665 kB (code-splitting is future polish).
- Registration has no rate limiting / CAPTCHA (self-hosted MVP scope).

## Phase 2 — Memory & Knowledge (RAG): ⬜ NOT STARTED

Long-term memory store, workspace files, document upload (PDF/TXT/MD),
chunking, embeddings, vector retrieval, knowledge base management, RAG tool
with source citations, cross-user isolation tests. Short-term memory already
exists via the checkpointer (see docs/architecture/07-memory-system.md).

## Phase 3 — Multi-Agent: ⬜ NOT STARTED

Specialized agents, coordinator + `SubAgent` declarations, parallel
delegation, depth/duration limits, subagent event streaming
(`subgraphs=True`).

## Phase 4 — Integrations & Automation: ⬜ NOT STARTED

MCP client + per-agent tool allowlists, APScheduler-based automations
running through the same execution service, Telegram integration,
permissions UI.

## Phase 5 — Production Hardening: ⬜ NOT STARTED

PostgreSQL + Qdrant adapters, encrypted-at-rest provider keys, Langfuse/OTel
observability, CI/CD (GitHub Actions), health/readiness probes beyond
`/api/health`, load/failure testing, structured request ids in logs.

## Next steps (suggested order)

1. Checkpoint GC for deleted conversations (small, closes a known gap).
2. Phase 2 spike: memory store schema + RAG ingestion pipeline behind the
   existing `ToolContext` seam.
3. Frontend code-splitting + keyboard shortcuts polish.
4. GitHub Actions workflow running the existing test/lint/typecheck matrix.
