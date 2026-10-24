import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Settings, XCircle } from "lucide-react";
import { api } from "@/services/api";
import { Badge, Card, Spinner } from "@/components/ui";
import type { ProviderInfo } from "@/types";

export default function ProvidersPage() {
  const { data: providers, isLoading } = useQuery({
    queryKey: ["providers"],
    queryFn: () => api.get<ProviderInfo[]>("/api/providers"),
  });

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
        <h1 className="mb-1 text-base font-semibold tracking-tight">Providers</h1>
        <p className="mb-5 text-xs text-muted">
          Model providers configured on this server. API keys are set via environment variables
          (backend <code className="rounded bg-border/40 px-1 font-mono">.env</code>) and are never
          exposed to the browser.
        </p>

        <div className="flex flex-col gap-2">
          {providers?.map((p) => (
            <Card key={p.id} className="px-4 py-3.5">
              <div className="flex items-center gap-2">
                {p.configured ? (
                  <CheckCircle2 className="size-4 text-emerald-500" />
                ) : (
                  <XCircle className="size-4 text-muted/50" />
                )}
                <span className="text-sm font-medium">{p.label}</span>
                <span className="font-mono text-[11px] text-muted">{p.id}</span>
                <Badge tone={p.configured ? "success" : "neutral"}>
                  {p.configured ? "configured" : "no API key"}
                </Badge>
              </div>
              {p.models.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {p.models.map((m) => (
                    <span
                      key={m}
                      className="rounded-full border border-border px-2 py-0.5 font-mono text-[11px] text-muted"
                    >
                      {m}
                    </span>
                  ))}
                </div>
              )}
              {p.id === "fake" && p.configured && (
                <p className="mt-2 text-[11px] text-amber-600 dark:text-amber-400">
                  Deterministic fake provider is enabled — runs make no external calls.
                </p>
              )}
            </Card>
          ))}
        </div>

        <div className="mt-4 flex items-start gap-2 rounded-md border border-dashed border-border px-3.5 py-3 text-xs text-muted">
          <Settings className="mt-0.5 size-3.5 shrink-0" />
          <p>
            Suggested models are configurable via <code className="font-mono">OPENAI_MODELS</code>,{" "}
            <code className="font-mono">OPENROUTER_MODELS</code> and{" "}
            <code className="font-mono">CUSTOM_MODELS</code> environment variables. Any model name can
            be typed in the agent editor regardless of this list.
          </p>
        </div>
      </div>
    </div>
  );
}
