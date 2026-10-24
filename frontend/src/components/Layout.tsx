import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { clsx } from "clsx";
import {
  Bot,
  Brain,
  Clock,
  Database,
  Hammer,
  LogOut,
  MessageSquare,
  Moon,
  Plug,
  Settings,
  Sun,
  Wrench,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";

interface NavItem {
  to: string;
  label: string;
  icon: typeof Bot;
  comingSoon?: boolean;
}

const groups: { title: string; items: NavItem[] }[] = [
  {
    title: "Workspace",
    items: [
      { to: "/chat", label: "Chat", icon: MessageSquare },
      { to: "/agents", label: "Agents", icon: Bot },
      { to: "/knowledge", label: "Knowledge", icon: Database },
      { to: "/memory", label: "Memory", icon: Brain },
      { to: "/automations", label: "Automations", icon: Clock, comingSoon: true },
    ],
  },
  {
    title: "Developer",
    items: [
      { to: "/tools", label: "Tools", icon: Wrench },
      { to: "/mcp", label: "MCP Servers", icon: Plug, comingSoon: true },
      { to: "/runs", label: "Execution Logs", icon: Hammer },
    ],
  },
  {
    title: "Settings",
    items: [
      { to: "/providers", label: "Providers", icon: Settings },
      { to: "/profile", label: "Profile", icon: Brain, comingSoon: true },
    ],
  },
];

function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    const stored = localStorage.getItem("theme");
    if (stored) return stored === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  return (
    <button
      onClick={() => setDark((d) => !d)}
      className="flex size-8 items-center justify-center rounded-md text-muted hover:bg-border/30 hover:text-foreground"
      title={dark ? "Switch to light theme" : "Switch to dark theme"}
    >
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="flex h-full">
      <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-card/60">
        <div className="flex h-14 items-center gap-2 px-4">
          <div className="flex size-6 items-center justify-center rounded bg-accent/15">
            <Bot className="size-3.5 text-accent" />
          </div>
          <span className="text-[13px] font-semibold tracking-tight">AI Agent Platform</span>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 py-2">
          {groups.map((group) => (
            <div key={group.title} className="mb-3">
              <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted/70">
                {group.title}
              </p>
              {group.items.map((item) =>
                item.comingSoon ? (
                  <div
                    key={item.to}
                    className="flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-muted/50"
                    title="Coming in a later phase"
                  >
                    <item.icon className="size-4" />
                    <span className="flex-1">{item.label}</span>
                    <span className="rounded bg-border/40 px-1 py-px text-[9px] uppercase">soon</span>
                  </div>
                ) : (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      clsx(
                        "flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] transition-colors",
                        isActive
                          ? "bg-accent/10 font-medium text-accent"
                          : "text-muted hover:bg-border/30 hover:text-foreground",
                      )
                    }
                  >
                    <item.icon className="size-4" />
                    {item.label}
                  </NavLink>
                ),
              )}
            </div>
          ))}
        </nav>

        <div className="border-t border-border p-2">
          <div className="flex items-center gap-2 px-2 py-1.5">
            <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-accent/15 text-[10px] font-semibold text-accent">
              {user?.name?.charAt(0).toUpperCase() ?? "?"}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[12px] font-medium">{user?.name}</p>
              <p className="truncate text-[10px] text-muted">{user?.email}</p>
            </div>
            <ThemeToggle />
            <button
              onClick={async () => {
                await logout();
                navigate("/login");
              }}
              className="flex size-8 items-center justify-center rounded-md text-muted hover:bg-border/30 hover:text-foreground"
              title="Log out"
            >
              <LogOut className="size-4" />
            </button>
          </div>
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
