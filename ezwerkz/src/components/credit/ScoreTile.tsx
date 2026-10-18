import { Gauge, Info } from "lucide-react";
import { Card, CardTitle } from "@/components/ui/Card";
import { CONSENTS } from "@/content/consents";
import type { CreditSummary } from "@/lib/credit/summary";
import { SoftPullConsent } from "./SoftPullConsent";
import { formatLongDate } from "./format";

/** CROA: never promise a score change; the disclaimer sits right under the number. */
export const SCORE_DISCLAIMER = "Results vary. Late payments can lower your score.";

export function ScoreTile({ summary }: { summary: CreditSummary }) {
  const { score, softPullConsentAt } = summary;
  return (
    <Card>
      <div className="flex items-center justify-between">
        <CardTitle>Credit score</CardTitle>
        <Gauge size={18} aria-hidden className="text-muted" />
      </div>
      {score ? (
        <>
          <div className="mt-2 text-5xl font-bold tracking-tight">{score.score}</div>
          <p className="mt-1 text-xs text-muted">
            {score.source} · updated {formatLongDate(score.pulledAt)}. Checking is a soft inquiry and doesn&apos;t affect your score.
          </p>
        </>
      ) : softPullConsentAt ? (
        <p className="mt-2 text-sm text-muted">
          Thanks! Your score is on its way from our soft-inquiry partner and will appear here once it arrives.
        </p>
      ) : (
        <>
          <p className="mt-2 text-sm text-muted">See your score here, refreshed monthly. Checking it won&apos;t affect it.</p>
          <SoftPullConsent title={CONSENTS.soft_pull.title} body={CONSENTS.soft_pull.body} version={CONSENTS.soft_pull.version} />
        </>
      )}
      <p className="mt-3 flex items-start gap-1.5 text-xs font-medium text-muted">
        <Info size={14} aria-hidden className="mt-px shrink-0" />
        {SCORE_DISCLAIMER}
      </p>
    </Card>
  );
}
