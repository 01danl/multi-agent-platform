# 09 — Multi-Agent Architecture

Phase 3 acceptance — a coordinator delegates a task to specialized agents,
receives their outputs, and generates a consolidated response — is met and
browser-verified end-to-end.

## Model: Deep Agents subagents, not a second framework

The platform uses Deep Agents' native delegation (`SubAgent` declarations +
the `task` tool) exactly as intended; our contribution is the mapping from
persisted agent configurations into those declarations.

```text
Coordinator (any agent with delegation_targets)
   |  task(subagent_type="research", description="…")
   v
SubAgent "research"  — own model, own tools, own prompt, own KBs
   |  calculator("2+2")          (inside the subgraph)
   v
ToolMessage → coordinator consolidates → final answer
```

## Configuration

- `agents.delegation_targets` — list of agent ids the agent may delegate to.
  Validated on write: targets must belong to the same owner; self-reference
  rejected; foreign/unknown ids rejected with 422.
- Targets are resolved at run time by `_resolve_delegation_specs`: stale or
  deleted targets are skipped (runs never crash on stale config); each target
  becomes a `DelegationSpec` with a URL-safe slug derived from its name
  (`Research Agent` → `research-agent`, collisions suffixed with id).

## Runner integration

`build_graph` converts specs into typed `SubAgent` declarations:

- **Own model**: built from the target's provider/model config via the same
  factory as the parent. Unconfigured target providers inherit the parent's
  model (logged warning) instead of failing the run.
- **Own tools**: the target's `enabled_tools`, built with a per-target
  `ToolContext` — same user/run scope, the target's `agent_id`, and the
  target's knowledge bases (a research subagent searches its own KBs, not the
  coordinator's).
- **Own prompt**: the target's system prompt.

## Limits and safety

| Concern | Mechanism |
|---|---|
| Delegation depth | 1 by construction — declared subagents do not receive the `task` tool, so no recursive delegation or config cycles can occur at runtime |
| Cross-tenant access | targets filtered by `owner_id` in SQL at resolution time (not by prompt) |
| Runaway execution | parent `ModelCallLimitMiddleware` + recursion limit + wall-clock timeout (unchanged) |
| Stale configuration | missing targets skipped; unconfigured models inherit parent |

## Observability

The `task` call is a regular tool call in the parent stream: `tool_started`,
`tool_completed` (with the specialist's answer), a `tool`-role transcript row,
and a `model_call` trace entry. The execution inspector therefore shows
delegation timelines without special handling.

Known limitation (honest): token usage aggregation currently counts the
parent graph's model calls; subgraph model calls (the specialist's own turns)
are not added to the run's usage totals — visible in the UI as
undercounted usage for delegating runs. Inner subagent tool events are also
not streamed (subgraphs=False); `subgraphs=True` streaming is the follow-up.

## Alternatives considered

- **Platform-level orchestration loop** (coordinator service calling
  AgentRunner recursively per specialist): would duplicate Deep Agents'
  delegation, complicate streaming, and re-implement context isolation.
- **LangGraph supervisor pattern from scratch**: same objection.
- **Arbitrary-depth delegation**: rejected for Phase 3 — depth 1 covers the
  coordinator/specialists workflow and cannot loop; deeper chains (and
  parallel fan-out UX) are future work with explicit cycle detection.
