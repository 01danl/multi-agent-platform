# AI Agent Platform

A self-hosted platform for creating, running, and inspecting LLM agents.
Users register, configure agents (system prompt, model, tools), chat with them
over a streaming interface, and audit every execution.

Execution is built on **Deep Agents + LangGraph** (not a hand-rolled agent
loop): the platform contributes the harness around them — persistence, auth,
provider routing, tool registry, limits, and observability.

## Status

**Phase 1 complete** — working AI chat platform with streaming, tool calling,
persistent conversations, and an execution inspector. See
[docs/implementation-status.md](docs/implementation-status.md) for exactly
what works and what is planned (memory/RAG, multi-agent, MCP, scheduler).

## Quick start (Docker)

```bash
cp .env.example .env          # add at least one provider API key
docker compose up --build -d
open http://localhost:8080
```

No key handy? Set `FAKE_PROVIDER_ENABLED=true` in `.env` for a deterministic
provider that exercises the full stack without external calls (not for
production).

## Quick start (local dev)

Requirements: Python 3.12+ ([uv](https://docs.astral.sh/uv/)), Node 18+.

```bash
# Backend (FastAPI on :8100, SQLite, auto-migrations on startup)
cd backend
uv sync
cp ../.env.example .env      # optional: keys for real providers
uv run uvicorn app.main:app --reload --port 8100

# Frontend (Vite on :5173, proxies /api to :8100)
cd frontend
npm ci
npm run dev
```

Or via make: `make dev-backend` / `make dev-frontend` / `make test`.

## What works today

- **Auth** — register/login/logout with scrypt password hashing and hashed
  session tokens in HttpOnly cookies.
- **Agent studio** — create/edit agents: system prompt, provider, model,
  temperature, output-token cap, per-agent tool toggles.
- **Providers** — OpenAI, OpenRouter, any OpenAI-compatible endpoint
  (credentials are env-only, never persisted or exposed), plus an optional
  deterministic fake provider for tests/demos.
- **Chat** — real SSE streaming: token deltas, live tool-call status, stop
  generation, markdown with syntax highlighting, copy, usage per run.
- **Tools** — `calculator` (safe AST evaluation, DoS-guarded) and
  `current_datetime`; failures surface in the trace.
- **Persistence** — conversations survive restarts (SQLite + LangGraph
  checkpointer in a separate database).
- **Execution inspector** — every run with status, duration, token usage, and
  an expandable event timeline (model calls, tool calls, failures).
- **Multi-user** — agents, conversations, and runs are strictly isolated per
  owner (covered by tests).

## Verification

```bash
make test        # backend: 34 tests (unit + SSE end-to-end with fake provider)
make lint        # ruff + frontend lint
make typecheck   # mypy + tsc
```

Agent execution tests run the real deepagents/LangGraph machinery against a
deterministic fake model — CI needs no paid API calls.

## Architecture

Modular monolith: FastAPI backend, React SPA, SQLite (PostgreSQL adapter
later). Full docs in [docs/architecture/](docs/architecture/):

- [01 System overview](docs/architecture/01-system-overview.md)
- [02 Backend architecture](docs/architecture/02-backend-architecture.md)
- [03 Agent harness](docs/architecture/03-agent-harness.md)
- [04 LangGraph / Deep Agents integration](docs/architecture/04-langgraph-deepagents.md)
- [05 Request lifecycle](docs/architecture/05-request-lifecycle.md)
- [06 Tool execution](docs/architecture/06-tool-execution.md)
- [10 Database design](docs/architecture/10-database-design.md)
- [11 Streaming](docs/architecture/11-streaming.md)
- [12 Security](docs/architecture/12-security.md)
- [13 Error handling](docs/architecture/13-error-handling.md)
- [14 Design decisions](docs/architecture/14-design-decisions.md)

## Configuration

All settings are environment-driven — see [.env.example](.env.example):
provider keys, model catalogs, run limits (`MAX_MODEL_CALLS_PER_RUN`,
`RUN_TIMEOUT_SECONDS`), storage paths, CORS origins.

## Known limitations (Phase 1)

- Single process: one active run per conversation; cancellation works only
  against the process that started the run. Runs interrupted by a restart are
  marked `failed(server_restarted)`.
- SQLite only (fine for a small self-hosted install); PostgreSQL/Qdrant
  adapters are Phase 5.
- Scheduling, MCP, knowledge bases, and subagent delegation are not
  implemented yet (Phases 2–4).
- Real-provider integration (OpenAI/OpenRouter) is exercised through the same
  `ChatOpenAI` path as tests but has not been verified against a paid account
  in CI; the fake provider covers the execution machinery.

## License

[MIT](LICENSE)
