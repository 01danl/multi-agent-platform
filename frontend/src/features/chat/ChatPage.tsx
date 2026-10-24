import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import {
  ArrowDown,
  Bot,
  Check,
  Copy,
  MessageSquarePlus,
  Pencil,
  Square,
  Trash2,
  Wrench,
  X,
} from "lucide-react";
import { api } from "@/services/api";
import { streamChatEvents } from "@/services/sse";
import { Badge, Button, EmptyState, Spinner } from "@/components/ui";
import { Markdown } from "@/components/Markdown";
import type { Agent, ChatEvent, Conversation, ConversationDetail, Message, ToolCall } from "@/types";

/** A tool call rendered inline between assistant messages. */
function ToolCallBlock({
  name,
  state,
  output,
}: {
  name: string;
  state: "running" | "done" | "failed";
  output?: string;
}) {
  return (
    <div className="my-1.5 flex flex-col gap-1 rounded-md border border-border bg-background/60 px-2.5 py-2 text-xs animate-fade-in">
      <div className="flex items-center gap-1.5 text-muted">
        {state === "running" ? (
          <Spinner className="size-3" />
        ) : state === "done" ? (
          <Check className="size-3 text-emerald-500" />
        ) : (
          <X className="size-3 text-red-500" />
        )}
        <Wrench className="size-3" />
        <span className="font-mono font-medium text-foreground">{name}</span>
        {state === "running" && <span className="text-muted">running…</span>}
      </div>
      {output && (
        <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] text-muted">
          {output.slice(0, 800)}
        </pre>
      )}
    </div>
  );
}

interface LiveTool {
  id: string;
  name: string;
  state: "running" | "done" | "failed";
  output?: string;
}

interface StreamState {
  runId: string | null;
  deltas: string;
  tools: LiveTool[];
    usage: { input_tokens: number; output_tokens: number; total_tokens: number; model_calls: number } | null;
  error: string | null;
}

const emptyStream: StreamState = { runId: null, deltas: "", tools: [], usage: null, error: null };

export default function ChatPage() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: agents } = useQuery({
    queryKey: ["agents"],
    queryFn: () => api.get<Agent[]>("/api/agents"),
  });

  const { data: conversations } = useQuery({
    queryKey: ["conversations"],
    queryFn: () => api.get<Conversation[]>("/api/conversations"),
  });

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ["conversation", conversationId],
    queryFn: () => api.get<ConversationDetail>(`/api/conversations/${conversationId}`),
    enabled: !!conversationId,
  });

  const [stream, setStream] = useState<StreamState>(emptyStream);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const [input, setInput] = useState("");
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [agentMenu, setAgentMenu] = useState(false);

  const conversation = useMemo(
    () => conversations?.find((c) => c.id === conversationId) ?? null,
    [conversations, conversationId],
  );
  const agent = useMemo(
    () => agents?.find((a) => a.id === conversation?.agent_id) ?? null,
    [agents, conversation],
  );

  const createConversation = useMutation({
    mutationFn: async (agentId: string) => {
      const conv = await api.post<Conversation>("/api/conversations", { agent_id: agentId });
      return conv;
    },
    onSuccess: (conv) => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      navigate(`/chat/${conv.id}`);
    },
  });

  const deleteConversation = useMutation({
    mutationFn: (id: string) => api.delete(`/api/conversations/${id}`),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      if (id === conversationId) navigate("/chat");
    },
  });

  const renameConversation = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      api.patch<Conversation>(`/api/conversations/${id}`, { title }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      setRenaming(null);
    },
  });

  const stop = useCallback(() => {
    if (stream.runId) {
      api.post(`/api/runs/${stream.runId}/cancel`).catch(() => {
        // disconnect also cancels server-side
      });
    }
    abortRef.current?.abort();
  }, [stream.runId]);

  const send = useCallback(
    async (content: string) => {
      if (!conversationId || !content.trim() || streaming) return;
      setInput("");
      setStreaming(true);
      setStream(emptyStream);
      const controller = new AbortController();
      abortRef.current = controller;

      const applyEvent = (event: ChatEvent) => {
        if (event.type === "run_started") {
          setStream((s) => ({ ...s, runId: event.data.run_id }));
        } else if (event.type === "assistant_delta") {
          setStream((s) => ({ ...s, deltas: s.deltas + event.data.delta }));
        } else if (event.type === "tool_started") {
          setStream((s) => ({
            ...s,
            tools: [...s.tools, { id: event.data.tool_call_id, name: event.data.name, state: "running" }],
          }));
        } else if (event.type === "tool_completed") {
          setStream((s) => ({
            ...s,
            tools: s.tools.map((t) =>
              t.id === event.data.tool_call_id
                ? { ...t, state: "done", output: event.data.output }
                : t,
            ),
          }));
        } else if (event.type === "tool_failed") {
          setStream((s) => ({
            ...s,
            tools: s.tools.map((t) =>
              t.id === event.data.tool_call_id
                ? { ...t, state: "failed", output: event.data.error }
                : t,
            ),
          }));
        } else if (event.type === "usage") {
          setStream((s) => ({ ...s, usage: event.data }));
        } else if (event.type === "run_failed") {
          setStream((s) => ({ ...s, error: `${event.data.code}: ${event.data.message}` }));
        } else if (event.type === "error") {
          setStream((s) => ({ ...s, error: event.data.message }));
        }
      };

      try {
        await streamChatEvents(conversationId, content, applyEvent, controller.signal);
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setStream((s) => ({ ...s, error: "Connection lost while streaming." }));
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
        queryClient.invalidateQueries({ queryKey: ["conversation", conversationId] });
        queryClient.invalidateQueries({ queryKey: ["conversations"] });
        queryClient.invalidateQueries({ queryKey: ["runs"] });
        // The refetched conversation now holds the persisted transcript;
        // keep only run-level info (usage) from the live stream so content
        // is not rendered twice.
        setStream((s) => ({ ...emptyStream, usage: s.usage }));
      }
    },
    [conversationId, streaming, queryClient],
  );

  // ---- rendering helpers ----

  const renderMessage = (msg: Message) => {
    if (msg.role === "user") {
      return (
        <div key={msg.id} className="flex justify-end animate-fade-in">
          <div className="max-w-[78%] rounded-lg bg-foreground px-3.5 py-2 text-[13.5px] leading-relaxed text-background">
            <Markdown content={msg.content} />
          </div>
        </div>
      );
    }
    if (msg.role === "tool") {
      return (
        <ToolCallBlock
          key={msg.id}
          name={msg.name ?? "tool"}
          state="done"
          output={msg.content}
        />
      );
    }
    // assistant
    return (
      <AssistantBubble key={msg.id} content={msg.content} toolCalls={msg.tool_calls ?? []} />
    );
  };

  const messages = detail?.messages ?? [];
  const showLiveStream = streaming || stream.deltas !== "" || stream.tools.length > 0 || stream.error;

  // auto-scroll while streaming
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);
  useEffect(() => {
    if (pinned) bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, stream.deltas, stream.tools.length, pinned]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 60);
  };

  return (
    <div className="flex h-full min-w-0">
      {/* Conversation sidebar */}
      <div className="flex w-64 shrink-0 flex-col border-r border-border bg-card/40">
        <div className="flex items-center justify-between px-3 py-2.5">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted/70">
            Conversations
          </span>
          {agents && agents.length > 0 && (
            <div className="relative">
              <button
                onClick={() => setAgentMenu((v) => !v)}
                className="flex size-7 items-center justify-center rounded-md text-muted hover:bg-border/30 hover:text-foreground"
                title="New conversation"
              >
                <MessageSquarePlus className="size-4" />
              </button>
              {agentMenu && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setAgentMenu(false)} />
                  <div className="absolute right-0 z-20 mt-1 w-52 rounded-md border border-border bg-card p-1 shadow-lg">
                    <p className="px-2 py-1 text-[10px] uppercase tracking-wider text-muted/70">
                      Start with agent
                    </p>
                    {agents.map((a) => (
                      <button
                        key={a.id}
                        className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[13px] hover:bg-border/30"
                        onClick={() => {
                          setAgentMenu(false);
                          createConversation.mutate(a.id);
                        }}
                      >
                        <Bot className="size-3.5 text-muted" />
                        {a.name}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-2 pb-2">
          {conversations?.map((c) => {
            const active = c.id === conversationId;
            return (
              <div
                key={c.id}
                className={clsx(
                  "group mb-0.5 flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px]",
                  active ? "bg-accent/10 text-accent" : "text-muted hover:bg-border/25 hover:text-foreground",
                )}
              >
                {renaming === c.id ? (
                  <form
                    className="flex w-full items-center gap-1"
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (renameTitle.trim())
                        renameConversation.mutate({ id: c.id, title: renameTitle.trim() });
                    }}
                  >
                    <input
                      autoFocus
                      value={renameTitle}
                      onChange={(e) => setRenameTitle(e.target.value)}
                      className="h-6 min-w-0 flex-1 rounded border border-border bg-background px-1.5 text-xs"
                    />
                    <button type="submit" className="text-emerald-500 hover:opacity-70">
                      <Check className="size-3.5" />
                    </button>
                  </form>
                ) : (
                  <>
                    <button
                      className="flex min-w-0 flex-1 items-center gap-2 text-left"
                      onClick={() => navigate(`/chat/${c.id}`)}
                    >
                      <Bot className="size-3.5 shrink-0" />
                      <span className="min-w-0 flex-1 truncate">{c.title}</span>
                    </button>
                    <span className="hidden items-center gap-0.5 group-hover:flex">
                      <button
                        title="Rename"
                        className="rounded p-0.5 hover:text-foreground"
                        onClick={() => {
                          setRenaming(c.id);
                          setRenameTitle(c.title);
                        }}
                      >
                        <Pencil className="size-3" />
                      </button>
                      <button
                        title="Delete"
                        className="rounded p-0.5 hover:text-red-500"
                        onClick={() => deleteConversation.mutate(c.id)}
                      >
                        <Trash2 className="size-3" />
                      </button>
                    </span>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Chat column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Header */}
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
          <div className="flex min-w-0 items-center gap-2">
            {agent ? <Bot className="size-4 shrink-0 text-accent" /> : null}
            <span className="truncate text-sm font-medium">
              {conversation ? conversation.title : "Chat"}
            </span>
            {agent && (
              <Badge tone="neutral">
                {agent.model_provider}:{agent.model_name}
              </Badge>
            )}
          </div>
          {stream.usage && (
            <span className="text-[11px] text-muted">
              {stream.usage.model_calls} model calls · {stream.usage.total_tokens} tokens
            </span>
          )}
        </div>

        {/* Messages */}
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="relative flex-1 overflow-y-auto px-4 py-4"
        >
          {!conversationId && (
            <EmptyState
              icon={<Bot className="size-8" />}
              title={agents?.length ? "Start a conversation" : "No agents yet"}
              hint={
                agents?.length
                  ? "Create a conversation from the sidebar (+ icon)."
                  : "Go to Agents and create your first agent to start chatting."
              }
            />
          )}

          {conversationId && detailLoading && (
            <div className="flex justify-center py-10">
              <Spinner />
            </div>
          )}

          <div className="mx-auto flex max-w-3xl flex-col gap-3">
            {messages.map(renderMessage)}

            {showLiveStream && (
              <div className="flex flex-col gap-1.5">
                {stream.tools.map((t) => (
                  <ToolCallBlock key={t.id} name={t.name} state={t.state} output={t.output} />
                ))}
                {stream.deltas && (
                  <div className="max-w-[78%] rounded-lg border border-border bg-card px-3.5 py-2">
                    <Markdown content={stream.deltas} />
                  </div>
                )}
                {streaming && !stream.deltas && stream.tools.length === 0 && (
                  <div className="flex items-center gap-2 text-xs text-muted">
                    <Spinner className="size-3" /> thinking…
                  </div>
                )}
                {stream.error && (
                  <div className="rounded-md bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
                    {stream.error}
                  </div>
                )}
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {!pinned && (
            <button
              onClick={() => setPinned(true)}
              className="absolute bottom-4 right-6 flex size-8 items-center justify-center rounded-full border border-border bg-card shadow-sm hover:bg-border/30"
              title="Scroll to bottom"
            >
              <ArrowDown className="size-4" />
            </button>
          )}
        </div>

        {/* Composer */}
        <div className="shrink-0 border-t border-border p-3">
          <form
            className="mx-auto flex max-w-3xl items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              rows={Math.min(4, Math.max(1, input.split("\n").length))}
              placeholder={
                conversationId
                  ? "Message… (Enter to send, Shift+Enter for newline)"
                  : "Pick or start a conversation first"
              }
              disabled={!conversationId}
              className="max-h-32 min-h-9 flex-1 resize-none rounded-md border border-border bg-card px-3 py-2 text-sm leading-relaxed placeholder:text-muted/70 focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-50"
            />
            {streaming ? (
              <Button type="button" variant="danger" onClick={stop} size="md">
                <Square className="size-3.5" /> Stop
              </Button>
            ) : (
              <Button type="submit" variant="primary" disabled={!conversationId || !input.trim()}>
                Send
              </Button>
            )}
          </form>
        </div>
      </div>
    </div>
  );
}

function AssistantBubble({ content, toolCalls }: { content: string; toolCalls: ToolCall[] }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="group flex flex-col items-start gap-1 animate-fade-in">
      <div className="max-w-[85%] rounded-lg border border-border bg-card px-3.5 py-2">
        {toolCalls.length > 0 && (
          <div className="mb-1.5 flex flex-wrap gap-1">
            {toolCalls.map((tc) => (
              <Badge key={tc.id ?? tc.name} tone="accent">
                {tc.name}
              </Badge>
            ))}
          </div>
        )}
        {content ? (
          <Markdown content={content} />
        ) : (
          <span className="text-xs italic text-muted">tool call</span>
        )}
      </div>
      {content && (
        <button
          className="flex items-center gap-1 px-1 text-[10px] text-muted opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100"
          onClick={() => {
            navigator.clipboard.writeText(content);
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          }}
        >
          {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
          {copied ? "Copied" : "Copy"}
        </button>
      )}
    </div>
  );
}
