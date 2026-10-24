# 13 — Error Handling

## Principles

1. **Classified, not raw**: every failure the UI can see carries a stable
   machine `code` + a human `message`; stack traces stay in server logs.
2. **Partial results survive**: transcript and trace rows are committed as
   the run progresses, so failures (and cancels) leave an inspectable
   history instead of a black hole.
3. **Honest statuses**: a run is `completed`, `failed`, `cancelled` — never
   left `running` (startup sweep handles orphaned rows).

## Error classification (`agents/runner.py::classify_error`)

Matched by exception class name (providers reuse OpenAI-style names, so no
import-coupling to every SDK):

| Code | Meaning (user-facing) |
|---|---|
| `provider_not_configured` | no API key / base URL on the server |
| `provider_auth_error` | provider rejected the key |
| `provider_rate_limited` | rate limit hit — retry later |
| `provider_timeout` | provider timed out |
| `provider_connection_error` | cannot reach provider |
| `provider_model_not_found` | configured model unknown at provider |
| `provider_bad_request` | provider rejected the request |
| `run_limit_exceeded` | execution step limit (recursion) |
| `run_timeout` | wall-clock limit reached |
| `run_invalid_model_output` | model output not parseable |
| `run_error` | anything else (details in server log) |

## HTTP layer

- Dependency failures (auth, ownership) → 401/404 before any run starts.
- Validation → FastAPI 422 with field details.
- Concurrent run → 409 with explanation.
- Unknown server errors → 500; the global exception path logs ids
  (`request_id` planned with structured-logging hardening).

## SSE layer

`run_failed` / `error` events carry `{code, message}`; the chat UI renders
them inline under the turn. Transport failures (proxy drop, browser offline)
surface as "Connection lost while streaming." — the server side still
finalizes the run independently of what the client saw.

## Frontend

- React Query `retry: 1` for reads; mutations surface `ApiError.message` in
  forms; the chat replaces the live stream with the persisted transcript
  after every run so the UI converges to the DB truth.

## Recovery scenarios (tested or verified)

| Scenario | Result |
|---|---|
| Tool raises | failed ToolMessage → model adapts; `tool_failed` event |
| Provider 401 | `run_failed provider_auth_error`; run row carries code |
| Client disconnect | run `cancelled`, partial transcript kept |
| Server restart mid-run | orphan marked `failed(server_restarted)`; conversation continues from checkpoint |
| DB failure mid-run | run fails; already-committed transcript rows remain |
