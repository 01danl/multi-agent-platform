import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { Database, FileText, Plus, Trash2, Upload, X } from "lucide-react";
import { api } from "@/services/api";
import { Badge, Button, Card, EmptyState, Input, Label, Spinner } from "@/components/ui";
import type { KnowledgeDocument, Kb } from "@/types";

const statusTone = { pending: "warning", processing: "warning", ready: "success", failed: "danger" } as const;

export default function KnowledgePage() {
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [selectedKb, setSelectedKb] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const { data: kbs, isLoading } = useQuery({
    queryKey: ["kbs"],
    queryFn: () => api.get<Kb[]>("/api/knowledge"),
  });

  const kb = kbs?.find((k) => k.id === selectedKb) ?? null;

  const { data: documents } = useQuery({
    queryKey: ["kb-documents", selectedKb],
    queryFn: () => api.get<KnowledgeDocument[]>(`/api/knowledge/${selectedKb}/documents`),
    enabled: !!selectedKb,
    refetchInterval: (query) =>
      query.state.data?.some((d) => d.status === "pending" || d.status === "processing") ? 1000 : false,
  });

  const createKb = useMutation({
    mutationFn: () => api.post<Kb>("/api/knowledge", { name, description }),
    onSuccess: (kb) => {
      queryClient.invalidateQueries({ queryKey: ["kbs"] });
      setCreating(false);
      setName("");
      setDescription("");
      setSelectedKb(kb.id);
    },
  });

  const deleteKb = useMutation({
    mutationFn: (id: string) => api.delete(`/api/knowledge/${id}`),
    onSuccess: (_d, id) => {
      queryClient.invalidateQueries({ queryKey: ["kbs"] });
      if (id === selectedKb) setSelectedKb(null);
    },
  });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const resp = await fetch(`/api/knowledge/${selectedKb}/documents`, {
        method: "POST",
        body: form,
        credentials: "same-origin",
      });
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Upload failed");
      return body;
    },
    onSuccess: () => {
      setUploadError(null);
      queryClient.invalidateQueries({ queryKey: ["kb-documents", selectedKb] });
    },
    onError: (err) => setUploadError(err instanceof Error ? err.message : "Upload failed"),
  });

  const deleteDocument = useMutation({
    mutationFn: (id: string) => api.delete(`/api/knowledge/${selectedKb}/documents/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["kb-documents", selectedKb] }),
  });

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="flex h-full min-w-0">
      {/* KB list */}
      <div className="flex w-72 shrink-0 flex-col border-r border-border bg-card/40">
        <div className="flex items-center justify-between px-3 py-2.5">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted/70">
            Knowledge bases
          </span>
          <button
            onClick={() => setCreating((v) => !v)}
            className="flex size-7 items-center justify-center rounded-md text-muted hover:bg-border/30 hover:text-foreground"
            title="New knowledge base"
          >
            <Plus className="size-4" />
          </button>
        </div>

        {creating && (
          <div className="mx-2 mb-2 rounded-md border border-border bg-card p-3">
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Product docs" autoFocus />
            <Label className="mt-2">Description</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="optional" />
            <div className="mt-2.5 flex justify-end gap-1.5">
              <Button size="sm" variant="ghost" onClick={() => setCreating(false)}>
                <X className="size-3" />
              </Button>
              <Button size="sm" variant="primary" disabled={!name.trim()} loading={createKb.isPending} onClick={() => createKb.mutate()}>
                Create
              </Button>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-2">
          {kbs?.map((k) => (
            <div
              key={k.id}
              className={clsx(
                "group mb-0.5 flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px]",
                k.id === selectedKb
                  ? "bg-accent/10 text-accent"
                  : "text-muted hover:bg-border/25 hover:text-foreground",
              )}
            >
              <button
                className="flex min-w-0 flex-1 items-center gap-2 text-left"
                onClick={() => setSelectedKb(k.id)}
              >
                <Database className="size-3.5 shrink-0" />
                <span className="min-w-0 flex-1 truncate">{k.name}</span>
              </button>
              <button
                className="hidden rounded p-0.5 hover:text-red-500 group-hover:block"
                title="Delete knowledge base"
                onClick={() => {
                  if (confirm(`Delete knowledge base "${k.name}" and all its documents?`))
                    deleteKb.mutate(k.id);
                }}
              >
                <Trash2 className="size-3" />
              </button>
            </div>
          ))}
          {kbs?.length === 0 && !creating && (
            <p className="px-2 py-4 text-xs text-muted">No knowledge bases yet.</p>
          )}
        </div>
      </div>

      {/* Documents */}
      <div className="flex min-w-0 flex-1 flex-col">
        {!kb ? (
          <EmptyState
            icon={<Database className="size-8" />}
            title="Select a knowledge base"
            hint="Create one, upload PDF/TXT/MD documents, then attach the base to an agent in Agent Studio."
          />
        ) : (
          <>
            <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
              <div className="min-w-0">
                <span className="truncate text-sm font-medium">{kb.name}</span>
                {kb.description && <span className="ml-2 text-xs text-muted">{kb.description}</span>}
              </div>
              <>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf,.txt,.md,.markdown"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) upload.mutate(file);
                    e.target.value = "";
                  }}
                />
                <Button variant="primary" size="sm" onClick={() => fileRef.current?.click()} loading={upload.isPending}>
                  <Upload className="size-3.5" /> Upload document
                </Button>
              </>
            </div>

            {uploadError && (
              <p className="mx-4 mt-3 rounded-md bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
                {uploadError}
              </p>
            )}

            <div className="flex-1 overflow-y-auto p-4">
              <div className="mx-auto flex max-w-3xl flex-col gap-2">
                {documents?.length === 0 && (
                  <EmptyState
                    icon={<FileText className="size-8" />}
                    title="No documents"
                    hint="Upload PDF, TXT or Markdown files. They are parsed, chunked and embedded on upload."
                  />
                )}
                {documents?.map((doc) => (
                  <Card key={doc.id} className="flex items-center gap-3 px-4 py-3">
                    <FileText className="size-4 shrink-0 text-muted" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-medium">{doc.filename}</p>
                      <p className="text-[11px] text-muted">
                        {(doc.size_bytes / 1024).toFixed(1)} KB
                        {doc.status === "ready" && <> · {doc.chunk_count} chunks</>}
                        {doc.status === "failed" && doc.error && <> · {doc.error.slice(0, 120)}</>}
                      </p>
                    </div>
                    <Badge tone={statusTone[doc.status as keyof typeof statusTone] ?? "neutral"}>
                      {doc.status}
                    </Badge>
                    <button
                      className="rounded p-1 text-muted hover:text-red-500"
                      title="Delete document"
                      onClick={() => deleteDocument.mutate(doc.id)}
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </Card>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
