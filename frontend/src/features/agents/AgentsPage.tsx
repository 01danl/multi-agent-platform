import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Bot, MessageSquarePlus, Pencil, Plus, Trash2, X } from "lucide-react";
import { api } from "@/services/api";
import { Badge, Button, Card, EmptyState, Input, Label, Spinner, Textarea } from "@/components/ui";
import type { Agent, Conversation, Kb, ProviderInfo, ToolInfo } from "@/types";

interface AgentDraft {
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
}

const emptyDraft = (provider: string, model: string): AgentDraft => ({
  name: "",
  description: "",
  system_prompt: "You are a helpful assistant.",
  model_provider: provider,
  model_name: model,
  temperature: 0.7,
  max_output_tokens: null,
  enabled_tools: [],
  memory_enabled: false,
  knowledge_base_ids: [],
  delegation_targets: [],
});

export default function AgentsPage() {
  const [editingId, setEditingId] = useState<string | "new" | null>(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const { data: agents, isLoading } = useQuery({
    queryKey: ["agents"],
    queryFn: () => api.get<Agent[]>("/api/agents"),
  });
  const { data: providers } = useQuery({
    queryKey: ["providers"],
    queryFn: () => api.get<ProviderInfo[]>("/api/providers"),
  });
  const { data: tools } = useQuery({
    queryKey: ["tools"],
    queryFn: () => api.get<ToolInfo[]>("/api/tools"),
  });
  const { data: kbs } = useQuery({
    queryKey: ["kbs"],
    queryFn: () => api.get<Kb[]>("/api/knowledge"),
  });

  const deleteAgent = useMutation({
    mutationFn: (id: string) => api.delete(`/api/agents/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agents"] }),
  });

  const chatWith = useMutation({
    mutationFn: async (agentId: string) =>
      api.post<Conversation>("/api/conversations", { agent_id: agentId }),
    onSuccess: (conv) => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      navigate(`/chat/${conv.id}`);
    },
  });

  const editing = editingId === "new" ? null : agents?.find((a) => a.id === editingId) ?? null;

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 py-6">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h1 className="text-base font-semibold tracking-tight">Agents</h1>
            <p className="text-xs text-muted">Configure assistants with their own model, prompt and tools.</p>
          </div>
          <Button variant="primary" size="sm" onClick={() => setEditingId("new")}>
            <Plus className="size-3.5" /> New agent
          </Button>
        </div>

        {editingId !== null && (
          <AgentEditor
            key={editingId}
            agent={editing}
            agents={agents ?? []}
            providers={providers ?? []}
            tools={tools ?? []}
            kbs={kbs ?? []}
            onClose={() => setEditingId(null)}
          />
        )}

        {(!agents || agents.length === 0) && editingId === null && (
          <EmptyState
            icon={<Bot className="size-8" />}
            title="No agents yet"
            hint="Create an agent to start chatting. It needs a model provider configured on the server."
          />
        )}

        <div className="flex flex-col gap-2">
          {agents?.map((agent) => (
            <Card key={agent.id} className="group flex items-center gap-3 px-4 py-3">
              <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-accent/12">
                <Bot className="size-4 text-accent" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="truncate text-sm font-medium">{agent.name}</p>
                  {agent.enabled_tools.length > 0 && (
                    <Badge tone="neutral">{agent.enabled_tools.length} tools</Badge>
                  )}
                </div>
                <p className="truncate text-xs text-muted">
                  {agent.description || agent.system_prompt.slice(0, 80) || "No description"}
                </p>
              </div>
              <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                <Button
                  size="sm"
                  variant="ghost"
                  title="Chat"
                  onClick={() => chatWith.mutate(agent.id)}
                >
                  <MessageSquarePlus className="size-3.5" />
                </Button>
                <Button size="sm" variant="ghost" title="Edit" onClick={() => setEditingId(agent.id)}>
                  <Pencil className="size-3.5" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  title="Delete"
                  className="hover:text-red-500"
                  onClick={() => {
                    if (confirm(`Delete agent "${agent.name}" and its conversations?`))
                      deleteAgent.mutate(agent.id);
                  }}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

function AgentEditor({
  agent,
  agents,
  providers,
  tools,
  kbs,
  onClose,
}: {
  agent: Agent | null;
  agents: Agent[];
  providers: ProviderInfo[];
  tools: ToolInfo[];
  kbs: Kb[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const configured = providers.filter((p) => p.configured);
  const firstProvider = configured[0]?.id ?? providers[0]?.id ?? "fake";
  const firstModel = configured[0]?.models[0] ?? providers[0]?.models[0] ?? "";

  const [draft, setDraft] = useState<AgentDraft>(() =>
    agent
      ? {
          name: agent.name,
          description: agent.description,
          system_prompt: agent.system_prompt,
          model_provider: agent.model_provider,
          model_name: agent.model_name,
          temperature: agent.temperature,
          max_output_tokens: agent.max_output_tokens,
          enabled_tools: agent.enabled_tools,
          memory_enabled: agent.memory_enabled,
          knowledge_base_ids: agent.knowledge_base_ids,
          delegation_targets: agent.delegation_targets ?? [],
        }
      : emptyDraft(firstProvider, firstModel),
  );
  const [error, setError] = useState<string | null>(null);

  const provider = providers.find((p) => p.id === draft.model_provider);

  const save = useMutation({
    mutationFn: async () => {
      const body = { ...draft, max_output_tokens: draft.max_output_tokens || null };
      if (agent) return api.patch<Agent>(`/api/agents/${agent.id}`, body);
      return api.post<Agent>("/api/agents", body);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      onClose();
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Failed to save"),
  });

  useEffect(() => {
    if (provider && !provider.models.includes(draft.model_name) && !agent) {
      setDraft((d) => ({ ...d, model_name: provider.models[0] ?? d.model_name }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.model_provider]);

  const set = <K extends keyof AgentDraft>(key: K, value: AgentDraft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  return (
    <Card className="mb-5 p-5 animate-fade-in">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold">{agent ? `Edit: ${agent.name}` : "New agent"}</h2>
        <button onClick={onClose} className="rounded p-1 text-muted hover:text-foreground">
          <X className="size-4" />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3.5">
        <div>
          <Label>Name</Label>
          <Input value={draft.name} onChange={(e) => set("name", e.target.value)} placeholder="Research Assistant" />
        </div>
        <div>
          <Label>Description</Label>
          <Input
            value={draft.description}
            onChange={(e) => set("description", e.target.value)}
            placeholder="What does this agent do?"
          />
        </div>
        <div>
          <Label>Provider</Label>
          <select
            value={draft.model_provider}
            onChange={(e) => set("model_provider", e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-card px-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
          >
            {providers.map((p) => (
              <option key={p.id} value={p.id} disabled={!p.configured}>
                {p.label}
                {p.configured ? "" : " (no API key on server)"}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label>Model</Label>
          <Input
            list="model-options"
            value={draft.model_name}
            onChange={(e) => set("model_name", e.target.value)}
            placeholder={provider?.models[0] ?? "model name"}
          />
          <datalist id="model-options">
            {provider?.models.map((m) => <option key={m} value={m} />)}
          </datalist>
        </div>
        <div>
          <Label>Temperature: {draft.temperature.toFixed(1)}</Label>
          <input
            type="range"
            min={0}
            max={2}
            step={0.1}
            value={draft.temperature}
            onChange={(e) => set("temperature", Number(e.target.value))}
            className="mt-2 w-full accent-[var(--accent)]"
          />
        </div>
        <div>
          <Label>Max output tokens (optional)</Label>
          <Input
            type="number"
            min={1}
            max={200000}
            value={draft.max_output_tokens ?? ""}
            onChange={(e) => set("max_output_tokens", e.target.value ? Number(e.target.value) : null)}
            placeholder="provider default"
          />
        </div>
      </div>

      <div className="mt-3.5">
        <Label>System prompt</Label>
        <Textarea
          rows={5}
          value={draft.system_prompt}
          onChange={(e) => set("system_prompt", e.target.value)}
          placeholder="You are a…"
          className="font-mono text-[12.5px]"
        />
      </div>

      <div className="mt-3.5">
        <Label>Tools</Label>
        <div className="flex flex-wrap gap-2">
          {tools.map((t) => {
            const enabled = draft.enabled_tools.includes(t.name);
            return (
              <button
                key={t.name}
                type="button"
                title={t.description}
                onClick={() =>
                  set(
                    "enabled_tools",
                    enabled
                      ? draft.enabled_tools.filter((n) => n !== t.name)
                      : [...draft.enabled_tools, t.name],
                  )
                }
                className={
                  "rounded-full border px-2.5 py-1 font-mono text-[11px] transition-colors " +
                  (enabled
                    ? "border-accent/50 bg-accent/10 text-accent"
                    : "border-border text-muted hover:border-muted/50")
                }
              >
                {t.name}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-3.5">
        <Label>Knowledge bases</Label>
        {kbs.length === 0 ? (
          <p className="text-xs text-muted">
            No knowledge bases yet — create one under Knowledge, then attach it here.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {kbs.map((kb) => {
              const on = draft.knowledge_base_ids.includes(kb.id);
              return (
                <button
                  key={kb.id}
                  type="button"
                  title={kb.description || kb.name}
                  onClick={() =>
                    set(
                      "knowledge_base_ids",
                      on
                        ? draft.knowledge_base_ids.filter((id) => id !== kb.id)
                        : [...draft.knowledge_base_ids, kb.id],
                    )
                  }
                  className={
                    "rounded-full border px-2.5 py-1 text-[11px] transition-colors " +
                    (on
                      ? "border-accent/50 bg-accent/10 text-accent"
                      : "border-border text-muted hover:border-muted/50")
                  }
                >
                  {kb.name}
                </button>
              );
            })}
          </div>
        )}
        <p className="mt-1.5 text-[11px] text-muted">
          Attached bases are searchable by the knowledge_search tool.
        </p>
      </div>

      <div className="mt-3.5">
        <Label>Can delegate to</Label>
        {agents.filter((a) => a.id !== agent?.id).length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {agents
              .filter((a) => a.id !== agent?.id)
              .map((a) => {
                const on = draft.delegation_targets.includes(a.id);
                return (
                  <button
                    key={a.id}
                    type="button"
                    title={a.description || a.name}
                    onClick={() =>
                      set(
                        "delegation_targets",
                        on
                          ? draft.delegation_targets.filter((id) => id !== a.id)
                          : [...draft.delegation_targets, a.id],
                      )
                    }
                    className={
                      "rounded-full border px-2.5 py-1 text-[11px] transition-colors " +
                      (on
                        ? "border-accent/50 bg-accent/10 text-accent"
                        : "border-border text-muted hover:border-muted/50")
                    }
                  >
                    {a.name}
                  </button>
                );
              })}
          </div>
        ) : (
          <p className="text-xs text-muted">Create more agents to enable delegation.</p>
        )}
        <p className="mt-1.5 text-[11px] text-muted">
          The agent can call the task tool to send work to these specialists.
        </p>
      </div>

      <label className="mt-3.5 flex cursor-pointer items-center gap-2 text-[13px]">
        <input
          type="checkbox"
          checked={draft.memory_enabled}
          onChange={(e) => set("memory_enabled", e.target.checked)}
          className="size-3.5 accent-[var(--accent)]"
        />
        <span>
          Memory: inject saved memories into the system prompt
          <span className="ml-1 text-muted">(manage under Memory)</span>
        </span>
      </label>

      {error && (
        <p className="mt-3 rounded-md bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>
          {agent ? "Save changes" : "Create agent"}
        </Button>
      </div>
    </Card>
  );
}
