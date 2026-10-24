# 04 — LangGraph / Deep Agents Integration

## Why frameworks instead of a custom loop

The platform's core decision: the tool-calling loop, state management,
checkpointing, and subagent mechanics are solved problems in
Deep Agents/LangGraph. A hand-rolled `while tool_calls:` loop would
re-implement streaming, retries, state schemas, and interrupt handling with
no advantage. The installed versions are pinned in `backend/uv.lock`
(deepagents 0.7.x, langgraph 1.2.x, langchain-core 1.x); signatures below
were verified against the installed packages, not memory.

## What we use

```python
graph = create_deep_agent(
    model=<ChatOpenAI | fake>,              # built by ModelProviderManager
    tools=[...],                            # built by ToolRegistry
    system_prompt=agent.system_prompt,
    middleware=[ModelCallLimitMiddleware(run_limit=...)],
    checkpointer=AsyncSqliteSaver(...),     # shared across runs
)
```

`create_deep_agent` returns a `CompiledStateGraph`. We invoke it with:

```python
config = {
    "configurable": {"thread_id": f"conv:{conversation_id}"},
    "recursion_limit": settings.graph_recursion_limit,
}
graph.astream({"messages": [("user", text)]}, config=config,
              stream_mode=["messages", "updates"])
```

- **thread_id = conversation id** — one checkpoint thread per conversation;
   state survives restarts, giving short-term memory for free (see
   07-memory-system.md).
- **Checkpointer** — `AsyncSqliteSaver` in a dedicated SQLite file, opened
  once in the app lifespan and shared by all runs.
- **Middleware** — only `ModelCallLimitMiddleware` today; Deep Agents already
  provides its middleware stack (summarization, subagents, filesystem-backed
  state tools). We add platform concerns, not duplicates.

## Stream shapes we adapt from

Verified against the installed version with a tool-calling fake model:

- `messages` mode yields `(message_or_chunk, metadata)`:
  - `AIMessageChunk` with text content → token deltas (content may be a
    string or content blocks; we extract text).
  - tool calls arrive as `tool_call_chunks` (name/id first) on real
    providers, or as complete `tool_calls` on fakes — both paths emit
    `tool_started` (deduplicated by call id).
  - `ToolMessage` → `tool_completed` / `tool_failed` (status field).
- `updates` mode yields `{node_name: {"messages": [...]}}` with **final**
  AIMessage objects (authoritative content, `tool_calls`, `usage_metadata`)
  and ToolMessages — this is what we persist and where usage is counted.
  Node names include middleware-generated nodes; the adapter scans
  generically for `messages` keys instead of matching node names.

Subagent events (the built-in `task` tool) appear as ordinary tool calls at
the main-agent level with `subgraphs=False`. Phase 3 will stream subagent
internals via `subgraphs=True` + namespace routing.

## What we deliberately do NOT use yet

- `interrupt_on` / human-in-the-loop (no UI for it).
- `response_format` structured outputs.
- Custom `SubAgent` definitions (Phase 3).
- `store` cross-thread memory (Phase 2 long-term memory will evaluate it).

## Failure modes

| Framework behavior | Platform handling |
|---|---|
| `GraphRecursionError` | mapped to `run_limit_exceeded` |
| Provider exceptions (RateLimitError, APITimeoutError, ...) | matched by class name → structured codes |
| Checkpointer lock/corruption | run fails with `run_error`; transcript rows already persisted stay |
| Unparseable tool arguments | framework surfaces a failed ToolMessage → `tool_failed` event |
