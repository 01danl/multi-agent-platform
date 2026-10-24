import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "@/hooks/useAuth";
import Layout from "@/components/Layout";
import AuthPage from "@/features/auth/AuthPage";
import ChatPage from "@/features/chat/ChatPage";
import AgentsPage from "@/features/agents/AgentsPage";
import RunsPage from "@/features/runs/RunsPage";
import ToolsPage from "@/features/meta/ToolsPage";
import ProvidersPage from "@/features/meta/ProvidersPage";
import KnowledgePage from "@/features/knowledge/KnowledgePage";
import MemoryPage from "@/features/memory/MemoryPage";
import { Spinner } from "@/components/ui";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 5_000, refetchOnWindowFocus: false },
  },
});

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading)
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="size-5" />
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<AuthPage />} />
            <Route
              path="/"
              element={
                <Protected>
                  <Layout />
                </Protected>
              }
            >
              <Route index element={<Navigate to="/chat" replace />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="chat/:conversationId" element={<ChatPage />} />
              <Route path="agents" element={<AgentsPage />} />
              <Route path="knowledge" element={<KnowledgePage />} />
              <Route path="memory" element={<MemoryPage />} />
              <Route path="tools" element={<ToolsPage />} />
              <Route path="runs" element={<RunsPage />} />
              <Route path="providers" element={<ProvidersPage />} />
              <Route path="*" element={<Navigate to="/chat" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
