import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, Plus, Trash2 } from "lucide-react";
import { api } from "@/services/api";
import { Badge, Button, Card, EmptyState, Label, Select, Spinner, Textarea } from "@/components/ui";
import type { Agent, MemoryItem } from "@/types";

export default function MemoryPage() {
  const queryClient = useQueryClient();
  const [content, setContent] = useState("");
  const [category, setCategory] = useState("fact");
  const [agentId, setAgentId] = useState("");

  const { data: memories, isLoading } = useQuery({
    queryKey: ["memories"],
    queryFn: () => api.get<MemoryItem[]>("/api/memories"),
  });
  const { data: agents } = useQuery({
    queryKey: ["agents"],
    queryFn: () => api.get<Agent[]>("/api/agents"),
  });

  const create = useMutation({
    mutationFn: () =>
      api.post("/api/memories", {
        content,
        category,
        agent_id: agentId || null,
      }),
    onSuccess: () => {
      setContent("");
      queryClient.invalidateQueries({ queryKey: ["memories"] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/api/memories/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["memories"] }),
  });

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    );
  }

  const agentName = (id: string | null) => agents?.find((a) => a.id === id)?.name;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 py-6">
        <h1 className="mb-1 text-base font-semibold tracking-tight">Memory</h1>
        <p className="mb-5 text-xs text-muted">
          Long-term facts agents can save and recall. Agents with memory enabled also get these
          injected into their system prompt.
        </p>

        <Card className="mb-5 p-4">
          <div className="flex flex-col gap-3">
            <div>
              <Label>New memory</Label>
              <Textarea
                rows={2}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="e.g. User prefers TypeScript examples"
              />
            </div>
            <div className="flex items-end gap-2">
              <div className="w-40">
                <Label>Category</Label>
                <Select value={category} onChange={(e) => setCategory(e.target.value)}>
                  <option value="fact">fact</option>
                  <option value="preference">preference</option>
                  <option value="project">project</option>
                </Select>
              </div>
              <div className="w-56">
                <Label>Scope</Label>
                <Select value={agentId} onChange={(e) => setAgentId(e.target.value)}>
                  <option value="">All agents (global)</option>
                  {agents?.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </Select>
              </div>
              <Button
                variant="primary"
                className="ml-auto"
                disabled={!content.trim()}
                loading={create.isPending}
                onClick={() => create.mutate()}
              >
                <Plus className="size-3.5" /> Save
              </Button>
            </div>
          </div>
        </Card>

        {memories?.length === 0 && (
          <EmptyState icon={<Brain className="size-8" />} title="No memories saved" hint="Add one above, or let an agent with the save_memory tool store facts during chats." />
        )}

        <div className="flex flex-col gap-2">
          {memories?.map((m) => (
            <Card key={m.id} className="flex items-start gap-3 px-4 py-3">
              <Badge tone="accent">{m.category}</Badge>
              <div className="min-w-0 flex-1">
                <p className="text-[13px]">{m.content}</p>
                <p className="mt-0.5 text-[11px] text-muted">
                  {agentName(m.agent_id) ?? "global"} · {m.source}
                </p>
              </div>
              <button
                className="rounded p-1 text-muted hover:text-red-500"
                title="Delete"
                onClick={() => remove.mutate(m.id)}
              >
                <Trash2 className="size-3.5" />
              </button>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
