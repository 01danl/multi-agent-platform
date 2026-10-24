import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ChevronLeft, Clock, Hammer } from "lucide-react";
import { api } from "@/services/api";
import { Badge, Card, EmptyState, Spinner } from "@/components/ui";
import type { AgentRun, RunDetail } from "@/types";

const statusTone = {
  running: "warning",
  completed: "success",
  failed: "danger",
  cancelled: "neutral",
} as const;

function formatDuration(started: string, finished: string | null): string {
  if (!finished) return "—";
  const ms = new Date(finished).getTime() - new Date(started).getTime();
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export default function RunsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: runs, isLoading } = useQuery({
    queryKey: ["runs"],
    queryFn: () => api.get<AgentRun[]>("/api/runs?limit=100"),
    refetchInterval: (query) =>
      query.state.data?.some((r) => r.status === "running") ? 2000 : false,
  });

  const { data: detail } = useQuery({
    queryKey: ["run", selectedId],
    queryFn: () => api.get<RunDetail>(`/api/runs/${selectedId}`),
    enabled: !!selectedId,
  });

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    );
  }

  if (selectedId && detail) {
    return <RunDetailPanel detail={detail} onBack={() => setSelectedId(null)} />;
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 py-6">
        <h1 className="mb-1 text-base font-semibold tracking-tight">Execution Logs</h1>
        <p className="mb-5 text-xs text-muted">Every agent run with its trace, tool calls and token usage.</p>

        {(!runs || runs.length === 0) && (
          <EmptyState icon={<Hammer className="size-8" />} title="No runs yet" hint="Runs appear here after you chat with an agent." />
        )}

        <div className="flex flex-col gap-2">
          {runs?.map((run) => (
            <RunRow key={run.id} run={run} onClick={() => setSelectedId(run.id)} />
          ))}
        </div>
      </div>
    </div>
  );
}

function RunRow({ run, onClick }: { run: AgentRun; onClick: () => void }) {
  return (
    <Card className="cursor-pointer px-4 py-3 transition-colors hover:border-muted/40" onClick={onClick}>
      <div className="flex items-center gap-2">
        <Badge tone={statusTone[run.status]}>{run.status}</Badge>
        <span className="min-w-0 flex-1 truncate text-[13px]">{run.input_text || "(no input)"}</span>
        <span className="shrink-0 text-[11px] text-muted">
          {run.usage?.total_tokens ?? 0} tok · {formatDuration(run.started_at, run.finished_at)}
        </span>
      </div>
      <div className="mt-1 flex items-center gap-2 text-[11px] text-muted">
        <Clock className="size-3" />
        {new Date(run.started_at).toLocaleString()}
        {run.error_code && <span className="text-red-500">· {run.error_code}</span>}
      </div>
    </Card>
  );
}

function RunDetailPanel({ detail, onBack }: { detail: RunDetail; onBack: () => void }) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 py-6">
        <button
          onClick={onBack}
          className="mb-4 flex items-center gap-1 text-xs text-muted hover:text-foreground"
        >
          <ChevronLeft className="size-3.5" /> All runs
        </button>

        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Badge tone={statusTone[detail.status]}>{detail.status}</Badge>
          <h1 className="text-sm font-semibold">Run {detail.id.slice(0, 8)}</h1>
        </div>

        <div className="mb-5 grid grid-cols-4 gap-2">
          <Stat label="Model calls" value={detail.usage?.model_calls ?? 0} />
          <Stat label="Input tokens" value={detail.usage?.input_tokens ?? 0} />
          <Stat label="Output tokens" value={detail.usage?.output_tokens ?? 0} />
          <Stat label="Duration" value={formatDuration(detail.started_at, detail.finished_at)} />
        </div>

        {detail.error_message && (
          <div className="mb-4 rounded-md bg-red-500/10 px-3 py-2.5 text-xs text-red-600 dark:text-red-400">
            <span className="font-mono">{detail.error_code}</span>: {detail.error_message}
          </div>
        )}

        <Card className="mb-4 p-4">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted/70">Input</p>
          <p className="whitespace-pre-wrap text-[13px]">{detail.input_text}</p>
        </Card>

        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted/70">
          Timeline ({detail.events.length} events)
        </h2>
        <div className="flex flex-col gap-1.5">
          {detail.events.map((event) => (
            <TimelineEvent key={event.id} eventType={event.event_type} payload={event.payload} />
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <Card className="px-3 py-2.5">
      <p className="text-[10px] uppercase tracking-wider text-muted/70">{label}</p>
      <p className="mt-0.5 text-sm font-semibold tabular-nums">{value}</p>
    </Card>
  );
}

function TimelineEvent({
  eventType,
  payload,
}: {
  eventType: string;
  payload: Record<string, unknown>;
}) {
  const [open, setOpen] = useState(false);
  const isModel = eventType === "model_call";
  const usage = (payload.usage ?? {}) as Record<string, number | undefined>;
  const toolCalls = (payload.tool_calls ?? []) as { name?: string }[];

  return (
    <Card className="px-3.5 py-2.5">
      <button className="flex w-full items-center gap-2 text-left" onClick={() => setOpen((v) => !v)}>
        <span
          className={clsx(
            "size-1.5 rounded-full",
            isModel ? "bg-accent" : eventType === "run_completed" ? "bg-emerald-500" : eventType.startsWith("run_") ? "bg-red-500" : "bg-muted",
          )}
        />
        <span className="font-mono text-[12px] font-medium">{eventType}</span>
        {toolCalls.length > 0 && (
          <span className="text-[11px] text-muted">
            → {toolCalls.map((tc) => tc.name).join(", ")}
          </span>
        )}
        {usage.total_tokens != null && (
          <span className="ml-auto text-[11px] tabular-nums text-muted">{usage.total_tokens} tok</span>
        )}
      </button>
      {open && (
        <pre className="mt-2 max-h-64 overflow-auto rounded bg-background/70 p-2.5 font-mono text-[11px] leading-relaxed text-muted">
          {JSON.stringify(payload, null, 2)}
        </pre>
      )}
    </Card>
  );
}
