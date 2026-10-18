import { Check, Flame, Rocket } from "lucide-react";
import { Card, CardTitle } from "@/components/ui/Card";
import { formatCents } from "@/lib/money";
import type { CreditSummary } from "@/lib/credit/summary";

function ProgressBar({ value, max, label }: { value: number; max: number; label: string }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={Math.min(value, max)}
      aria-label={label}
      className="h-2 w-full overflow-hidden rounded-full bg-accent/15"
    >
      <div className="h-full rounded-full bg-accent transition-[width] duration-700" style={{ width: `${pct}%` }} />
    </div>
  );
}

/** Streak + level-up progress. Copy celebrates progress and never threatens. */
export function StreakCard({ summary }: { summary: CreditSummary }) {
  const { streak, nextMilestone, levelUp } = summary;
  return (
    <Card>
      <CardTitle>Streak</CardTitle>
      <div className="mt-2 flex items-center gap-3">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-accent to-accent-2 text-white">
          <Flame size={22} aria-hidden />
        </span>
        <div>
          <div className="text-2xl font-bold tracking-tight">
            {streak.current} month{streak.current === 1 ? "" : "s"}
          </div>
          <p className="text-sm text-muted">
            {streak.current === 0
              ? "Your first on-time payment starts your streak."
              : streak.current >= 3
                ? "of on-time payments in a row. You're on a roll!"
                : "of on-time payments in a row. Great start!"}
          </p>
        </div>
      </div>

      {nextMilestone ? (
        <div className="mt-4 space-y-2">
          <div className="flex justify-between text-xs">
            <span className="font-medium">Next badge: {nextMilestone.badge.title}</span>
            <span className="text-muted">
              {nextMilestone.monthsToGo} to go
            </span>
          </div>
          <ProgressBar
            value={streak.current}
            max={streak.current + nextMilestone.monthsToGo}
            label={`Progress to ${nextMilestone.badge.title}`}
          />
        </div>
      ) : null}

      {levelUp ? (
        <div className="mt-4 rounded-2xl bg-surface-2 p-3">
          {levelUp.leveledUp ? (
            <p className="flex items-center gap-2 text-sm">
              <Check size={16} aria-hidden className="text-positive" />
              <span>
                Leveled up: your limit is <span className="font-semibold">{formatCents(levelUp.currentLimitCents)}</span>
              </span>
            </p>
          ) : (
            <div className="space-y-2">
              <p className="flex items-center gap-2 text-sm">
                <Rocket size={16} aria-hidden className="text-accent" />
                <span>
                  {levelUp.eligible
                    ? `You've unlocked a ${formatCents(levelUp.nextLimitCents)} limit. We're applying it to your line.`
                    : `${levelUp.remainingMonths} more on-time payment${levelUp.remainingMonths === 1 ? "" : "s"} to level up to a ${formatCents(levelUp.nextLimitCents)} limit`}
                </span>
              </p>
              <ProgressBar value={levelUp.onTimeMonths} max={levelUp.requiredMonths} label="Progress to level-up" />
            </div>
          )}
        </div>
      ) : null}
    </Card>
  );
}
