# 03 — Agent Harness

The harness is the platform's engineering layer around Deep Agents. It owns
everything the framework should not care about: lifecycle, configuration,
provider routing, tools, limits, persistence of transcripts and traces.

## Components

### `ModelProviderManager` (`agents/providers.py`)

Maps an agent's persisted provider/model choice to a `ChatOpenAI` instance:

- `openai` — direct API.
- `openrouter` — same client, `base_url=https://openrouter.ai/api/v1`.
- `custom` — any OpenAI-compatible endpoint (vLLM, LiteLLM, ...).
- `fake` — deterministic in-process model (tests/demos), only when
  `FAKE_PROVIDER_ENABLED=true`.

Credentials come exclusively from environment variables; they are never
persisted, returned by the API, or logged. Providers without keys are listed
in the UI as unconfigured (and the agent editor disables them), and a run
against them fails with `provider_not_configured` rather than crashing.

Not every provider supports every parameter; today we pass only
`temperature` and optional `max_tokens`, which are safe across the
OpenAI-compatible family. Provider-specific capabilities will grow behind
this single choke point.

### `ToolRegistry` (`agents/tools.py`)

Tools are declared once with metadata (`name`, `description`, `category`) and
built per run via a factory receiving a `ToolContext` (user/agent/
conversation/run ids) — future tools (workspace files, knowledge search) will
scope their access through this context instead of trusting model input.

Built-ins: `calculator` (AST-whitelisted arithmetic with exponent/size
guards) and `current_datetime` (IANA timezone-aware, UTC fallback). Unknown
names in an agent's `enabled_tools` are ignored defensively.

### `AgentRunner` (`agents/runner.py`)

The execution entry point. `stream_run()`:

1. Builds a graph per run via `create_deep_agent(model, tools,
   system_prompt, middleware=[ModelCallLimitMiddleware], checkpointer)` —
   building is cheap and keeps configuration fresh; no live agent objects are
   cached or stored (DB stores configuration only).
2. Streams the graph with `stream_mode=["messages", "updates"]` under
   `asyncio.timeout(run_timeout_seconds)` and a recursion limit.
3. Adapts framework events into the platform schema (see 11-streaming.md),
   persisting assistant/tool messages and `run_events` as they complete — a
   cancelled run keeps its partial transcript.
4. Aggregates usage from `usage_metadata` on every final AIMessage.
5. Finalizes the run row (`completed` / `failed` / `cancelled` / timeout) in
   its own DB session.

Limits enforced (defense in depth):

| Limit | Mechanism |
|---|---|
| Model calls per run | `ModelCallLimitMiddleware(run_limit=MAX_MODEL_CALLS_PER_RUN)` |
| Graph steps | LangGraph `recursion_limit` |
| Wall clock | `asyncio.timeout` → `run_timeout` failure |
| Tool input abuse | per-tool validation (e.g. calculator guards) |

### `RunTaskRegistry` (`agents/runs.py`)

In-process map `run_id → asyncio.Task`. `POST /api/runs/{id}/cancel` and
client disconnects converge on `task.cancel()`, which the runner converts into
a `cancelled` finalize. Single-process by design (documented limitation).

## Alternatives & trade-offs

- **Build graph per run vs cache per agent**: cache would go stale on config
  edits and need invalidation; per-run build costs milliseconds and is
  stateless.
- **Own event schema vs raw LangGraph events**: isolates the frontend and the
  API contract from framework changes — the adaptation layer is ~80 lines.
- **One runner DB session per run**: keeps streaming writes independent of
  the request session lifecycle; commits are per-message so partial results
  survive cancellation.
