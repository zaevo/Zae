import type { ReactNode } from "react";

export function EmptyState({ title, body, action }: { title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-[var(--radius-card)] border border-dashed border-line p-8 text-center">
      <div className="text-sm font-semibold text-ink">{title}</div>
      {body ? <div className="mt-1 text-sm text-muted">{body}</div> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
