# 11 — Streaming

Real streaming end-to-end: the provider's tokens reach the browser as they
are produced; nothing is buffered whole and split.

## Event schema (`agents/events.py`)

Platform-owned, renderer-independent:

| Event | Payload | Emitted when |
|---|---|---|
| `run_started` | run_id, agent_id | run task starts |
| `assistant_delta` | delta (text token/block) | each AIMessageChunk with text |
| `assistant_message` | content, tool_calls | final AIMessage persisted |
| `tool_started` | tool_call_id, name | tool call announced (chunks or complete) |
| `tool_completed` | tool_call_id, name, output, node | ToolMessage success |
| `tool_failed` | tool_call_id, name, error | ToolMessage error |
| `usage` | input/output/total tokens, model_calls | before completion if any model calls |
| `run_completed` | run_id, duration_ms, usage | successful finish |
| `run_failed` | run_id, code, message | classified failure |
| `error` | code, message | transport-level problems |

## Pipeline

```text
LangGraph astream(messages+updates)
   → AgentRunner adaptation (dedupe tool ids, extract text, aggregate usage)
   → PlatformEvent
   → asyncio.Queue            (decouples framework streaming from HTTP)
   → StreamingResponse SSE    (event: <type>\ndata: <json>\n\n)
   → fetch POST + ReadableStream reader in the browser (EventSource can't POST)
   → React state (deltas, live tool blocks, usage)
```

The queue exists so that **cancellation** has one path: client disconnect
(response generator closed) and `POST /api/runs/{id}/cancel` both cancel the
single `_drive` task; the runner's `CancelledError` handler finalizes the run
as `cancelled` and the already-persisted partial transcript stays.

## Delivery guarantees

- Events are ordered as produced; deltas are cumulative-safe (the frontend
  appends, then replaces the live view with the refetched persisted transcript
  — no duplication after completion).
- Tool ids deduplicated across `messages` and `updates` modes.
- On disconnect the HTTP side stops immediately; the DB keeps exactly what
  was persisted before the cancel.

## Transport notes

- Dev: Vite proxies `/api` to :8100. Docker/prod: nginx config disables
  buffering and raises read timeouts for SSE (`docker/nginx.conf`).
- SSE heartbeats are not implemented; token deltas and tool events keep the
  connection visibly active during runs. Long silent gaps are bounded by
  `RUN_TIMEOUT_SECONDS` server-side.

## Frontend behavior

- Streaming state lives in `ChatPage` (`runId`, deltas buffer, live tool
  list, usage, error); after `run_completed` the conversation query is
  invalidated and the live stream state is reset to keep only usage — the
  persisted messages become the single rendered source of truth.
- Stop button → `POST /api/runs/{id}/cancel` + `AbortController.abort()`.
- Auto-scroll pins to bottom unless the user scrolls up (unpin indicator).
