import { formatCents } from "@/lib/money";
import { CREDIT } from "@/lib/pricing";
import type { CreditSummary } from "@/lib/credit/summary";
import { UtilizationRing } from "./UtilizationRing";

function HeroAmount({ cents }: { cents: number }) {
  const [whole, frac] = formatCents(cents).split(".");
  return (
    <span className="text-[2.75rem] font-bold leading-none tracking-tight sm:text-5xl">
      {whole}
      <span className="text-2xl font-semibold text-white/80">.{frac}</span>
    </span>
  );
}

const STATUS_LABEL = { open: "Active", closed: "Closed", charged_off: "Closed" } as const;

/** Revolut-style credit line "card": available credit as the hero figure, utilization ring, and the three numbers. */
export function CreditLineCard({ summary }: { summary: CreditSummary }) {
  const line = summary.line!;
  return (
    <section
      aria-labelledby="credit-line-title"
      className="relative overflow-hidden rounded-[var(--radius-card)] bg-gradient-to-br from-accent to-accent-2 p-5 text-white shadow-lg sm:p-6"
    >
      <div aria-hidden className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-white/10" />
      <div aria-hidden className="pointer-events-none absolute -bottom-20 -left-10 h-40 w-40 rounded-full bg-white/5" />

      <div className="relative flex items-start justify-between gap-3">
        <div>
          <h2 id="credit-line-title" className="text-xs font-semibold uppercase tracking-wider text-white/80">
            EzWerkz Credit Builder
          </h2>
          <p className="mt-0.5 text-xs text-white/70">
            Store line <span aria-hidden>••••</span>
            <span className="sr-only">ending in</span> {summary.accountLast4}
          </p>
        </div>
        <span className="rounded-full bg-white/20 px-2.5 py-0.5 text-xs font-semibold">{STATUS_LABEL[line.status]}</span>
      </div>

      <div className="relative mt-6 flex items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm text-white/80">Available to spend</div>
          <div className="mt-1">
            <HeroAmount cents={summary.availableCents} />
          </div>
          <div className="mt-2 text-sm text-white/80">of {formatCents(line.limitCents)} limit</div>
        </div>
        <UtilizationRing value={summary.utilization} />
      </div>

      <dl className="relative mt-6 grid grid-cols-3 gap-2 rounded-2xl bg-white/10 p-3 text-center">
        <div>
          <dt className="text-[11px] font-medium uppercase tracking-wider text-white/70">Used</dt>
          <dd className="mt-0.5 text-sm font-semibold">{formatCents(line.balanceCents)}</dd>
        </div>
        <div>
          <dt className="text-[11px] font-medium uppercase tracking-wider text-white/70">Limit</dt>
          <dd className="mt-0.5 text-sm font-semibold">{formatCents(line.limitCents)}</dd>
        </div>
        <div>
          <dt className="text-[11px] font-medium uppercase tracking-wider text-white/70">Membership</dt>
          <dd className="mt-0.5 text-sm font-semibold">{formatCents(CREDIT.membershipFeeCents)}/mo</dd>
        </div>
      </dl>
    </section>
  );
}
