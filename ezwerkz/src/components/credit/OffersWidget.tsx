import { ArrowUpRight, Info, Lock } from "lucide-react";
import { Card, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { formatCents } from "@/lib/money";
import type { CreditSummary } from "@/lib/credit/summary";
import { SCORE_DISCLAIMER } from "./ScoreTile";

const SCORE_FLOOR = 300;

/**
 * The 660 card matcher. Unlocked: a horizontally scrolling row of card-shaped
 * offers ranked by fit (never by commission), with the commission disclosure
 * and a "Why am I seeing this?" explainer. Locked: a teaser with progress.
 */
export function OffersWidget({ summary }: { summary: CreditSummary }) {
  const { offers, score } = summary;

  if (!offers.unlocked) {
    const pct = score ? Math.min(100, Math.max(0, Math.round(((score.score - SCORE_FLOOR) / (offers.threshold - SCORE_FLOOR)) * 100))) : 0;
    return (
      <Card>
        <div className="flex items-center justify-between">
          <CardTitle>Card matcher</CardTitle>
          <Lock size={16} aria-hidden className="text-muted" />
        </div>
        <p className="mt-2 font-semibold">Unlocks at a {offers.threshold} score</p>
        <p className="mt-1 text-sm text-muted">
          {score
            ? `You're at ${score.score}. When you reach ${offers.threshold}, we'll show cards that fit your profile.`
            : "Check your score above to see your progress toward card matches."}
        </p>
        {score ? (
          <div className="mt-3 space-y-1.5">
            <div
              role="progressbar"
              aria-valuemin={SCORE_FLOOR}
              aria-valuemax={offers.threshold}
              aria-valuenow={Math.min(score.score, offers.threshold)}
              aria-label={`Score progress toward ${offers.threshold}`}
              className="h-2 w-full overflow-hidden rounded-full bg-accent/15"
            >
              <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
            </div>
            <div className="flex justify-between text-xs text-muted">
              <span>{score.score}</span>
              <span>{offers.threshold}</span>
            </div>
          </div>
        ) : null}
        <p className="mt-3 text-xs text-muted">{SCORE_DISCLAIMER}</p>
      </Card>
    );
  }

  return (
    <section aria-labelledby="offers-title" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="offers-title" className="text-lg font-semibold tracking-tight">
          Cards that fit you
        </h2>
        <Badge tone="positive">{offers.threshold}+ unlocked</Badge>
      </div>
      <p className="text-xs text-muted">
        <span className="font-semibold text-ink">EzWerkz may earn a commission</span> if you apply and are approved. It never changes the order you see.
      </p>

      {offers.eligible.length ? (
        <ul
          className="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2 [scrollbar-width:thin] focus-visible:outline-2 focus-visible:outline-accent md:mx-0 md:px-0"
          aria-label="Card offers, ranked by fit"
          tabIndex={0}
        >
          {offers.eligible.map((o) => (
            <li key={o.id} className="w-[17rem] shrink-0 snap-start">
              <article className="flex h-full flex-col overflow-hidden rounded-[var(--radius-card)] border border-line bg-surface shadow-sm">
                <div className="relative aspect-[1.586/1] bg-gradient-to-br from-accent to-accent-2 p-4 text-white">
                  <div aria-hidden className="absolute -right-10 -top-10 h-32 w-32 rounded-full bg-white/10" />
                  <div className="relative flex h-full flex-col justify-between">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-xs font-semibold uppercase tracking-wider text-white/80">{o.issuer}</span>
                      <span className="rounded-full bg-white/20 px-2 py-0.5 text-[11px] font-semibold">#{o.rank} fit</span>
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold leading-tight">{o.productName}</h3>
                      <span aria-hidden className="mt-2 block h-6 w-9 rounded-md bg-white/30" />
                    </div>
                  </div>
                </div>
                <div className="flex flex-1 flex-col p-4">
                  <dl className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <dt className="text-xs text-muted">Annual fee</dt>
                      <dd className="font-semibold">{o.annualFeeCents === 0 ? "None" : formatCents(o.annualFeeCents)}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted">APR</dt>
                      <dd className="text-xs font-medium">{o.aprText || "See issuer"}</dd>
                    </div>
                  </dl>
                  <ul className="mt-3 space-y-1 text-sm">
                    {o.highlights.slice(0, 3).map((h) => (
                      <li key={h} className="flex gap-2">
                        <span aria-hidden className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent" />
                        {h}
                      </li>
                    ))}
                  </ul>
                  <div className="mt-auto pt-4">
                    <a
                      href={`/api/credit/offers/${encodeURIComponent(o.id)}/click`}
                      target="_blank"
                      rel="sponsored noopener noreferrer"
                      className="inline-flex w-full items-center justify-center gap-1.5 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                    >
                      See offer <ArrowUpRight size={14} aria-hidden />
                      <span className="sr-only">from {o.issuer} (opens in a new tab)</span>
                    </a>
                    <p className="mt-2 text-center text-[11px] text-muted">
                      EzWerkz may earn up to {formatCents(o.bountyCents)} if you&apos;re approved.
                    </p>
                  </div>
                </div>
              </article>
            </li>
          ))}
        </ul>
      ) : (
        <p className="rounded-2xl bg-surface-2 p-4 text-sm text-muted">No offers match your profile right now. Check back soon.</p>
      )}

      <details className="group rounded-2xl bg-surface-2 p-3 text-sm">
        <summary className="flex cursor-pointer list-none items-center gap-2 font-medium focus-visible:outline-2 focus-visible:outline-accent [&::-webkit-details-marker]:hidden">
          <Info size={16} aria-hidden className="text-accent" />
          Why am I seeing this?
        </summary>
        <div className="mt-2 space-y-2 text-muted">
          <p>
            Your latest score{score ? ` (${score.score})` : ""} is at or above {offers.threshold}, so the card matcher is on. We only show cards whose
            issuers typically approve applicants in your score range.
          </p>
          <p>
            Offers are ranked by fit: first the lowest annual fee, then the most useful features. What EzWerkz might earn is shown on each card and
            is never used to rank them.
          </p>
          <p>Approval isn&apos;t guaranteed, and applying usually means a hard inquiry by the issuer, which can affect your score.</p>
          {offers.notYet.length ? (
            <p>
              {offers.notYet.length} offer{offers.notYet.length === 1 ? " is" : "s are"} hidden because {offers.notYet.length === 1 ? "it targets" : "they target"} a
              higher score range.
            </p>
          ) : null}
        </div>
      </details>
    </section>
  );
}
