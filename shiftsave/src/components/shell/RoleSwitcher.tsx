"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import type { Role } from "@/lib/types";

const LABELS: Record<Role, string> = {
  member: "Credit member",
  worker: "Shift worker",
  client_manager: "Store manager",
  admin: "Admin",
};

/** Demo-only: switch which sample account you are viewing as. */
export function RoleSwitcher({ current, compact = false }: { current: Role; compact?: boolean }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  return (
    <label className="flex flex-col gap-1 text-xs text-muted">
      {compact ? <span className="sr-only">View as</span> : <span>View demo as</span>}
      <select
        className="rounded-lg border border-line bg-surface-2 px-2 py-1.5 text-xs font-medium text-ink"
        value={current}
        disabled={pending}
        onChange={(e) => {
          const role = e.target.value as Role;
          start(async () => {
            await fetch("/api/demo/role", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ role }),
            });
            router.push("/");
            router.refresh();
          });
        }}
      >
        {(Object.keys(LABELS) as Role[]).map((r) => (
          <option key={r} value={r}>
            {LABELS[r]}
          </option>
        ))}
      </select>
    </label>
  );
}
