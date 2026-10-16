import type { ReactNode } from "react";
import { cn } from "./cn";

type Tone = "neutral" | "accent" | "positive" | "warning" | "danger";

const tones: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted",
  accent: "bg-accent/15 text-accent",
  positive: "bg-positive/15 text-positive",
  warning: "bg-warning/15 text-warning",
  danger: "bg-danger/15 text-danger",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold", tones[tone], className)}>
      {children}
    </span>
  );
}
