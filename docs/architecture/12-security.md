# 12 — Security

## Authentication

- Passwords: stdlib scrypt (`n=2^14, r=8, p=1`, 16-byte salt, 32-byte key),
  `hmac.compare_digest` verification. No plaintext ever stored.
- Sessions: 32-byte urlsafe token in an HttpOnly, SameSite=Lax cookie
  (`secure` outside debug); only the SHA-256 hash is stored server-side with
  an expiry (14d default). Logout deletes the row; expired rows are rejected
  and removed on sight.
- Registration rate/lockout protections are not implemented yet (single-user,
  self-hosted scope; listed as Phase 5 hardening).

## Authorization & isolation

- Every agents/conversations/runs query filters by `owner_id`; other users'
  resources 404 (no existence oracle).
- Tool execution is scoped by `ToolContext` (user/agent/conversation/run ids)
  — today's tools are pure, and the context is the seam later file/knowledge
  tools must use.
- Agent editor only offers providers configured on the server; a run against
  an unconfigured provider fails with a structured error instead of leaking
  why.

## Secrets

- Provider API keys live only in server env vars. They are never written to
  the DB, never returned by any endpoint (`GET /api/providers` exposes only
  configured true/false), and never logged.
- `SECRET_KEY` is env-provided and must be changed in production
  (`.env.example` marks it).

## Input handling

- All API bodies validated by Pydantic (length caps everywhere, e.g. messages
  ≤ 32k chars, password policy).
- Calculator tool: AST whitelist (no attribute access, no names, no calls);
  DoS guards on exponent/result size/length.
- Uploads: not implemented in Phase 1; the design constraints (size limits,
  MIME sniffing, path-traversal-safe storage keys) are queued with the
  knowledge base (Phase 2).

## Execution containment

- Model-call cap per run, graph recursion limit, wall-clock timeout
  (see 03-agent-harness.md).
- One active run per conversation (409 otherwise).
- No shell, filesystem, or network tools are exposed to agents. Future
  code-execution tools must be sandboxed and explicitly authorized; future
  URL-fetching tools must address SSRF (allowlist, no internal ranges) —
  these are deliberate non-goals until then.

## Prompt-injection posture (honest)

System prompts are not treated as a security boundary. Retrieved-content
tools (future RAG/MCP) will render untrusted text as data (tool output
framing, no implicit instructions), keep the tool permission list explicit
per agent, and surface citations so users can verify. We do not claim prompt
injection is solved.

## Logging

Structured logs carry run/agent/conversation/user ids and classified error
codes; secrets and message contents are not logged. Internal exception detail
stays server-side — the API returns `code` + human-readable `message` only.
