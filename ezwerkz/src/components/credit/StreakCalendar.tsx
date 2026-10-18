import { Check, Clock, TriangleAlert, X } from "lucide-react";
import { Card, CardTitle } from "@/components/ui/Card";
import { cn } from "@/components/ui/cn";
import type { HistoryDotState, HistoryMonth } from "@/lib/credit/engine";
import { formatMonth, formatMonthYear } from "./format";

const CELL: Record<HistoryDotState, { label: string; className: string; icon: typeof Check | null }> = {
  on_time: { label: "On time", className: "bg-positive/15 text-positive", icon: Check },
  late: { label: "Late", className: "bg-warning/15 text-warning", icon: TriangleAlert },
  missed: { label: "Past due", className: "bg-danger/15 text-danger", icon: X },
  due: { label: "Due", className: "bg-accent/10 text-accent", icon: Clock },
  no_payment_due: { label: "Nothing due", className: "bg-surface-2 text-muted", icon: null },
  none: { label: "—", className: "bg-surface-2 text-muted", icon: null },
  not_open: { label: "—", className: "border border-dashed border-line text-muted", icon: null },
};

/** The last 12 statement months as a calendar grid, each cell labeled in words. */
export function StreakCalendar({ history }: { history: HistoryMonth[] }) {
  const months = history.slice(-12);
  return (
    <Card>
      <CardTitle>Streak calendar</CardTitle>
      <ol className="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-4">
        {months.map((m) => {
          const c = CELL[m.state];
          const Icon = c.icon;
          return (
            <li key={m.month} className={cn("flex flex-col items-center gap-1 rounded-2xl px-2 py-3 text-center", c.className)}>
              <span className="text-xs font-semibold text-ink">
                <abbr title={formatMonthYear(m.month)} className="no-underline">
                  {formatMonth(m.month)}
                </abbr>
              </span>
              {Icon ? <Icon size={18} aria-hidden strokeWidth={2.5} /> : <span className="h-[18px]" aria-hidden />}
              <span className="text-[11px] font-medium">{c.label === "—" ? <span aria-label="No statement">—</span> : c.label}</span>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
