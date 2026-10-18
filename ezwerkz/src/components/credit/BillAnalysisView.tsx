"use client";

import { FileText, MessageSquareText, Phone, PiggyBank } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Card, CardTitle } from "@/components/ui/Card";
import { formatCents } from "@/lib/money";
import type { BillAnalysis, IssueKind } from "@/lib/ai/billAnalysis";
import { CopyButton } from "./CopyButton";
import { formatLongDate } from "./format";

const ISSUE_LABEL: Record<IssueKind, string> = {
  promo_expired: "Promo ended",
  rate_increase: "Rate increase",
  duplicate_charge: "Duplicate charge",
  equipment_rental: "Equipment rental",
  unrequested_service: "Add-on",
  late_fee: "Late fee",
  overage: "Overage",
  junk_fee: "Avoidable fee",
  plan_mismatch: "Plan fit",
  billing_error: "Possible error",
  other: "Other",
};

const CONFIDENCE_TONE = { high: "positive", medium: "accent", low: "neutral" } as const;

const CATEGORY_LABEL: Record<BillAnalysis["category"], string> = {
  electric: "Electric",
  gas: "Gas",
  water: "Water",
  phone: "Phone",
  internet: "Internet",
  cable_tv: "TV",
  insurance: "Insurance",
  other: "Bill",
};

function scriptText(a: BillAnalysis): string {
  const s = a.negotiationScript;
  return [
    s.opening,
    "",
    ...s.talkingPoints.map((p) => `• ${p}`),
    "",
    "If they say no:",
    ...s.ifTheySayNo.map((p) => `• ${p}`),
    "",
    s.closing,
  ].join("\n");
}

export function BillAnalysisView({ analysis: a }: { analysis: BillAnalysis }) {
  const period =
    a.billingPeriodStart && a.billingPeriodEnd ? `${formatLongDate(a.billingPeriodStart)} – ${formatLongDate(a.billingPeriodEnd)}` : null;

  if (!a.isBill) {
    return (
      <Card>
        <CardTitle>We couldn&apos;t read a bill here</CardTitle>
        <p className="mt-2 text-sm text-muted">{a.summary || "Try a clearer photo of the full bill, or upload the PDF from your provider's website."}</p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>
              {CATEGORY_LABEL[a.category]} bill{a.fileName ? ` · ${a.fileName}` : ""}
            </CardTitle>
            <h2 className="mt-1 text-xl font-semibold tracking-tight">{a.provider}</h2>
            {period ? <p className="text-sm text-muted">{period}</p> : null}
          </div>
          <div className="text-right">
            <div className="text-xs text-muted">Total due</div>
            <div className="text-xl font-semibold">{formatCents(a.totalDueCents)}</div>
          </div>
        </div>
        <div className="mt-4 flex items-center gap-3 rounded-2xl bg-positive/10 p-4">
          <PiggyBank size={28} aria-hidden className="shrink-0 text-positive" />
          <div>
            <div className="text-sm font-medium">Possible savings</div>
            <div className="text-2xl font-bold tracking-tight">
              {formatCents(a.estimatedMonthlySavingsCents)}
              <span className="text-sm font-medium text-muted">/mo</span>
            </div>
            <div className="text-xs text-muted">
              About {formatCents(a.estimatedAnnualSavingsCents)} a year
              {a.oneTimeCreditsCents > 0 ? ` plus ${formatCents(a.oneTimeCreditsCents)} in one-time credits` : ""}. Estimates, not guarantees.
            </div>
          </div>
        </div>
        {a.summary ? <p className="mt-3 text-sm">{a.summary}</p> : null}
      </Card>

      {a.flaggedIssues.length ? (
        <section aria-labelledby="flagged-title" className="space-y-3">
          <h2 id="flagged-title" className="text-lg font-semibold tracking-tight">
            What we flagged
          </h2>
          <ul className="space-y-3">
            {a.flaggedIssues.map((i, idx) => (
              <li key={idx}>
                <Card className="p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="accent">{ISSUE_LABEL[i.kind]}</Badge>
                    <Badge tone={CONFIDENCE_TONE[i.confidence]}>{i.confidence} confidence</Badge>
                  </div>
                  <div className="mt-2 flex items-start justify-between gap-3">
                    <h3 className="font-semibold">{i.title}</h3>
                    <span className="shrink-0 text-sm font-semibold text-positive">
                      {i.estimatedMonthlySavingsCents > 0
                        ? `${formatCents(i.estimatedMonthlySavingsCents)}/mo`
                        : i.oneTimeCreditCents > 0
                          ? `${formatCents(i.oneTimeCreditCents)} once`
                          : ""}
                    </span>
                  </div>
                  <blockquote className="mt-2 rounded-xl border-l-4 border-accent/40 bg-surface-2 px-3 py-2 font-mono text-xs text-muted">
                    <span className="sr-only">From your bill: </span>
                    {i.evidence}
                  </blockquote>
                  <p className="mt-2 text-sm text-muted">{i.explanation}</p>
                  <p className="mt-2 text-sm">
                    <span className="font-medium">Ask: </span>
                    {i.suggestedAsk}
                  </p>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <Card>
          <p className="text-sm text-muted">Nothing stood out on this bill. That&apos;s good news.</p>
        </Card>
      )}

      <Card>
        <div className="flex items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 font-semibold">
            <Phone size={16} aria-hidden /> Call script
          </h2>
          <CopyButton text={scriptText(a)} label="Copy script" />
        </div>
        <p className="mt-1 text-xs text-muted">You make the call and speak for yourself. Change anything that doesn&apos;t fit your situation.</p>
        <div className="mt-3 space-y-3 text-sm">
          <p>{a.negotiationScript.opening}</p>
          <ol className="list-decimal space-y-1.5 pl-5">
            {a.negotiationScript.talkingPoints.map((p, idx) => (
              <li key={idx}>{p}</li>
            ))}
          </ol>
          {a.negotiationScript.ifTheySayNo.length ? (
            <div>
              <p className="font-medium">If they say no</p>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-muted">
                {a.negotiationScript.ifTheySayNo.map((p, idx) => (
                  <li key={idx}>{p}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <p>{a.negotiationScript.closing}</p>
        </div>
      </Card>

      <Card>
        <div className="flex items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 font-semibold">
            <FileText size={16} aria-hidden /> Email or letter
          </h2>
          <CopyButton text={`Subject: ${a.letterDraft.subject}\n\n${a.letterDraft.body}`} label="Copy letter" />
        </div>
        <p className="mt-3 text-sm font-medium">Subject: {a.letterDraft.subject}</p>
        <pre className="mt-2 whitespace-pre-wrap break-words rounded-2xl bg-surface-2 p-3 font-sans text-sm">{a.letterDraft.body}</pre>
      </Card>

      {a.questionsToAsk.length ? (
        <Card>
          <div className="flex items-center justify-between gap-3">
            <h2 className="flex items-center gap-2 font-semibold">
              <MessageSquareText size={16} aria-hidden /> Questions to ask
            </h2>
            <CopyButton text={a.questionsToAsk.map((q) => `• ${q}`).join("\n")} label="Copy" />
          </div>
          <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm">
            {a.questionsToAsk.map((q, idx) => (
              <li key={idx}>{q}</li>
            ))}
          </ul>
        </Card>
      ) : null}

      {a.lineItems.length ? (
        <details className="rounded-[var(--radius-card)] border border-line bg-surface p-5">
          <summary className="cursor-pointer text-sm font-semibold focus-visible:outline-2 focus-visible:outline-accent">
            All {a.lineItems.length} line items
          </summary>
          <table className="mt-3 w-full text-sm">
            <caption className="sr-only">Line items on this bill</caption>
            <thead>
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="pb-2 font-medium">
                  Item
                </th>
                <th scope="col" className="pb-2 text-right font-medium">
                  Amount
                </th>
              </tr>
            </thead>
            <tbody>
              {a.lineItems.map((l, idx) => (
                <tr key={idx} className="border-t border-line">
                  <td className="py-2 pr-3">{l.description}</td>
                  <td className="py-2 text-right tabular-nums">{formatCents(l.amountCents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ) : null}

      <p className="text-xs text-muted">
        {a.source === "demo" ? "Sample analysis (demo mode). " : "Analyzed with Claude. "}
        These are suggestions for you to use yourself. EzWerkz never contacts your provider or speaks on your behalf.
      </p>
    </div>
  );
}
