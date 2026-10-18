import { Check, Clock, TriangleAlert, X } from "lucide-react";
import { Card, CardTitle } from "@/components/ui/Card";
import { cn } from "@/components/ui/cn";
import type { HistoryDotState, HistoryMonth } from "@/lib/credit/engine";
import { formatMonth, formatMonthYear } from "./format";

const STATES: Record<HistoryDotState, { label: string; dot: string; icon: typeof Check | null }> = {
  on_time: { label: "Paid on time", dot: "bg-positive text-white", icon: Check },
  late: { label: "Paid late", dot: "bg-warning text-white", icon: TriangleAlert },
  missed: { label: "Past due", dot: "bg-danger text-white", icon: X },
  due: { label: "Due", dot: "border-2 border-accent text-accent", icon: Clock },
  no_payment_due: { label: "No payment due", dot: "bg-surface-2 border border-line", icon: null },
  none: { label: "No statement", dot: "bg-surface-2", icon: null },
  not_open: { label: "Before your line opened", dot: "border border-dashed border-line", icon: null },
};

const LEGEND: HistoryDotState[] = ["on_time", "late", "missed", "due"];

/**
 * 24 months of statement outcomes. Each state has its own icon and a legend,
 * so it never relies on color alone; a screen-reader list mirrors the dots.
 */
export function PaymentHistoryDots({ history }: { history: HistoryMonth[] }) {
  const rows = [history.slice(0, 12), history.slice(12)];
  const onTime = history.filter((h) => h.state === "on_time").length;
  return (
    <Card>
      <div className="flex items-baseline justify-between gap-3">
        <CardTitle>Payment history</CardTitle>
        <span className="text-xs text-muted">Last 24 months</span>
      </div>
      <p className="mt-1 text-sm">
        <span className="font-semibold">{onTime}</span> on-time payment{onTime === 1 ? "" : "s"} reported
      </p>

      <div className="mt-4 space-y-3" aria-hidden>
        {rows.map((row, r) => (
          <div key={r} className="grid grid-cols-12 gap-1">
            {row.map((m) => {
              const st = STATES[m.state];
              const Icon = st.icon;
              return (
                <div key={m.month} className="flex flex-col items-center gap-1" title={`${formatMonthYear(m.month)}: ${st.label}`}>
                  <span className={cn("flex h-5 w-5 items-center justify-center rounded-full sm:h-6 sm:w-6", st.dot)}>
                    {Icon ? <Icon size={12} strokeWidth={3} /> : null}
                  </span>
                  <span className="text-[10px] leading-none text-muted">{formatMonth(m.month).slice(0, 1)}</span>
                </div>
              );
            })}
          </div>
        ))}
      </div>

      <ol className="sr-only">
        {history
          .filter((m) => m.state !== "not_open")
          .map((m) => (
            <li key={m.month}>
              {formatMonthYear(m.month)}: {STATES[m.state].label}
            </li>
          ))}
      </ol>

      <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted" aria-label="Legend">
        {LEGEND.map((k) => {
          const st = STATES[k];
          const Icon = st.icon;
          return (
            <li key={k} className="flex items-center gap-1.5">
              <span className={cn("flex h-4 w-4 items-center justify-center rounded-full", st.dot)} aria-hidden>
                {Icon ? <Icon size={10} strokeWidth={3} /> : null}
              </span>
              {st.label}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
