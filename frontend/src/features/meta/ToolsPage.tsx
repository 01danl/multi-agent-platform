import { useQuery } from "@tanstack/react-query";
import { Wrench } from "lucide-react";
import { api } from "@/services/api";
import { Badge, Card, EmptyState, Spinner } from "@/components/ui";
import type { ToolInfo } from "@/types";

export default function ToolsPage() {
  const { data: tools, isLoading } = useQuery({
    queryKey: ["tools"],
    queryFn: () => api.get<ToolInfo[]>("/api/tools"),
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
        <h1 className="mb-1 text-base font-semibold tracking-tight">Tools</h1>
        <p className="mb-5 text-xs text-muted">
          Platform tools agents can call. Enable per agent in its settings.
        </p>

        {(!tools || tools.length === 0) && (
          <EmptyState icon={<Wrench className="size-8" />} title="No tools registered" />
        )}

        <div className="grid grid-cols-2 gap-2">
          {tools?.map((tool) => (
            <Card key={tool.name} className="px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[13px] font-medium">{tool.name}</span>
                <Badge tone="neutral">{tool.category}</Badge>
              </div>
              <p className="mt-1 text-xs text-muted">{tool.description}</p>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
