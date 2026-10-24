# Implementation Status

Single source of truth for what works, what does not, and what is next.
Last updated: 2026-10-24 (end of Phase 3).

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

## Phase 2 — Memory & Knowledge (RAG): ✅ COMPLETE

### Completed features (on top of Phase 1)

**Long-term memory**
- `memories` table (owner + optional agent scope, categories, source metadata).
- Explicit CRUD API + Memory page (add/list/delete, agent scoping).
- Agent tools `save_memory` / `recall_memory` (async, run-scoped, refuse bad
  categories, prompted not to store secrets).
- `memory_enabled` agents: stored memories appended to the system prompt
  (capped, labeled section) before graph build.

**Knowledge bases / RAG**
- `knowledge_bases` / `knowledge_documents` / `document_chunks` tables.
- Upload API: type whitelist (PDF/TXT/MD), size cap, background ingestion with
  visible statuses (pending/processing/ready/failed + error text).
- Parsing (pypdf + text), paragraph-aware chunking (1200/180 overlap).
- Embedding abstraction: OpenAI `text-embedding-3-small` when keyed;
  deterministic local token-hash provider for offline/tests (keyword-grade,
  honestly labeled).
- Retrieval: cosine in SQLite, owner-scoped SQL filtering, `[filename#chunk]`
  citations with scores; honest empty results (no fabricated sources).
- `knowledge_search` agent tool; agent ↔ KB attachment (`knowledge_base_ids`).
- Frontend: Knowledge page (KB create/delete, upload with picker, status
  polling, document delete), Memory page, agent studio KB chips + memory
  toggle; fake provider exercises knowledge_search for keyless demos.

### Tests executed (last run)

- `uv run pytest -q` → **51 passed** (34 Phase-1 + 17 memory/knowledge:
  CRUD & cross-user isolation, ingestion ready/failed paths, bad-type
  rejection, exact-term retrieval quality + no-source behavior, direct tool
  invocation with citations, embedding sanity, chunking).
- `ruff check` / `mypy app` → clean; `npm run build` → clean.
- Browser E2E: KB created, document uploaded (ready, 1 chunk), Docs Assistant
  with attached KB answered "refund deadline" from the document with
  `[aurora.txt#chunk0]` citation; memory saved via UI.

### New known limitations

- Embedding quality without an OpenAI key is keyword-grade (by design);
  swap providers via `EMBEDDING` seam when needed.
- Ingestion runs as an in-process background task; a crash mid-ingest leaves
  the document failed (re-upload needed) — no durable job queue yet.
- Vector search is Python cosine over SQLite JSON (fine ≤ tens of thousands
  of chunks); Qdrant adapter later.

## Phase 3 — Multi-Agent: ✅ COMPLETE

- `agents.delegation_targets` (own agents only; self/foreign/unknown ids
  rejected with 422) + Alembic migration.
- Runner resolves targets into typed Deep Agents `SubAgent` declarations:
  the specialist keeps its own model (falls back to parent's if its provider
  is unconfigured), tools, system prompt and knowledge bases; depth is 1 by
  construction (subagents never get the `task` tool — no runtime cycles).
- Stale/deleted targets skipped safely at run time.
- Fake provider exercises the real `task()` path for keyless demos/tests.
- Agent Studio: "Can delegate to" chips.
- Tests: full coordinator→specialist→calculator flow over SSE (events,
  transcript, trace), target validation, deleted-target safety, spec
  resolution. **55 backend tests green**; browser-verified delegation flow.

Known limitation: run usage counts the parent graph's model calls only —
subagent turns are not yet aggregated (documented in 09-multi-agent).

## Phase 4 — Integrations & Automation: ⬜ NOT STARTED

MCP client + per-agent tool allowlists, APScheduler-based automations
running through the same execution service, Telegram integration,
permissions UI.

## Phase 5 — Production Hardening: ⬜ NOT STARTED

PostgreSQL + Qdrant adapters, encrypted-at-rest provider keys, Langfuse/OTel
observability, CI/CD (GitHub Actions), health/readiness probes beyond
`/api/health`, load/failure testing, structured request ids in logs.

## Next steps (suggested order)

1. Phase 4 — MCP client (external tool servers, per-agent allowlists) and
   scheduler (APcheduler jobs through the same execution service).
2. Subagent usage aggregation + `subgraphs=True` inner-tool streaming.
3. Checkpoint GC for deleted conversations + failed-ingestion retry (small).
4. GitHub Actions workflow running the existing test/lint/typecheck matrix.
