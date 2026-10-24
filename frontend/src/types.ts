export interface User {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

export interface ToolCall {
  id: string | null;
  name: string | null;
  args: Record<string, unknown> | null;
}

export interface Message {
  id: number;
  run_id: string | null;
  role: "user" | "assistant" | "tool";
  content: string;
  tool_calls: ToolCall[] | null;
  tool_call_id: string | null;
  name: string | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  agent_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  model_provider: string;
  model_name: string;
  temperature: number;
  max_output_tokens: number | null;
  enabled_tools: string[];
  memory_enabled: boolean;
  knowledge_base_ids: string[];
  delegation_targets: string[];
  created_at: string;
  updated_at: string;
}

export interface RunUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  model_calls: number;
}

export interface AgentRun {
  id: string;
  conversation_id: string;
  agent_id: string;
  status: "running" | "completed" | "failed" | "cancelled";
  error_code: string | null;
  error_message: string | null;
  input_text: string;
  usage: RunUsage | null;
  started_at: string;
  finished_at: string | null;
}

export interface RunEvent {
  id: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface RunDetail extends AgentRun {
  events: RunEvent[];
}

export interface ToolInfo {
  name: string;
  description: string;
  category: string;
}

export interface ProviderInfo {
  id: string;
  label: string;
  configured: boolean;
  models: string[];
}

export type ChatEvent =
  | { type: "run_started"; data: { run_id: string; agent_id: string } }
  | { type: "assistant_delta"; data: { delta: string } }
  | { type: "assistant_message"; data: { content: string; tool_calls: ToolCall[] } }
  | { type: "tool_started"; data: { tool_call_id: string; name: string } }
  | { type: "tool_completed"; data: { tool_call_id: string; name: string; output?: string; node?: string } }
  | { type: "tool_failed"; data: { tool_call_id: string; name: string; error?: string } }
  | { type: "usage"; data: RunUsage }
  | { type: "run_completed"; data: { run_id: string; duration_ms: number; usage: RunUsage } }
  | { type: "run_failed"; data: { run_id: string; code: string; message: string } }
  | { type: "error"; data: { code: string; message: string } };

export interface MemoryItem {
  id: string;
  agent_id: string | null;
  category: string;
  content: string;
  source: string;
  conversation_id: string | null;
  created_at: string;
}

export interface Kb {
  id: string;
  name: string;
  description: string;
  created_at: string;
}

export interface KnowledgeDocument {
  id: string;
  kb_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  status: "pending" | "processing" | "ready" | "failed";
  error: string | null;
  chunk_count: number;
  created_at: string;
}
