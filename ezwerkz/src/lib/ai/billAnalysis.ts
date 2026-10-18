/**
 * Bill analysis shape, post-processing and the demo mock. Pure: safe to
 * import from client components for types (the Claude call lives in
 * billNegotiator.ts, which is server-only).
 *
 * The negotiator only ever *suggests* what the member can say. EzWerkz
 * never contacts providers or speaks for the member (SPEC §2 rule 12).
 */
import { z } from "zod";

export const BILL_CATEGORIES = ["electric", "gas", "water", "phone", "internet", "cable_tv", "insurance", "other"] as const;
export type BillCategory = (typeof BILL_CATEGORIES)[number];

export const LINE_ITEM_KINDS = ["recurring", "usage", "one_time", "fee", "tax", "discount", "other"] as const;

export const ISSUE_KINDS = [
  "promo_expired",
  "rate_increase",
  "duplicate_charge",
  "equipment_rental",
  "unrequested_service",
  "late_fee",
  "overage",
  "junk_fee",
  "plan_mismatch",
  "billing_error",
  "other",
] as const;
export type IssueKind = (typeof ISSUE_KINDS)[number];

/**
 * What Claude returns (structured output). Kept to features structured
 * outputs support: objects, arrays, enums, nullable strings, integers.
 */
export const BillAnalysisModelSchema = z.object({
  isBill: z.boolean().describe("false if the document is not a utility, phone, internet, TV or insurance bill, or is unreadable"),
  provider: z.string().describe("Company that issued the bill, as printed"),
  category: z.enum(BILL_CATEGORIES),
  billingPeriodStart: z.string().nullable().describe("YYYY-MM-DD, or null if not shown"),
  billingPeriodEnd: z.string().nullable().describe("YYYY-MM-DD, or null if not shown"),
  totalDueCents: z.number().int().describe("Total amount due in integer US cents"),
  lineItems: z
    .array(
      z.object({
        description: z.string(),
        amountCents: z.number().int().describe("Integer cents; negative for credits and discounts"),
        kind: z.enum(LINE_ITEM_KINDS),
      }),
    )
    .describe("Every charge, credit, fee and tax line visible on the bill"),
  flaggedIssues: z.array(
    z.object({
      kind: z.enum(ISSUE_KINDS),
      title: z.string().describe("Short plain-English title"),
      evidence: z.string().describe("The exact text or line from the bill that supports this, quoted verbatim"),
      explanation: z.string().describe("Why this may be negotiable, in one or two plain sentences"),
      estimatedMonthlySavingsCents: z.number().int().describe("Conservative recurring monthly savings in cents; 0 if one-time"),
      oneTimeCreditCents: z.number().int().describe("Conservative one-time refund or waiver in cents; 0 if recurring"),
      confidence: z.enum(["low", "medium", "high"]),
      suggestedAsk: z.string().describe("What the member can politely ask for"),
    }),
  ),
  negotiationScript: z.object({
    opening: z.string().describe("First-person opening the account holder says themselves"),
    talkingPoints: z.array(z.string()),
    ifTheySayNo: z.array(z.string()),
    closing: z.string(),
  }),
  letterDraft: z.object({
    subject: z.string(),
    body: z.string().describe("Email or letter the member can send themselves; use [Your name] and [Account number] placeholders"),
  }),
  questionsToAsk: z.array(z.string()),
  summary: z.string().describe("Two-sentence summary for the member"),
});

export type BillAnalysisModelOutput = z.infer<typeof BillAnalysisModelSchema>;
export type FlaggedIssue = BillAnalysisModelOutput["flaggedIssues"][number];

export interface BillAnalysis extends BillAnalysisModelOutput {
  id: string;
  estimatedMonthlySavingsCents: number;
  estimatedAnnualSavingsCents: number;
  oneTimeCreditsCents: number;
  source: "claude" | "demo";
  model: string | null;
  fileName: string | null;
  analyzedAt: string;
}

/**
 * Phrases the script must never contain: threats, legal pressure used as
 * leverage, or anyone speaking for the member. The prompt forbids these;
 * this is the server-side backstop.
 */
const DISHONEST_PATTERNS: RegExp[] = [
  /\b(sue|suing|lawsuit|legal action|my (?:lawyer|attorney))\b/i,
  /\breport (?:you|your company)\b/i,
  /\bon behalf of\b/i,
  /\b(?:i am|i'm|this is) (?:calling )?(?:from|with) ezwerkz\b/i,
  /\bor else\b/i,
];

export function isDishonestLine(text: string): boolean {
  return DISHONEST_PATTERNS.some((re) => re.test(text));
}

function keepHonest(lines: string[]): string[] {
  return lines.filter((l) => !isDishonestLine(l));
}

function clampCents(value: number, max: number): number {
  if (!Number.isFinite(value) || value <= 0) return 0;
  return Math.min(Math.round(value), Math.max(0, max));
}

/** Normalize model output: no negative or impossible savings, totals computed here, scripts kept honest. */
export function finalizeBillAnalysis(
  raw: BillAnalysisModelOutput,
  meta: { id: string; source: BillAnalysis["source"]; model: string | null; fileName: string | null; analyzedAt?: string },
): BillAnalysis {
  const total = Math.max(0, Math.round(raw.totalDueCents));
  const issues = raw.isBill
    ? raw.flaggedIssues
        .filter((i) => i.evidence.trim().length > 0)
        .map((i) => ({
          ...i,
          estimatedMonthlySavingsCents: clampCents(i.estimatedMonthlySavingsCents, total),
          oneTimeCreditCents: clampCents(i.oneTimeCreditCents, total),
        }))
    : [];
  const monthly = Math.min(total, issues.reduce((n, i) => n + i.estimatedMonthlySavingsCents, 0));
  const oneTime = Math.min(total, issues.reduce((n, i) => n + i.oneTimeCreditCents, 0));
  const script = raw.negotiationScript;
  return {
    ...raw,
    id: meta.id,
    totalDueCents: total,
    flaggedIssues: issues,
    negotiationScript: {
      opening: isDishonestLine(script.opening) ? "Hi, I'm the account holder and I'd like to review a few charges on my latest bill." : script.opening,
      talkingPoints: keepHonest(script.talkingPoints),
      ifTheySayNo: keepHonest(script.ifTheySayNo),
      closing: isDishonestLine(script.closing) ? "Thanks for your help. Could you confirm the changes and my new monthly total by email?" : script.closing,
    },
    letterDraft: {
      subject: raw.letterDraft.subject,
      body: raw.letterDraft.body
        .split("\n")
        .filter((l) => !isDishonestLine(l))
        .join("\n"),
    },
    questionsToAsk: keepHonest(raw.questionsToAsk),
    estimatedMonthlySavingsCents: monthly,
    estimatedAnnualSavingsCents: monthly * 12,
    oneTimeCreditsCents: oneTime,
    source: meta.source,
    model: meta.model,
    fileName: meta.fileName,
    analyzedAt: meta.analyzedAt ?? new Date().toISOString(),
  };
}

/** A realistic analysis for demo mode (fictional provider). */
export function mockBillAnalysis(meta: { id: string; fileName: string | null; analyzedAt?: string }): BillAnalysis {
  const raw: BillAnalysisModelOutput = {
    isBill: true,
    provider: "Brightwave Wireless",
    category: "phone",
    billingPeriodStart: "2026-09-03",
    billingPeriodEnd: "2026-10-02",
    totalDueCents: 168_86,
    lineItems: [
      { description: "Unlimited Plus plan — 2 lines", amountCents: 120_00, kind: "recurring" },
      { description: "Device Protection Plus — Line 2", amountCents: 15_00, kind: "recurring" },
      { description: "Loyalty credit (12 mo)", amountCents: 0, kind: "discount" },
      { description: "International calling pack", amountCents: 10_00, kind: "recurring" },
      { description: "Paper bill fee", amountCents: 2_99, kind: "fee" },
      { description: "Administrative & telco recovery charge", amountCents: 3_98, kind: "fee" },
      { description: "Late payment fee", amountCents: 7_50, kind: "one_time" },
      { description: "Taxes, surcharges & regulatory fees", amountCents: 9_39, kind: "tax" },
    ],
    flaggedIssues: [
      {
        kind: "promo_expired",
        title: "Your $20 loyalty credit ended",
        evidence: "Loyalty credit (12 mo) — ended 09/02 ........ $0.00 (was -$20.00)",
        explanation: "Promotional credits often end quietly. Providers frequently renew them for customers in good standing who ask.",
        estimatedMonthlySavingsCents: 20_00,
        oneTimeCreditCents: 0,
        confidence: "medium",
        suggestedAsk: "Ask whether the loyalty credit can be renewed or replaced with a current existing-customer offer.",
      },
      {
        kind: "unrequested_service",
        title: "Device protection on Line 2",
        evidence: "Device Protection Plus — Line 2 ........ $15.00",
        explanation: "If Line 2's phone is older or already covered elsewhere, this add-on may not be worth $180 a year.",
        estimatedMonthlySavingsCents: 15_00,
        oneTimeCreditCents: 0,
        confidence: "medium",
        suggestedAsk: "Ask what the plan covers and remove it if you don't need it.",
      },
      {
        kind: "plan_mismatch",
        title: "International pack you may not use",
        evidence: "International calling pack ........ $10.00",
        explanation: "If you rarely call abroad, pay-per-use or a free calling app is usually cheaper.",
        estimatedMonthlySavingsCents: 10_00,
        oneTimeCreditCents: 0,
        confidence: "low",
        suggestedAsk: "Ask how many international minutes you used in the last three months and drop the pack if it's few.",
      },
      {
        kind: "junk_fee",
        title: "Paper bill fee",
        evidence: "Paper bill fee ........ $2.99",
        explanation: "Switching to paperless billing removes this fee.",
        estimatedMonthlySavingsCents: 2_99,
        oneTimeCreditCents: 0,
        confidence: "high",
        suggestedAsk: "Switch to paperless billing.",
      },
      {
        kind: "late_fee",
        title: "One-time late fee",
        evidence: "Late payment fee ........ $7.50",
        explanation: "Many providers waive a first late fee as a courtesy if your account is otherwise in good standing.",
        estimatedMonthlySavingsCents: 0,
        oneTimeCreditCents: 7_50,
        confidence: "medium",
        suggestedAsk: "Ask for a one-time courtesy waiver of the late fee.",
      },
    ],
    negotiationScript: {
      opening:
        "Hi, my name is [your name] and I'm the account holder. I'm calling about my bill for September 3 to October 2. I've been a customer for [how long] and I'd like to review a few charges with you.",
      talkingPoints: [
        "My $20 loyalty credit ended on September 2. Is it possible to renew it, or is there a current offer for existing customers?",
        "I see Device Protection Plus on Line 2 for $15 a month. Can you tell me what it covers? If I don't need it, I'd like to remove it.",
        "I'd like to check how much I've used the international calling pack. If it's very little, please remove it.",
        "Please switch me to paperless billing so the $2.99 paper bill fee goes away.",
        "There's a $7.50 late fee this month. I'm normally on time — would you be able to waive it as a one-time courtesy?",
      ],
      ifTheySayNo: [
        "I understand. Is there anyone in the loyalty or retention team who could look at this?",
        "Are there any plans that fit how I actually use my lines at a lower price?",
        "Could you note my request on the account so I can follow up next month?",
      ],
      closing:
        "Thank you for your help. Before we finish, could you confirm which changes were made, my new monthly total, and send a confirmation by email or text?",
    },
    letterDraft: {
      subject: "Request to review charges on my account",
      body: [
        "Hello,",
        "",
        "I'm writing about my bill for September 3 – October 2, 2026 (account [Account number]).",
        "",
        "I'd like to ask for the following:",
        "1. Renewal of my $20/month loyalty credit, which ended on September 2, or any current offer for existing customers.",
        "2. Details on Device Protection Plus for Line 2 ($15/month) and its removal if it isn't needed.",
        "3. Removal of the international calling pack ($10/month) if my usage is low.",
        "4. Paperless billing, removing the $2.99 paper bill fee.",
        "5. A one-time courtesy waiver of the $7.50 late fee.",
        "",
        "Please confirm any changes and my new monthly total in writing.",
        "",
        "Thank you,",
        "[Your name]",
      ].join("\n"),
    },
    questionsToAsk: [
      "When exactly did my loyalty credit end, and can it be renewed?",
      "What does Device Protection Plus cover, and what's the deductible?",
      "How many international minutes did I use in the last three months?",
      "Is there a plan for two lines that costs less than what I pay now?",
      "Can you confirm the changes and my new total in writing?",
    ],
    summary:
      "Your Brightwave bill went up mainly because a $20 loyalty credit ended. You could save about $48 a month by asking to renew it and trimming add-ons, plus a possible $7.50 one-time late fee waiver.",
  };
  return finalizeBillAnalysis(raw, { id: meta.id, source: "demo", model: null, fileName: meta.fileName, analyzedAt: meta.analyzedAt });
}
