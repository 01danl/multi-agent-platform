# 01 — System Overview

## What this project is

AI Agent Platform is a self-hosted, multi-tenant web application for creating,
configuring, running, and inspecting LLM-powered agents. Users register, create
agents (system prompt, model, tools), chat with them over Server-Sent Events,
and inspect every execution (model calls, tool calls, token usage, errors).

The defining architectural decision: **we do not implement an agent execution
engine**. Execution mechanics (graph execution, tool-calling loops, streaming,
checkpointing, subagents) come from the framework stack:

| Layer | Technology (pinned in `backend/uv.lock`) | Responsibility |
|---|---|---|
| Platform services | FastAPI, SQLAlchemy 2 async, Alembic | Auth, CRUD, conversations, runs, persistence |
| Custom harness | `app/agents/*` (our code) | Agent lifecycle, provider routing, tool registry, run limits, event adaptation |
| Agent framework | `deepagents` 0.7 | Planning, tools, subagents on top of LangGraph |
| Runtime | `langgraph` 1.2 | Stateful graph execution, checkpointing, streaming |
| Models | `langchain-openai` etc. | OpenAI / OpenRouter / OpenAI-compatible endpoints |

The harness is a thin engineering layer: it translates persisted agent
configuration into a `create_deep_agent(...)` graph per run, adapts framework
stream events into the platform's own event schema, enforces limits, and
records executions.

## Topology

A modular monolith: one backend process, one frontend SPA, one SQLite database
(dev) or PostgreSQL (production, later), one checkpointer database, local file
storage. No message brokers, no microservices.

```text
React SPA (Vite, TS, Tailwind)
        |  REST + SSE (cookie session)
        v
FastAPI API layer  (app/api/*)          — HTTP boundary, validation, auth
        |
Application services (app/agents, app/conversations, ...)
        |                        |
        v                        v
Agent harness               DB layer (app/db)
  AgentManager                repositories, models
  ModelProviderManager        SQLAlchemy async
  ToolRegistry
  AgentRunner  -----------------------> LangGraph AsyncSqliteSaver (checkpoints)
        |
        v
  deepagents create_deep_agent() -> CompiledStateGraph
        |
        v
  ChatOpenAI (OpenAI / OpenRouter / custom base URL) + platform tools
```

## Source-of-truth split

- **Relational DB** (`app.db`): users, sessions, agent configs, conversations,
  messages, runs, run events. Everything the UI lists and edits.
- **LangGraph checkpointer** (separate SQLite file): raw execution state per
  thread (message history as the graph sees it, incl. tool-call internals).
  Enables conversation continuation across restarts.
- Both stores coexist deliberately: the checkpointer is opaque framework state;
  the relational `messages` table is the platform's canonical, inspectable
  transcript. The runner writes transcript rows while streaming events.

## Key design rules

1. API routes never orchestrate agents directly; they call services.
2. DB models never leak into the runtime; the harness receives plain data.
3. Secrets (provider API keys) live only in server env vars, never in the DB,
   never in responses or logs.
4. Every execution produces an `agent_runs` row plus `run_events` rows —
   observability is a first-class feature, not a bolt-on.
5. Failures are structured: platform error schema (`code`, `message`) with
   internal detail kept server-side.

## Phasing

- **Phase 1 (this codebase state)**: auth, agents CRUD, providers, real chat
  with streaming, tool calling, conversation persistence, execution inspector,
  Docker.
- Later phases (memory/RAG, multi-agent delegation, MCP, scheduler) extend the
  harness without replacing it. See `docs/implementation-status.md` for the
  current state — it is the single source of truth for what works.
