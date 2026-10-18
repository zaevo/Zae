import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { ShieldCheck } from "lucide-react";
import { getSessionUser } from "@/lib/auth";
import { formatCents } from "@/lib/money";
import { listBillAnalyses } from "@/lib/credit/queries";
import { PageHeader } from "@/components/ui/PageHeader";
import { BillAnalysisView } from "@/components/credit/BillAnalysisView";
import { BillUploader } from "@/components/credit/BillUploader";
import { CreditNotAvailable, canUseCredit } from "@/components/credit/CreditGate";
import { formatLongDate } from "@/components/credit/format";

export const metadata: Metadata = { title: "Bill Negotiator" };
export const dynamic = "force-dynamic";

export default async function BillsPage() {
  const user = await getSessionUser();
  if (!user) redirect("/login");
  if (!canUseCredit(user)) return <CreditNotAvailable />;
  const past = await listBillAnalyses(user);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="AI Bill Negotiator"
        title="Find savings on your bills"
        subtitle="Upload a phone, internet, utility or insurance bill. We'll flag charges worth questioning and write a script you can use yourself."
      />
      <p className="flex items-start gap-2 rounded-2xl bg-surface-2 p-3 text-xs text-muted">
        <ShieldCheck size={16} aria-hidden className="mt-px shrink-0 text-positive" />
        EzWerkz never calls or writes to your provider and never speaks for you. Your bill is stored privately and used only for this analysis.
      </p>

      <BillUploader />

      {past.length ? (
        <section aria-labelledby="past-title" className="space-y-3">
          <h2 id="past-title" className="text-lg font-semibold tracking-tight">
            Past analyses
          </h2>
          <ul className="space-y-3">
            {past.map((a) => (
              <li key={a.id}>
                <details className="group rounded-[var(--radius-card)] border border-line bg-surface p-4">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-3 focus-visible:outline-2 focus-visible:outline-accent [&::-webkit-details-marker]:hidden">
                    <span>
                      <span className="block font-semibold">{a.provider}</span>
                      <span className="block text-xs text-muted">Analyzed {formatLongDate(a.analyzedAt)}</span>
                    </span>
                    <span className="text-sm font-semibold text-positive">{formatCents(a.estimatedMonthlySavingsCents)}/mo</span>
                  </summary>
                  <div className="mt-4">
                    <BillAnalysisView analysis={a} />
                  </div>
                </details>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
