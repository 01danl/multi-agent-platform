import type { ButtonHTMLAttributes, InputHTMLAttributes, TextareaHTMLAttributes, ReactNode } from "react";
import { clsx } from "clsx";
import { Loader2 } from "lucide-react";

export function Button({
  variant = "default",
  size = "md",
  loading,
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "primary" | "ghost" | "danger";
  size?: "sm" | "md";
  loading?: boolean;
}) {
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors",
        "disabled:pointer-events-none disabled:opacity-50",
        size === "sm" ? "h-7 px-2.5 text-xs" : "h-9 px-3.5 text-sm",
        variant === "default" &&
          "border border-border bg-card text-foreground hover:bg-border/40",
        variant === "primary" &&
          "bg-foreground text-background hover:opacity-85",
        variant === "ghost" && "text-muted hover:bg-border/30 hover:text-foreground",
        variant === "danger" &&
          "border border-transparent bg-red-500/10 text-red-500 hover:bg-red-500/20",
        className,
      )}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading && <Loader2 className="size-3.5 animate-spin" />}
      {children}
    </button>
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={clsx(
        "h-9 w-full rounded-md border border-border bg-card px-3 text-sm text-foreground",
        "placeholder:text-muted/70 focus:outline-none focus:ring-2 focus:ring-accent/40",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={clsx(
        "w-full rounded-md border border-border bg-card px-3 py-2 text-sm text-foreground",
        "placeholder:text-muted/70 focus:outline-none focus:ring-2 focus:ring-accent/40",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={clsx(
        "h-9 w-full rounded-md border border-border bg-card px-2.5 text-sm text-foreground",
        "focus:outline-none focus:ring-2 focus:ring-accent/40",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}

export function Card({
  className,
  children,
  onClick,
}: {
  className?: string;
  children: ReactNode;
  onClick?: () => void;
}) {
  return (
    <div onClick={onClick} className={clsx("rounded-lg border border-border bg-card", className)}>
      {children}
    </div>
  );
}

export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <label className={clsx("mb-1.5 block text-xs font-medium text-muted", className)}>
      {children}
    </label>
  );
}

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "success" | "danger" | "warning" | "accent";
  children: ReactNode;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
        tone === "neutral" && "bg-border/50 text-muted",
        tone === "success" && "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
        tone === "danger" && "bg-red-500/10 text-red-600 dark:text-red-400",
        tone === "warning" && "bg-amber-500/10 text-amber-600 dark:text-amber-400",
        tone === "accent" && "bg-accent/10 text-accent",
      )}
    >
      {children}
    </span>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx("size-4 animate-spin text-muted", className)} />;
}

export function EmptyState({
  title,
  hint,
  icon,
}: {
  title: string;
  hint?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-16 text-center">
      {icon && <div className="text-muted/60">{icon}</div>}
      <p className="text-sm font-medium text-foreground">{title}</p>
      {hint && <p className="max-w-sm text-xs text-muted">{hint}</p>}
    </div>
  );
}
