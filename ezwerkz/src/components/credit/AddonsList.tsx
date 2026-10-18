"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { LoaderCircle } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { formatCents } from "@/lib/money";
import type { AddonView } from "@/lib/credit/summary";
import { errorMessage, sendJson } from "./api";

/** Add-ons with the price up front; cancel is a single tap. */
export function AddonsList({ addons, membershipActive }: { addons: AddonView[]; membershipActive: boolean }) {
  const router = useRouter();
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [, start] = useTransition();

  const toggle = (a: AddonView) => {
    setBusyKey(a.key);
    setMessage(null);
    start(async () => {
      try {
        if (a.active) {
          await sendJson(`/api/credit/addons?addon=${encodeURIComponent(a.key)}`, { method: "DELETE" });
          setMessage({ tone: "ok", text: `${a.name} canceled. You won't be charged for it again.` });
        } else {
          await sendJson("/api/credit/addons", { method: "POST", body: { addon: a.key } });
          setMessage({ tone: "ok", text: `${a.name} added for ${formatCents(a.priceCents)}/month.` });
        }
        router.refresh();
      } catch (err) {
        setMessage({ tone: "error", text: errorMessage(err) });
      } finally {
        setBusyKey(null);
      }
    });
  };

  return (
    <Card>
      <CardTitle>Add-ons</CardTitle>
      <ul className="mt-3 divide-y divide-line">
        {addons.map((a) => (
          <li key={a.key} className="flex flex-col gap-3 py-4 first:pt-1 last:pb-0 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">{a.name}</span>
                {a.active ? <Badge tone="positive">Active</Badge> : null}
              </div>
              <p className="mt-0.5 text-sm text-muted">{a.description}</p>
              <p className="mt-1 text-sm font-medium">
                {formatCents(a.priceCents)}/month · cancel any time
              </p>
            </div>
            <Button
              variant={a.active ? "secondary" : "primary"}
              disabled={busyKey !== null || (!a.active && !membershipActive)}
              onClick={() => toggle(a)}
              className="shrink-0"
              aria-label={a.active ? `Cancel ${a.name}` : `Add ${a.name} for ${formatCents(a.priceCents)} per month`}
            >
              {busyKey === a.key ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : null}
              {a.active ? "Cancel" : "Add"}
            </Button>
          </li>
        ))}
      </ul>
      {!membershipActive ? <p className="mt-3 text-xs text-muted">Add-ons need an active membership.</p> : null}
      <div aria-live="polite">
        {message ? (
          <p className={message.tone === "ok" ? "mt-3 text-sm text-positive" : "mt-3 text-sm text-danger"} role={message.tone === "error" ? "alert" : undefined}>
            {message.text}
          </p>
        ) : null}
      </div>
    </Card>
  );
}
