"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { LoaderCircle } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { formatCents } from "@/lib/money";
import { Sheet } from "./Sheet";
import { errorMessage, sendJson } from "./api";
import { formatLongDate } from "./format";

/**
 * Membership status with cancel in two taps: "Cancel membership" opens the
 * sheet, "Yes, cancel" confirms. No retention offers or guilt copy.
 */
export function MembershipCard({
  status,
  feeCents,
  startedAt,
  canceledAt,
  balanceCents,
  lineOpen,
}: {
  status: "active" | "canceled";
  feeCents: number;
  startedAt: string;
  canceledAt: string | null;
  balanceCents: number;
  lineOpen: boolean;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  const run = (method: "DELETE" | "POST") =>
    start(async () => {
      setError(null);
      try {
        await sendJson("/api/credit/membership", { method });
        setOpen(false);
        router.refresh();
      } catch (err) {
        setError(errorMessage(err));
      }
    });

  return (
    <Card>
      <div className="flex items-center justify-between">
        <CardTitle>Membership</CardTitle>
        {status === "active" ? <Badge tone="positive">Active</Badge> : <Badge>Canceled</Badge>}
      </div>
      <p className="mt-2 text-sm">
        <span className="font-semibold">{formatCents(feeCents)}/month</span>, charged to your credit line. Member since {formatLongDate(startedAt)}.
      </p>
      {status === "canceled" && canceledAt ? (
        <p className="mt-1 text-sm text-muted">
          Canceled {formatLongDate(canceledAt)}. No more monthly fees.
          {lineOpen && balanceCents > 0 ? ` Your line closes once the remaining ${formatCents(balanceCents)} is paid.` : ""}
        </p>
      ) : null}

      {error && !open ? (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      ) : null}

      <div className="mt-4">
        {status === "active" ? (
          <Button variant="secondary" onClick={() => setOpen(true)}>
            Cancel membership
          </Button>
        ) : lineOpen ? (
          <Button variant="secondary" disabled={pending} onClick={() => run("POST")}>
            {pending ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : null}
            Resume membership
          </Button>
        ) : null}
      </div>

      <Sheet open={open} onClose={() => setOpen(false)} title="Cancel membership?">
        <div className="space-y-4 text-sm">
          <ul className="list-disc space-y-1.5 pl-5 text-muted">
            <li>No more {formatCents(feeCents)} monthly fees, starting now.</li>
            <li>
              {balanceCents > 0
                ? `Your line stays open until the remaining ${formatCents(balanceCents)} is paid, then closes.`
                : "Your credit line closes today."}
            </li>
            <li>Store purchases and add-ons stop. Your payment history so far stays on your credit report.</li>
          </ul>
          {error ? (
            <p role="alert" className="rounded-2xl bg-danger/10 p-3 text-danger">
              {error}
            </p>
          ) : null}
          <div className="grid grid-cols-2 gap-2">
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Keep it
            </Button>
            <Button variant="danger" disabled={pending} onClick={() => run("DELETE")}>
              {pending ? <LoaderCircle size={16} className="animate-spin" aria-hidden /> : null}
              Yes, cancel
            </Button>
          </div>
        </div>
      </Sheet>
    </Card>
  );
}
