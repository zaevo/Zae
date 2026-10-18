import Link from "next/link";
import { CalendarCheck, ChevronRight, Clock, Repeat } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Card, CardTitle } from "@/components/ui/Card";
import { formatCents } from "@/lib/money";
import type { CreditSummary } from "@/lib/credit/summary";
import { PayNowSheet, type PayNowWallet } from "./PayNowSheet";
import { daysUntil, formatLongDate, formatShortDate } from "./format";

/** Next statement + Pay now. Shows autopay status from the Wallet module. */
export function StatementCard({ summary, wallet }: { summary: CreditSummary; wallet: PayNowWallet | null }) {
  const s = summary.current;
  if (!s) {
    return (
      <Card>
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-positive/15 text-positive">
            <CalendarCheck size={18} aria-hidden />
          </span>
          <div>
            <CardTitle>Statement</CardTitle>
            <p className="mt-1 font-semibold">You&apos;re all paid up</p>
            <p className="mt-0.5 text-sm text-muted">
              {summary.nextStatementDate ? `Your next statement closes ${formatLongDate(summary.nextStatementDate)}.` : "No statements are due."}
            </p>
          </div>
        </div>
        <AutopayRow wallet={wallet} />
      </Card>
    );
  }

  const days = daysUntil(s.dueDate);
  const payable = s.remainingDueCents - s.pendingCents;
  return (
    <Card>
      <div className="flex items-center justify-between gap-3">
        <CardTitle>
          Statement · {formatShortDate(s.periodStart)} – {formatShortDate(s.periodEnd)}
        </CardTitle>
        {s.status === "past_due" ? <Badge tone="danger">Past due</Badge> : <Badge tone="accent">Due</Badge>}
      </div>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-3xl font-bold tracking-tight">{formatCents(s.remainingDueCents)}</div>
          <p className="mt-1 flex items-center gap-1.5 text-sm text-muted">
            <Clock size={14} aria-hidden />
            {s.status === "past_due"
              ? `Was due ${formatLongDate(s.dueDate)}`
              : `Due ${formatLongDate(s.dueDate)}${days >= 0 ? ` · ${days === 0 ? "today" : `in ${days} day${days === 1 ? "" : "s"}`}` : ""}`}
          </p>
        </div>
        {payable > 0 ? (
          <PayNowSheet
            statement={{ id: s.id, periodStart: s.periodStart, periodEnd: s.periodEnd, dueDate: s.dueDate, amountCents: payable }}
            wallet={wallet}
          />
        ) : null}
      </div>
      {s.pendingCents > 0 ? (
        <p className="mt-3 rounded-2xl bg-surface-2 p-3 text-sm text-muted" role="status">
          A {formatCents(s.pendingCents)} payment is processing. We&apos;ll update this statement when it settles.
        </p>
      ) : null}
      <dl className="mt-4 grid grid-cols-3 gap-2 border-t border-line pt-4 text-sm">
        <div>
          <dt className="text-xs text-muted">Membership</dt>
          <dd className="font-medium">{formatCents(s.membershipFeeCents)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Store purchases</dt>
          <dd className="font-medium">{formatCents(s.purchasesCents)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Minimum due</dt>
          <dd className="font-medium">{formatCents(s.minimumDueCents)}</dd>
        </div>
      </dl>
      <AutopayRow wallet={wallet} />
    </Card>
  );
}

function AutopayRow({ wallet }: { wallet: PayNowWallet | null }) {
  if (!wallet) return null;
  return (
    <Link
      href="/wallet"
      className="mt-4 flex items-center gap-3 rounded-2xl bg-surface-2 px-3 py-2.5 text-sm transition hover:bg-line focus-visible:outline-2 focus-visible:outline-accent"
    >
      <Repeat size={16} aria-hidden className={wallet.autopayActive ? "text-positive" : "text-muted"} />
      <span className="flex-1">
        Autopay from Wallet: <span className="font-semibold">{wallet.autopayActive ? "On" : "Off"}</span>
      </span>
      <ChevronRight size={16} aria-hidden className="text-muted" />
    </Link>
  );
}
