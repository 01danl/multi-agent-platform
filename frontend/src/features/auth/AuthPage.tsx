import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot } from "lucide-react";
import { Button, Card, Input, Label } from "@/components/ui";
import { api, ApiError } from "@/services/api";
import { useAuth } from "@/hooks/useAuth";
import type { User } from "@/types";

export default function AuthPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { setUser } = useAuth();
  const navigate = useNavigate();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const path = mode === "login" ? "/api/auth/login" : "/api/auth/register";
      const body = mode === "login" ? { email, password } : { email, name, password };
      const user = await api.post<User>(path, body);
      setUser(user);
      navigate("/chat", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full items-center justify-center bg-background px-4">
      <div className="w-full max-w-[340px]">
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <div className="flex size-10 items-center justify-center rounded-lg bg-accent/15">
            <Bot className="size-5 text-accent" />
          </div>
          <h1 className="text-lg font-semibold tracking-tight">AI Agent Platform</h1>
          <p className="text-[13px] text-muted">
            {mode === "login" ? "Sign in to your workspace" : "Create your account"}
          </p>
        </div>

        <Card className="p-5">
          <form onSubmit={submit} className="flex flex-col gap-3.5">
            {mode === "register" && (
              <div>
                <Label>Name</Label>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Ada Lovelace"
                  required
                  minLength={1}
                  maxLength={120}
                  autoFocus={mode === "register"}
                />
              </div>
            )}
            <div>
              <Label>Email</Label>
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                autoFocus={mode === "login"}
              />
            </div>
            <div>
              <Label>Password</Label>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={mode === "register" ? "At least 8 characters" : "••••••••"}
                required
                minLength={mode === "register" ? 8 : 1}
              />
            </div>

            {error && (
              <p className="rounded-md bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
                {error}
              </p>
            )}

            <Button type="submit" variant="primary" loading={loading} className="mt-1">
              {mode === "login" ? "Sign in" : "Create account"}
            </Button>
          </form>

          <button
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError(null);
            }}
            className="mt-4 w-full text-center text-xs text-muted hover:text-foreground"
          >
            {mode === "login" ? (
              <>No account? <span className="text-accent">Register</span></>
            ) : (
              <>Already registered? <span className="text-accent">Sign in</span></>
            )}
          </button>
        </Card>
      </div>
    </div>
  );
}
