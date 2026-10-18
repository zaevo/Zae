import { Award, Flame, Lock, Rocket, Sparkles } from "lucide-react";
import { Card, CardTitle } from "@/components/ui/Card";
import { cn } from "@/components/ui/cn";
import type { BadgeKey } from "@/lib/credit/engine";
import type { CreditSummary } from "@/lib/credit/summary";
import { formatLongDate } from "./format";

const ICONS: Record<BadgeKey, typeof Award> = {
  first_on_time_payment: Sparkles,
  streak_3: Flame,
  streak_6: Award,
  level_up: Rocket,
};

export function BadgesGrid({ badges }: { badges: CreditSummary["badges"] }) {
  const earned = badges.filter((b) => b.earnedAt).length;
  return (
    <Card>
      <div className="flex items-baseline justify-between">
        <CardTitle>Badges</CardTitle>
        <span className="text-xs text-muted">
          {earned} of {badges.length} earned
        </span>
      </div>
      <ul className="mt-4 grid grid-cols-2 gap-3">
        {badges.map((b) => {
          const Icon = b.earnedAt ? ICONS[b.key] : Lock;
          return (
            <li key={b.key} className={cn("rounded-2xl p-3", b.earnedAt ? "bg-accent/10" : "bg-surface-2")}>
              <span
                className={cn(
                  "flex h-10 w-10 items-center justify-center rounded-full",
                  b.earnedAt ? "bg-gradient-to-br from-accent to-accent-2 text-white" : "bg-surface text-muted",
                )}
              >
                <Icon size={18} aria-hidden />
              </span>
              <p className="mt-2 text-sm font-semibold">{b.title}</p>
              <p className="mt-0.5 text-xs text-muted">{b.earnedAt ? `Earned ${formatLongDate(b.earnedAt)}` : b.howToEarn}</p>
              <span className="sr-only">{b.earnedAt ? "Earned" : "Not earned yet"}</span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
