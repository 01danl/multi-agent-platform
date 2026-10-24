# 14 — Design Decisions

Key trade-offs made in Phase 1, with the reasons and the rejected
alternatives.

## D1. Deep Agents + LangGraph instead of a custom agent loop

**Decision**: use `create_deep_agent` for execution; write only the harness
around it.
**Why**: the tool loop, streaming, state, checkpointing, and (later)
subagents are the hard, well-tested parts. Duplicating them adds bugs, not
features.
**Rejected**: hand-rolled `while tool_calls` executor — precisely what the
project charter forbids; also LangChain `AgentExecutor` (older abstraction,
no native deep-agent features).
**Cost**: coupling to framework stream formats — mitigated by the event
adapter layer (D5).

## D2. Modular monolith, single process

**Decision**: one FastAPI process, no brokers/microservices.
**Why**: a self-hosted platform on a laptop must start with one command;
SQLite + in-process run registry cover Phase 1 loads.
**Consequences**: cancellation only works against the process that started a
run; one active run per conversation. Documented, accepted; multi-worker
deployment (Phase 5) will need an external run registry (e.g. Postgres
advisory locks) — the `RunTaskRegistry` interface isolates that change.

## D3. Two databases (platform + checkpointer)

**Decision**: platform transcript in SQLAlchemy/Alembic-managed SQLite;
LangGraph state in its own `AsyncSqliteSaver` file.
**Why**: the transcript must be queryable/versioned/inspectable; checkpointer
blobs are framework internals. One store doing both would either leak
framework internals into migrations or lose inspectability.
**Rejected**: deriving the UI transcript from checkpoints at read time —
opaque format, no indexes, coupling.

## D4. Graph built per run, config-only persistence

**Decision**: no live agent objects cached; `AgentRuntimeConfig` snapshot →
`create_deep_agent` per run.
**Why**: eliminates cache invalidation on config edit; construction is
cheap; restart-safe by construction; matches "DB stores configuration, never
runtime".
**Rejected**: agent instance cache keyed by config hash — invalidation
subtleties for zero measurable gain at this scale.

## D5. Own SSE event schema

**Decision**: adapt LangGraph stream items into `run_started/assistant_delta/
tool_*/run_*` events.
**Why**: the API contract must survive framework upgrades and the frontend
must not know LangGraph's formats. ~80 lines of adapter buys that.
**Rejected**: forwarding raw `astream_events` — couples every client to the
framework's event churn.

## D6. Queue between runner and SSE response

**Decision**: `_drive` task → `asyncio.Queue` → response generator.
**Why**: client disconnect and explicit cancel converge on one cancellation
path; the runner never blocks on a slow client.
**Rejected**: iterating the runner directly in the response generator —
disconnect handling would be tangled with streaming logic.

## D7. Sessions in DB (hashed) + HttpOnly cookies over JWT

**Decision**: opaque server-side sessions.
**Why**: instant revocation (logout deletes the row), no token-expiry-vs-
revocation dilemma, works naturally with SSE/fetch `credentials: same-origin`.
**Rejected**: stateless JWT — revocation requires a denylist anyway at which
point you've rebuilt sessions with more crypto.

## D8. Env-only provider credentials

**Decision**: keys never enter the DB in Phase 1 (charter's MVP allowance).
**Why**: no at-rest secret management needed yet; zero risk of leaking keys
through API/log surfaces.
**Cost**: per-user keys are impossible until encrypted-at-rest storage lands
(Phase 5: separate key + AES-GCM column encryption is the plan).

## D9. Deterministic fake provider for tests and demos

**Decision**: `fake` provider (env-gated) drives the real graph with
scripted tool calls.
**Why**: CI must not depend on paid APIs, yet must exercise the actual
deepagents execution, streaming adaptation, persistence, and cancellation.
**Rejected**: mocking the graph — would test nothing real.

## D10. SQLite now, PostgreSQL later — behind SQLAlchemy async everywhere

**Decision**: async SQLAlchemy 2.0 + Alembic from day one, SQLite dialect
for dev.
**Why**: local-first (copy a file, back it up with `cp`) while keeping the
production path a config change. FK pragma and path-resolution quirks are
isolated in `db/session.py`/`config.py`.

## D11. Frontend: hand-rolled Tailwind component kit

**Decision**: small `components/ui.tsx` primitives instead of pulling the
full shadcn/ui machinery.
**Why**: the visual surface is small (buttons/inputs/cards/badges); owning
~100 lines keeps the bundle lean and styling exact; swapping in shadcn later
is additive.
**Trade-off**: fewer prebuilt complex widgets (comboboxes, dialogs) — to be
revisited when the UI grows (e.g. knowledge base file management).
