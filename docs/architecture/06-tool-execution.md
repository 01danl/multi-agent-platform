# 06 — Tool Execution

## Registry model

```python
ToolSpec(name, description, category, factory: Callable[[ToolContext], BaseTool])
```

- Registered once at import; exposed via `GET /api/tools` (the agent editor
  lists it).
- Built **per run** by `AgentRunner.build_graph` from
  `AgentRuntimeConfig.enabled_tools` — only names present in the registry are
  instantiated (unknown names ignored, never guessed).
- `ToolContext` carries `user_id / agent_id / conversation_id / run_id`.
  Today's tools don't need it; file/knowledge tools in later phases will
  scope every path and query through it. It is the boundary that keeps tools
  multi-tenant-safe.

## Built-in tools

### `calculator(expression: str) -> str`

Safe arithmetic evaluation — no `eval`:

- Parsed with `ast.parse(mode="eval")`; only `Constant(int|float)`,
  `BinOp`/`UnaryOp` with a whitelist of operators are accepted.
- Denial-of-service guards **before** computing: expression length ≤ 500,
  exponent ≤ 4096, estimated digits ≤ 308. (An early version checked the
  result *after* computing — `9 ** 9 ** 9` then spun a CPU for minutes; the
  regression test `test_calculator_rejects_huge_exponent` pins the fix.)

### `current_datetime(timezone_name: str | None) -> str)`

Timezone-aware ISO-8601; unknown IANA names fall back to UTC rather than
erroring. Ships with the `tzdata` package for minimal environments.

## Execution path

Tools run inside the LangGraph graph (`ToolNode`) — the platform does not
call them itself. From the graph's stream:

- `tool_started` is emitted when the tool call's name/id appears
  (`tool_call_chunks` or complete `tool_calls`).
- The `ToolMessage` result yields `tool_completed` (or `tool_failed` when the
  framework marks status `error`).
- The runner persists a `role="tool"` transcript row (`name`, `tool_call_id`,
  content) so the inspector and history stay complete after restarts.

## Failure visibility

A raising tool never fails the run by itself: the framework returns a failed
ToolMessage, the model sees the error and can react, and the UI shows a red
inline block. `run_events` carries the same payload for post-mortems.

## Security stance

- No shell execution, no host filesystem access, no network egress in
  Phase 1 tools.
- Any future code-execution tool must run in a sandbox with explicit user
  authorization (planned, not built).
- MCP tools (Phase 4) will pass through this same registry + permission
  layer; remote results will be treated as untrusted content.
